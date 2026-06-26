"""
net_ir.py
=========
Canonical Net IR — sits between compileIR() output and emit_verilog.py.

Converts the raw {src, dst, src_port, dst_port} edge graph into a
structured net model with explicit driver/consumer ownership, widths,
and signal domains.

Works correctly for all three user types:
  User 1 — manual circuits: no __ nodes, clean edges
  User 2 — AI-generated:   __ placeholder nodes, isFsmOutput proxies
  User 3 — hybrid:         mix of both

The net model is the single source of truth for Verilog emission.
"""

from __future__ import annotations
from typing import Any


_CLOCK_SIGNALS = frozenset({
    "clk", "clock", "rst", "reset", "rst_n", "reset_n",
})

_CONTROL_SIGNALS = frozenset({
    "en", "enable", "load", "wr_en", "rd_en", "shift_en",
    "we", "valid", "ready", "start", "done", "tc", "full",
    "empty", "a_empty", "almost_empty", "cs_n", "sclk",
    "cnt_en", "btn_out", "tx_bit", "not_empty", "bit_tc",
    "not_bit_tc", "sel", "stall", "flush", "clear",
    "ack", "req", "grant", "busy", "error", "overflow",
    "underflow", "hit", "miss",
})

_ONE_BIT_HANDLES = {
    "macro_fifo":       frozenset({"wr_en", "rd_en", "full", "empty", "a_empty"}),
    "macro_cfgcounter": frozenset({"tc", "en", "load"}),
    "macro_shiftreg":   frozenset({"en", "load", "sin", "sout"}),
    "macro_edgedet":    frozenset({"out", "en"}),
    "macro_sync":       frozenset({"out"}),
    "macro_counter":    frozenset({"en", "res"}),
    "fsm_state":        frozenset({"in", "out"}),
}


def _classify_domain(name: str, width: Any) -> str:
    n = name.lower().strip()
    if n in _CLOCK_SIGNALS or "clk" in n or "rst" in n:
        return "clock"
    if n in _CONTROL_SIGNALS:
        return "control"
    try:
        if int(width) == 1:
            return "control"
    except (ValueError, TypeError):
        pass
    return "data"


def _node_output_wire(node: dict, handle: str, name_map: dict) -> str:
    """
    Return the Verilog wire name for a node's output handle.
    Mirrors the logic in emit_verilog._get_src but operates on
    the net IR level — no edge traversal needed.
    """
    nid   = node.get("id", "")
    ntype = node.get("type", "")
    nname = name_map.get(nid, nid)
    data  = node.get("data", {})

    if "__" in nid and ntype == "const":
        return None  

    if data.get("isFsmOutput"):
        sig = data.get("name", "")
        if sig:
            return sig
        if "__out_" in nid:
            return nid.split("__out_")[-1]
        return nname

    if ntype == "fsm_state":
        return handle if (handle and handle != "out") else nname

    if ntype == "macro_cfgcounter":
        m = {"tc": f"{nname}_tc", "count": f"{nname}_count",
             "terminal_count": f"{nname}_tc"}
        return m.get(handle, f"{nname}_{handle or 'tc'}")

    if ntype == "macro_fifo":
        m = {"dout": f"{nname}_dout", "full": f"{nname}_full",
             "empty": f"{nname}_empty", "a_empty": f"{nname}_ae"}
        return m.get(handle, f"{nname}_{handle or 'dout'}")

    if ntype == "macro_shiftreg":
        sr_mode = str(data.get("srMode", "PISO")).upper()
        if sr_mode in ("PISO", "SISO") and handle in ("sout", "out", ""):
            return f"{nname}_sout"
        return nname

    if ntype == "macro_counter":
        return f"{nname}_count"

    if ntype == "macro_sync":
        return f"{nname}_out"

    if ntype == "macro_edgedet":
        return nname

    if ntype == "macro_dpram":
        m = {"dout_a": f"{nname}_dout_a", "dout_b": f"{nname}_dout_b"}
        return m.get(handle, f"{nname}_{handle or 'dout_a'}")

    if ntype == "macro_penc":
        m = {"index": f"{nname}_index", "valid": f"{nname}_valid"}
        return m.get(handle, f"{nname}_{handle or 'index'}")

    if ntype == "splitter":
        return nname  

    if ntype == "comb":
        return nname

    if ntype == "const":
        return nname

    if ntype == "input":
        return nname

    return nname


def _node_width(node: dict, handle: str) -> str:
    """Return width string for a node's handle."""
    ntype = node.get("type", "")
    data  = node.get("data", {})
    w     = str(data.get("width", node.get("width", "8")))

    if ntype in _ONE_BIT_HANDLES and handle in _ONE_BIT_HANDLES.get(ntype, set()):
        return "1"
    if ntype == "fsm_state" and handle not in ("in", "out"):
        return "1"
    if data.get("isFsmOutput"):
        return "1"

    return w


def build_net_ir(nodes: list, edges: list) -> dict:
    """
    Build canonical net IR from raw compileIR() output.

    Input edges format (from compileIR):
        {src, dst, src_port, dst_port, ...}

    Returns:
        {
          "nets": {
            "signal_name": {
              "wire":         str,          # Verilog wire/reg name
              "driver":       {node, handle, node_id},
              "consumers":    [{node, handle, node_id}],
              "width":        str,
              "domain":       str,          # clock|control|data
              "clock_domain": str,
              "is_port":      bool,
              "is_fsm_output":bool,
            }
          },
          "nodes":    {node_id: node_dict},
          "name_map": {node_id: wire_name},
          "issues":   [str],
        }
    """
    node_map: dict[str, dict] = {n["id"]: n for n in nodes}

    name_map: dict[str, str] = {}
    for n in nodes:
        nid  = n["id"]
        data = n.get("data", {})
        name = (data.get("name") or n.get("name") or n.get("label"))
        
        if not name:
            if "__" in nid:
                name = nid.rsplit("__", 1)[-1]
            else:
                name = nid

        name_map[nid] = str(name).strip().replace(" ", "_")

    placeholder_map: dict[str, str] = {}
    for e in edges:
        src_id = e.get("src", e.get("source", ""))
        dst_id = e.get("dst", e.get("target", ""))
        src_h  = e.get("src_port", e.get("sourceHandle", ""))

        dst_node = node_map.get(dst_id)
        if not dst_node or dst_node.get("type") != "const":
            continue
        if "__" not in dst_id:
            continue

        src_node = node_map.get(src_id)
        if not src_node:
            continue

        wire = _node_output_wire(src_node, src_h, name_map)
        if wire:
            placeholder_map[dst_id] = wire


    nets: dict[str, dict] = {}
    issues: list[str]     = []

    for e in edges:
        src_id   = e.get("src", e.get("source", ""))
        dst_id   = e.get("dst", e.get("target", ""))
        src_h    = e.get("src_port", e.get("sourceHandle", ""))
        dst_h    = e.get("dst_port", e.get("targetHandle", ""))
        cond     = e.get("condition", "")
        is_fsm   = bool(e.get("isFsm") or
                        (isinstance(e.get("data"), dict) and
                         e["data"].get("isFsm")))

        src_node = node_map.get(src_id)
        dst_node = node_map.get(dst_id)

        if not src_node or not dst_node:
            continue


        if "__" in src_id and src_node.get("type") == "const":
            continue


        src_wire = _node_output_wire(src_node, src_h, name_map)


        if src_wire is None:
            src_wire = placeholder_map.get(src_id, name_map.get(src_id, src_id))

        if not src_wire:
            continue


        dst_name = name_map.get(dst_id, dst_id)

        width = _node_width(src_node, src_h)


        domain = _classify_domain(src_wire, width)


        if src_wire not in nets:
            nets[src_wire] = {
                "wire":          src_wire,
                "driver":        {
                    "node_id": src_id,
                    "handle":  src_h,
                    "name":    name_map.get(src_id, src_id),
                },
                "consumers":     [],
                "width":         width,
                "domain":        domain,
                "clock_domain":  "clk",
                "is_port":       src_node.get("type") == "input",
                "is_fsm_output": bool(src_node.get("data", {}).get("isFsmOutput")),
                "is_fsm_edge":   is_fsm,
            }
        else:

            existing_driver = nets[src_wire]["driver"]["node_id"]
            if existing_driver != src_id and not is_fsm:
                issues.append(
                    f"MULTIPLE DRIVERS: net '{src_wire}' driven by "
                    f"'{src_id}' and '{existing_driver}'"
                )

        if "__" in dst_id and dst_node.get("type") == "const":
            continue

        nets[src_wire]["consumers"].append({
            "node_id": dst_id,
            "handle":  dst_h,
            "name":    dst_name,
        })

    driven_wires = set(nets.keys())
    for n in nodes:
        ntype = n.get("type", "")
        nid   = n["id"]
        nname = name_map.get(nid, nid)
        if "__" in nid:
            continue
        critical = {
            "macro_cfgcounter": [f"{nname}_tc"],
            "macro_fifo":       [f"{nname}_dout"],
        }
        if ntype in critical:
            for wire in critical[ntype]:
                if wire not in driven_wires:
                    issues.append(
                        f"DISCONNECTED OUTPUT: {nid} output '{wire}' "
                        f"has no consumers"
                    )

    return {
        "nets":             nets,
        "nodes":            node_map,
        "name_map":         name_map,
        "placeholder_map":  placeholder_map,
        "issues":           issues,
    }


def validate_net_ir(net_ir: dict) -> list[str]:
    """
    Run ownership and consistency checks on the net IR.
    Returns list of issue strings.
    """
    issues = list(net_ir.get("issues", []))
    nets   = net_ir.get("nets", {})

    for wire, net in nets.items():

        if net["domain"] == "clock" and net["consumers"]:
            issues.append(
                f"CLOCK SIGNAL USED AS DATA: '{wire}' is in clock domain "
                f"but has {len(net['consumers'])} consumer(s)"
            )


        if not net["consumers"] and not net["is_port"]:
            if net["domain"] == "data":
                issues.append(
                    f"UNUSED NET: '{wire}' is declared but has no consumers"
                )

    return issues


def net_ir_to_wire_list(net_ir: dict) -> list[dict]:
    """
    Flatten net IR into a sorted list of wire declarations
    for use by the Verilog emitter.

    Returns list of {name, width, domain, is_port, is_fsm_output}
    sorted by domain (clock first, then control, then data) then name.
    """
    wires = []
    seen  = set()

    for wire_name, net in net_ir["nets"].items():
        if wire_name in seen:
            continue
        seen.add(wire_name)


        if net["domain"] == "clock":
            continue


        if net["is_port"]:
            continue

        wires.append({
            "name":          wire_name,
            "width":         net["width"],
            "domain":        net["domain"],
            "is_fsm_output": net["is_fsm_output"],
            "driver":        net["driver"],
        })

    domain_order = {"control": 0, "data": 1, "clock": 2}
    wires.sort(key=lambda w: (domain_order.get(w["domain"], 1), w["name"]))
    return wires


def get_driver_wire(net_ir: dict, dst_node_id: str,
                    dst_handle: str = None) -> str:
    """
    Look up what drives a specific node input handle.
    Returns the wire name or "0" if unconnected.

    Replaces _get_src in emit_verilog.py for net-IR-aware emission.
    Handles both compileIR() {src/dst} and ReactFlow {source/target} formats.
    """
    if not net_ir:
        return "0"


    if dst_node_id in net_ir.get("placeholder_map", {}):
        return net_ir["placeholder_map"][dst_node_id]

    for wire_name, net in net_ir["nets"].items():
        for consumer in net["consumers"]:
            if consumer["node_id"] == dst_node_id:
                if dst_handle is None or consumer["handle"] == dst_handle:
                    return wire_name

    if dst_node_id in net_ir.get("nets", {}):
        return dst_node_id

    return "0"