"""
emit_verilog.py  — RTL Copilot hierarchical code generator
=============================================================
Returns a dict:
  {
    "top.v":           <top-level Verilog that instantiates sub-modules>,
    "reg_<name>.v":    <per-instance register module>,
    "counter_<name>.v":<per-instance counter module>,
    ...
  }

Every macro block and structural block (mux > 2 inputs, reg, shift-reg,
FIFO, penc, sync) gets its own standalone, parameterized .v file.
Combinational-only blocks (comb, const, encoder, decoder, splitter,
concatenator) are emitted inline in top.v as assign statements.
FSM logic is also emitted inline in top.v as always blocks — no separate
sub-module, so condition signals are naturally in scope.

cli usage:
  python emit_verilog.py <ir.json>
  → prints JSON: { "files": {"top.v": "...", ...} }
"""

import json
import sys
import math
import traceback


from emit_mux      import emit_mux,      mux_instantiation
from emit_counter  import emit_counter,  counter_instantiation
from emit_shiftreg import emit_shiftreg, shiftreg_instantiation
from emit_fifo     import emit_fifo,     fifo_instantiation
from emit_penc          import emit_penc,          penc_instantiation
from emit_sync          import emit_sync,          sync_instantiation
from emit_reg           import emit_reg,            reg_instantiation
from emit_fsm           import emit_fsm_inline  # updated: accepts gated_signals
from emit_edge_detector import emit_edge_detector,  edge_detector_instantiation
from emit_dpram         import emit_dpram,          dpram_instantiation
from emit_cfg_counter   import emit_cfg_counter,    cfg_counter_instantiation
try:
    from net_ir import build_net_ir, get_driver_wire as _net_get_driver
    _NET_IR_AVAILABLE = True
except ImportError:
    _NET_IR_AVAILABLE = False


def _safe_int(val, default: int) -> int:
    """
    Convert val to int safely.
    If val is a parameter name (e.g. "DATA_WIDTH") or otherwise non-numeric,
    return default instead of crashing.
    """
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return default


def _safe_name(node: dict) -> str:
    """Return a safe Verilog identifier for a node."""
    label = (
        node.get("data", {}).get("name")
        or node.get("name")
        or node.get("label")
        or node.get("id", "node")
    )
    return str(label).strip().replace(" ", "_").replace("-", "_")


def _get_src(edges: list, raw_nodes: list, name_map: dict,
             ports: list, dst_id: str, dst_port: str = None) -> str:
    """
    Resolve the signal name that drives (dst_id, dst_port).
    Follows probe transparency, const node pass-through, and splitter slice notation.
    Returns "0" when unconnected.

    Key behaviours:
    - const nodes that are themselves driven by an upstream wire resolve to
      that upstream signal name (not their literal value).
    - FSM output signal nodes (isFsmOutput=True) resolve to the FSM signal wire.
    - macro_cfgcounter: returns {name}_tc for tc port, {name}_count for count port.
    """
    match = next(
        (e for e in edges
         if e["dst"] == dst_id and (dst_port is None or e.get("dst_port") == dst_port)),
        None
    )
    if not match:
        return "0"

    src_id   = match["src"]
    src_port = match.get("src_port", "")

    port_obj = next((p for p in ports if p.get("id") == src_id), None)
    if port_obj:
        return port_obj["name"]

    src_node = next((n for n in raw_nodes if n["id"] == src_id), None)
    if not src_node:
        return src_id

    src_name = name_map.get(src_id, src_id)

    if src_node["type"] == "probe":
        return _get_src(edges, raw_nodes, name_map, ports, src_id)

    if src_node["type"] == "fsm_state":

        return src_port if (src_port and src_port != "out") else src_name

    if src_node.get("data", {}).get("isFsmOutput"):
        sig_name = src_node.get("data", {}).get("name", "")
        if sig_name:
            return sig_name
        if "__out_" in src_id:
            return src_id.split("__out_")[-1]


    if src_node["type"] == "const":
        upstream_edge = next((e for e in edges if e["dst"] == src_id), None)
        if upstream_edge:
            return _get_src(edges, raw_nodes, name_map, ports,
                            upstream_edge["src"], upstream_edge.get("src_port"))

        val = (src_node.get("value")
               or src_node.get("data", {}).get("value", "0"))
        return str(val)

    if src_node["type"] == "splitter":
        parent = _get_src(edges, raw_nodes, name_map, ports, src_id)
        raw_range = str(src_node.get("bitIndex",
                        src_node.get("data", {}).get("bitIndex", "0"))).strip()
        return f"{parent}[{raw_range}]"

    if src_node["type"] == "math":
        return f"{src_name}_{src_port or 'out'}"

    if src_node["type"] == "macro_fifo":
        port_map = {
            "dout":    f"{src_name}_dout",
            "full":    f"{src_name}_full",
            "empty":   f"{src_name}_empty",
            "a_empty": f"{src_name}_ae",
        }
        return port_map.get(src_port, f"{src_name}_{src_port or 'dout'}")

    if src_node["type"] == "macro_penc":
        return f"{src_name}_{src_port or 'index'}"

    if src_node["type"] == "macro_dpram":
        return f"{src_name}_{src_port or 'dout_a'}"

    if src_node["type"] == "macro_cfgcounter":

        port_wire_map = {
            "tc":            f"{src_name}_tc",
            "terminal_count":f"{src_name}_tc",
            "count":         f"{src_name}_count",
        }
        return port_wire_map.get(src_port, f"{src_name}_{src_port or 'tc'}")

    if src_node["type"] == "custom_block":
        if src_port:
            return f"{src_name}_{src_port}"

        cb_ports = src_node.get("customPorts", [])
        first_out = next((p["name"] for p in cb_ports if p.get("dir") == "output"), None)
        return f"{src_name}_{first_out}" if first_out else src_name

    if src_node["type"] == "macro_shiftreg":

        sr_mode = str(src_node.get("srMode",
                      src_node.get("data", {}).get("srMode", "PISO"))).upper()
        if sr_mode in ("PISO", "SISO") and src_port in ("sout", "out", ""):
            return f"{src_name}_sout"
        return f"{src_name}_q"

    return src_name



def emit_verilog(ir: dict) -> dict:
    """
    Parameters
    ----------
    ir : the compiled IR dict from the React front-end

    Returns
    -------
    dict  { filename -> verilog_string }
      Always contains "top.v".
      Also contains one file per instantiated sub-module.
    """
    try:
        if isinstance(ir, dict) and "ir" in ir:
            ir = ir["ir"]

        raw_nodes   = ir.get("nodes", [])
        
        edges       = ir.get("edges", [])
        ports       = ir.get("ports", [])
        params_dict = ir.get("parameters", {})


        for n in raw_nodes:
            if "data" in n:
                for key in ("width", "op", "fifoDepth", "aeThresh",
                            "lsbPriority", "muxSize", "joinerSize",
                            "bitIndex", "fsmOutputs", "value",
                            "overrides", "default", "fsm"):
                    if key in n["data"] and key not in n:
                        n[key] = n["data"][key]

        MACRO_TYPES = {
            "macro_counter", "macro_shiftreg", "macro_sync",
            "macro_fifo", "macro_penc",
            "macro_edgedet", "macro_dpram", "macro_cfgcounter"
        }
        nodes = [
            n for n in raw_nodes
            if (n.get("abstraction") not in ["L1", "L2"] or n["type"] in MACRO_TYPES)
            and n["type"] not in ("output", "probe")
            and not (n.get("data", {}).get("isFsmOutput") or n.get("isFsmOutput"))
        ]


        seen_port_names = set()
        filtered_ports  = []
        for p in ports:
            pid   = p.get("id", "")
            pname = p.get("name", "")
            if "__" in pid:
                continue
            if pname in seen_port_names:
                continue
            seen_port_names.add(pname)
            filtered_ports.append(p)
        ports = filtered_ports

        fsm_output_ids = {
            n["id"] for n in raw_nodes
            if n.get("data", {}).get("isFsmOutput") or n.get("isFsmOutput")
        }

        seen_port_names = set()
        filtered_ports  = []
        for p in ports:
            pname = p.get("name", "")

            if "__" in p.get("id", ""):
                continue

            if pname in seen_port_names:
                continue
            seen_port_names.add(pname)
            filtered_ports.append(p)
        ports = filtered_ports

        if not nodes and not ports:
            return {"top.v": "// No components found on canvas."}


        name_map = {n["id"]: _safe_name(n) for n in raw_nodes}

        state_nodes = [n for n in nodes if n["type"] == "fsm_state"]
        math_nodes  = [n for n in nodes if n["type"] == "math"]
        has_fsm     = len(state_nodes) > 0

        requires_clock = (
            has_fsm
            or any(n["type"] in ("reg", "rom") for n in nodes)
            or any(n["type"].startswith("macro_") for n in nodes)
            or len(math_nodes) > 0
            or any(
                n["type"] == "custom_block" and
                n.get("customSchema", {}).get("pattern", "") in
                    ("counter_based", "register_based", "shift_based")
                for n in nodes
            )
        )
        if requires_clock:
            if not any(p["name"] == "clk" for p in ports):
                ports.insert(0, {"name": "clk", "dir": "input", "width": 1})
            if not any(p["name"] == "rst" for p in ports):
                ports.insert(1, {"name": "rst", "dir": "input", "width": 1})

        _net_ir = None
        if _NET_IR_AVAILABLE:
            try:
                _net_ir = build_net_ir(raw_nodes, edges)
                if _net_ir.get("issues"):
                    for iss in _net_ir["issues"][:5]:
                        pass  
            except Exception:
                _net_ir = None

        def src(dst_id, dst_port=None):
            if _net_ir:
                wire = _net_get_driver(_net_ir, dst_id, dst_port)
                if wire and wire != "0":
                    return wire

            return _get_src(edges, raw_nodes, name_map, ports, dst_id, dst_port)

        sub_files   = {}  
        sub_insts   = []   

        top = []
        top.append(f"// Auto-generated top module - RTL Copilot")
        top.append(f"// Sub-modules compiled separately alongside this file\n")

        import sys as _sys
        print(f"[emit_verilog:verify] Parameters: {params_dict}", file=_sys.stderr, flush=True)
        print(f"[emit_verilog:verify] Ports: {[(p.get('name'), p.get('dir'), p.get('width')) for p in ports]}", file=_sys.stderr, flush=True)
        print(f"[emit_verilog:verify] signal_list len={len(ir.get('signal_list', []))}", file=_sys.stderr, flush=True)
        print(f"[emit_verilog:verify] gated_signals will be built from signal_list", file=_sys.stderr, flush=True)

        if params_dict:
            top.append(f"\nmodule top #(")
            p_lines = [f"    parameter {k} = {v}" for k, v in params_dict.items()]
            top.append(",\n".join(p_lines))
            top.append(f") (")
        else:
            top.append(f"\nmodule top (")
        port_decls = []
        for p in ports:
            w_val = str(p.get("width", 1))
            w     = f"[{w_val}-1:0] " if w_val != "1" else ""
            port_decls.append(f"    {p['dir']} {w}{p['name']}")
        top.append(",\n".join(port_decls))
        top.append(f");\n")

        op_map = {
            "add": "+", "sub": "-", "mul": "*", "and": "&", "or": "|",
            "xor": "^", "eq": "==", "gt": ">", "lt": "<",
            "not": "~", "shl": "<<", "shr": ">>"
        }


        _driven_outputs = {
            (name_map.get(e.get("src", e.get("source", "")),
                          e.get("src", e.get("source", ""))),
             e.get("src_port", e.get("sourceHandle", "")))
            for e in edges
        }

        for n in nodes:
            oid  = n["id"]
            nid  = name_map[oid]
            ntyp = n["type"]
            w    = n.get("width", 8)

            if "__" in oid and (ntyp in ("const", "output") or
                                  n.get("isFsmOutput") or
                                  n.get("data", {}).get("isFsmOutput")):
                continue


            if oid.startswith("_output_mux"):
                continue

            if ntyp in ("input", "fsm_state", "probe", "math"):
                continue

            if ntyp == "custom_block":
                cb_ports = n.get("customPorts", [])
                for p in cb_ports:
                    if p.get("dir") == "output":
                        pw = str(p.get("width", "1"))
                        w_decl = f"[{pw}-1:0] " if pw != "1" else ""
                        top.append(f"    wire {w_decl}{nid}_{p['name']};")
                continue

            if ntyp == "macro_fifo":
                fw = n.get("width", 8)
                top.append(f"    wire [{fw}-1:0] {nid}_dout;")
                top.append(f"    wire {nid}_full;")
                top.append(f"    wire {nid}_empty;")
                top.append(f"    wire {nid}_ae;")
                continue

            if ntyp == "macro_penc":
                w_pe  = _safe_int(n.get("width", 8), 8)
                idx_w = max(1, math.ceil(math.log2(max(w_pe, 2))))
                top.append(f"    wire [{idx_w}-1:0] {nid}_index;")
                top.append(f"    wire {nid}_valid;")
                continue

            if ntyp == "macro_dpram":
                dw = _safe_int(n.get("width", 32), 32)
                aw = _safe_int(n.get("addrWidth", 6), 6)
                top.append(f"    wire [{dw}-1:0] {nid}_dout_a;")
                top.append(f"    wire [{dw}-1:0] {nid}_dout_b;")
                continue

            if ntyp == "macro_cfgcounter":

                top.append(f"    wire {nid}_tc;")
                if (nid, "count") in _driven_outputs:
                    top.append(f"    wire [{w}-1:0] {nid}_count;")
                continue

            if ntyp == "macro_edgedet":
                top.append(f"    wire {nid};")   # single 1-bit pulse_out wire
                continue

            if ntyp == "macro_shiftreg":

                sr_mode = str(n.get("srMode", n.get("data", {}).get("srMode", "PISO"))).upper().strip()
                if sr_mode in ("PISO", "SISO"):
                    if (nid, "sout") in _driven_outputs:
                        top.append(f"    wire {nid}_sout;")
                else:
                    if (nid, "out") in _driven_outputs or (nid, "q") in _driven_outputs:
                        w_decl = f"[{w}-1:0] " if str(w) != "1" else ""
                        top.append(f"    wire {w_decl}{nid}_q;")
                continue

            if ntyp in ("macro_counter", "macro_sync"):

                if any(k[0] == nid for k in _driven_outputs):
                    w_decl = f"[{w}-1:0] " if str(w) != "1" else ""
                    top.append(f"    wire {w_decl}{nid};")
                continue

            w_decl = f"[{w}-1:0] " if str(w) != "1" else ""
            top.append(f"    wire {w_decl}{nid};")


        all_output_signals = []
        for sn in state_nodes:
            for row in sn.get("fsmOutputs", []):
                sig = row.get("signal", "").strip()
                if sig and sig not in all_output_signals:
                    all_output_signals.append(sig)

        _signal_list = ir.get("signal_list", [])
        gated_signals = {
            s["name"]: s["gated_by"]
            for s in _signal_list
            if "gated_by" in s
        }


        for sig in gated_signals:
            top.append(f"    wire {sig};")

        top.append("")   # blank line

        for n in nodes:
            nid  = name_map[n["id"]]
            oid  = n["id"]
            ntyp = n["type"]
            w    = str(n.get("width", "8"))

            if "__" in oid and (ntyp in ("const", "output") or
                                  n.get("isFsmOutput") or
                                  n.get("data", {}).get("isFsmOutput")):
                continue

            if ntyp in ("input", "probe", "fsm_state", "math",
                        "reg", "mux",
                        "macro_counter", "macro_shiftreg", "macro_sync",
                        "macro_fifo", "macro_penc",
                        "macro_edgedet", "macro_dpram", "macro_cfgcounter",
                        "custom_block"):
                continue   

            elif ntyp == "const":
                top.append(f"    assign {nid} = {n.get('value', '0')};")

            elif ntyp == "comb":
                op = n.get("op", "add")
                if op == "__state_mux__":
                    pass  
                elif op == "not":
                    top.append(f"    assign {nid} = ~{src(oid, 'in0')};")
                elif op == "buf":
                    top.append(f"    assign {nid} = {src(oid, 'in0')};")
                else:
                    top.append(
                        f"    assign {nid} = {src(oid, 'in0')} "
                        f"{op_map.get(op, '+')} {src(oid, 'in1')};"
                    )

            elif ntyp == "encoder":
                top.append(f"    assign {nid} = 1 << {src(oid, 'in0')};")

            elif ntyp == "decoder":
                top.append(f"    assign {nid} = $clog2({src(oid, 'in0')});")

            elif ntyp == "splitter":
                raw_range = str(n.get("bitIndex", "0")).strip()
                if ":" in raw_range:

                    top.append(f"    assign {nid} = {src(oid)}[{raw_range}];")
                else:

                    top.append(f"    assign {nid} = {src(oid)}[{raw_range}];")

            elif ntyp == "concatenator":
                c_size = _safe_int(n.get("joinerSize", 2), 2)
                parts  = [src(oid, f"in{i}") for i in range(c_size - 1, -1, -1)]
                top.append(f"    assign {nid} = {{{', '.join(parts)}}};")

            elif ntyp == "rom":
                depth = n.get("depth", 256)
                top.append(f"    reg [{w}-1:0] {nid}_mem [0:{depth}-1];")
                top.append(f"    assign {nid} = {nid}_mem[{src(oid, 'addr')}];")

        top.append("")

        if has_fsm:

            _fsm_sc_id = ""
            if state_nodes:
                _raw_id = state_nodes[0].get("id", "")
                if "__" in _raw_id:
                    _fsm_sc_id = _raw_id.split("__")[0]
            _fsm_prefix = (_fsm_sc_id.upper().replace("_", "") + "_") if _fsm_sc_id else ""

            print(f"[emit_verilog] FSM prefix: '{_fsm_prefix}' for {len(state_nodes)} states", file=_sys.stderr, flush=True)

            fsm_lines = emit_fsm_inline(
                state_nodes, name_map, edges, all_output_signals,
                gated_signals=gated_signals,
                fsm_prefix=_fsm_prefix
            )
            for line in fsm_lines:
                top.append(line)


            for sig, gate in gated_signals.items():
                top.append(f"    assign {sig} = {sig}_raw & {gate};")
            if gated_signals:
                top.append("")


        for n in nodes:
            nid  = name_map[n["id"]]
            oid  = n["id"]
            ntyp = n["type"]
            w    = _safe_int(n.get("width", 8) or 8, 8)

            if ntyp == "reg":
                d_sig = src(oid, "d")
                w_decl = f"[{w}-1:0] " if w > 1 else ""
                top.append(f"    // D-FF: {nid}")
                top.append(f"    reg {w_decl}{nid}_q;")
                top.append(f"    always @(posedge clk) begin")
                top.append(f"        if (rst) {nid}_q <= {w}'b0;")
                top.append(f"        else     {nid}_q <= {d_sig};")
                top.append(f"    end")
                top.append(f"    assign {nid} = {nid}_q;")
                top.append("")

            elif ntyp == "mux":
                m_size    = _safe_int(n.get("muxSize", 2), 2)
                sel_bits  = max(1, math.ceil(math.log2(m_size)))
                data_srcs = [src(oid, f"in{i}") for i in range(m_size)]

                if sel_bits == 1:
                    sel_sig = src(oid, "sel0")
                else:
                    sel_parts = [src(oid, f"sel{i}") for i in range(sel_bits - 1, -1, -1)]
                    sel_sig   = "{" + ", ".join(sel_parts) + "}"

                top.append(f"    // MUX: {nid}")
                if m_size == 2:
                    top.append(f"    assign {nid} = {sel_sig} ? {data_srcs[1]} : {data_srcs[0]};")
                else:
                    mod_name, mod_src = emit_mux(nid, m_size, w)
                    sub_files[f"{mod_name}.v"] = mod_src
                    top.append(mux_instantiation(
                        nid, m_size, w, sel_bits, data_srcs, sel_sig, nid
                    ))
                top.append("")

            elif ntyp == "macro_counter":
                mod_name, mod_src = emit_counter(nid, w)
                sub_files[f"{mod_name}.v"] = mod_src
                top.append(f"    // Counter: {nid}")
                top.append(counter_instantiation(
                    nid, w,
                    en_src  = src(oid, "en"),
                    res_src = src(oid, "res"),
                    out_wire = nid
                ))
                top.append("")

            elif ntyp == "macro_shiftreg":
                sr_mode = str(n.get("srMode", n.get("data", {}).get("srMode", "PISO"))).upper().strip()
                sr_dir  = str(n.get("shiftDir", n.get("data", {}).get("shiftDir", "right"))).lower().strip()
                if sr_mode not in ("SISO", "PISO", "SIPO", "PIPO"):
                    sr_mode = "PISO"
                if sr_dir not in ("right", "left"):
                    sr_dir = "right"

                has_parallel_in  = sr_mode in ("PISO", "PIPO")
                has_serial_in    = sr_mode in ("SISO", "SIPO")
                has_parallel_out = sr_mode in ("SIPO", "PIPO")
                has_serial_out   = sr_mode in ("SISO", "PISO")

                mod_name, mod_src = emit_shiftreg(nid, w, mode=sr_mode, direction=sr_dir)
                sub_files[f"{mod_name}.v"] = mod_src
                top.append(f"    // Shift Register ({sr_mode}, {sr_dir}): {nid}")

                top.append(shiftreg_instantiation(
                    nid, w,
                    mode      = sr_mode,
                    direction = sr_dir,
                    din_src   = src(oid, "din")  if has_parallel_in  else "0",
                    sin_src   = src(oid, "sin")  if has_serial_in    else "0",
                    load_src  = src(oid, "load") if sr_mode in ("PISO", "PIPO") else "0",
                    en_src    = src(oid, "en"),
                    out_wire  = f"{nid}_q"       if has_parallel_out else "",
                    sout_wire = f"{nid}_sout"    if has_serial_out   else "",
                ))
                top.append("")

            elif ntyp == "macro_sync":
                mod_name, mod_src = emit_sync(nid, w)
                sub_files[f"{mod_name}.v"] = mod_src
                top.append(f"    // CDC Sync: {nid}")
                top.append(sync_instantiation(
                    nid, w,
                    d_src  = src(oid, "d"),
                    q_wire = nid
                ))
                top.append("")

            elif ntyp == "macro_fifo":
                depth    = _safe_int(n.get("fifoDepth", 16) or 16, 16)
                ae_thr   = _safe_int(n.get("aeThresh",   4) or  4,  4)
                mod_name, mod_src = emit_fifo(nid, depth, w, ae_thr)
                sub_files[f"{mod_name}.v"] = mod_src
                top.append(f"    // FIFO: {nid}")

                _fsm_sigs = [
                    row.get("signal", "")
                    for sn in state_nodes
                    for row in sn.get("fsmOutputs", [])
                ]

                def _resolve_fifo_ctrl(handle):
                    """Resolve a FIFO control handle — canvas edge first,
                    then FSM output signal name matching by substring."""
                    resolved = src(oid, handle)
                    if resolved != "0":
                        return resolved

                    _synonyms = {
                        "wr_en": ["wr_en", "write_en", "fifo_write", "wren"],
                        "rd_en": ["rd_en", "read_en",  "fifo_read",  "rden"],
                    }
                    keywords = _synonyms.get(handle, [handle])
                    for sig in _fsm_sigs:
                        sig_l = sig.lower()
                        if any(kw in sig_l for kw in keywords):
                            return sig
                    return resolved  # returns "0" if nothing found

                top.append(fifo_instantiation(
                    nid, depth, w, ae_thr,
                    wr_en_src  = _resolve_fifo_ctrl("wr_en"),
                    din_src    = src(oid, "din"),
                    rd_en_src  = _resolve_fifo_ctrl("rd_en"),
                    dout_wire  = f"{nid}_dout",
                    full_wire  = f"{nid}_full",
                    empty_wire = f"{nid}_empty",
                    ae_wire    = f"{nid}_ae"
                ))
                top.append("")

            elif ntyp == "macro_penc":
                w_pe     = _safe_int(n.get("width", 8) or 8, 8)
                lsb_pri  = _safe_int(n.get("lsbPriority", 0) or 0, 0)
                mod_name, mod_src = emit_penc(nid, w_pe, lsb_pri)
                sub_files[f"{mod_name}.v"] = mod_src
                top.append(f"    // Priority Encoder: {nid}")
                top.append(penc_instantiation(
                    nid, w_pe, lsb_pri,
                    data_in_src = src(oid, "data_in"),
                    index_wire  = f"{nid}_index",
                    valid_wire  = f"{nid}_valid"
                ))
                top.append("")

            elif ntyp == "macro_edgedet":
                edge_type = _safe_int(n.get("edgeType", 0) or 0, 0)
                mod_name, mod_src = emit_edge_detector(nid, edge_type)
                sub_files[f"{mod_name}.v"] = mod_src
                top.append(f"    // Edge Detector: {nid}")
                top.append(edge_detector_instantiation(
                    nid, edge_type,
                    signal_in_src  = src(oid, "signal_in"),
                    pulse_out_wire = nid
                ))
                top.append("")

            elif ntyp == "macro_dpram":
                dw = _safe_int(n.get("width", 32) or 32, 32)
                aw = _safe_int(n.get("addrWidth", 6) or 6, 6)
                mod_name, mod_src = emit_dpram(nid, dw, aw)
                sub_files[f"{mod_name}.v"] = mod_src
                top.append(f"    // Dual-Port RAM: {nid}")
                top.append(dpram_instantiation(
                    nid, dw, aw,
                    we_a_src    = src(oid, "we_a"),
                    addr_a_src  = src(oid, "addr_a"),
                    din_a_src   = src(oid, "din_a"),
                    we_b_src    = src(oid, "we_b"),
                    addr_b_src  = src(oid, "addr_b"),
                    din_b_src   = src(oid, "din_b"),
                    dout_a_wire = f"{nid}_dout_a",
                    dout_b_wire = f"{nid}_dout_b"
                ))
                top.append("")

            elif ntyp == "macro_cfgcounter":
                count_dir     = _safe_int(n.get("countDir", 1) or 1, 1)
                terminal_value = (n.get("terminalValue") or
                                  n.get("data", {}).get("terminalValue") or None)
                mod_name, mod_src = emit_cfg_counter(nid, w, count_dir,
                                                      terminal_value=terminal_value)
                sub_files[f"{mod_name}.v"] = mod_src
                top.append(f"    // Configurable Counter: {nid}")
                # Try both "enable"/"en" and "load_value"/"load_val" handle names
                en_src  = src(oid, "enable") or src(oid, "en")
                lv_src  = src(oid, "load_value") or src(oid, "load_val")
                ld_src  = src(oid, "load")
                if en_src == "0": en_src = src(oid, "en")
                if lv_src == "0": lv_src = src(oid, "load_val")
                top.append(cfg_counter_instantiation(
                    nid, w, count_dir,
                    enable_src     = en_src,
                    load_src       = ld_src,
                    load_value_src = lv_src,
                    count_wire     = f"{nid}_count" if (nid, "count") in _driven_outputs else "",
                    tc_wire        = f"{nid}_tc",
                    terminal_value = terminal_value
                ))
                top.append("")

            elif ntyp == "custom_block":
                cb_name    = n.get("customName", nid)
                cb_verilog = n.get("customVerilog", "")
                cb_ports   = n.get("customPorts", [])

                if cb_verilog:
                    sub_files[f"{cb_name}.v"] = cb_verilog

                top.append(f"    // Custom Block: {cb_name}")
                inst_lines = [f"    {cb_name} {nid}_inst ("]

                input_cb_ports  = [p for p in cb_ports if p.get("dir") == "input"]
                output_cb_ports = [p for p in cb_ports if p.get("dir") == "output"]


                cb_type = n.get("customBlockType", n.get("block_type", ""))
                is_sequential = cb_type in ("counter_based", "register_based", "shift_based")
                is_first = True
                if is_sequential:
                    inst_lines.append(f"        .clk(clk),")
                    inst_lines.append(f"        .rst(rst)")
                    is_first = False

                for p in input_cb_ports:
                    pname   = p["name"]
                    sig_src = src(oid, pname)
                    prefix  = "        " if is_first else "        ,"
                    inst_lines.append(f"{prefix}.{pname}({sig_src})")
                    is_first = False

                for p in output_cb_ports:
                    pname    = p["name"]
                    out_wire = f"{nid}_{pname}"
                    prefix   = "        " if is_first else "        ,"
                    inst_lines.append(f"{prefix}.{pname}({out_wire})")
                    is_first = False

                inst_lines.append(f"    );")
                top.append("\n".join(inst_lines))
                top.append("")

        _ol_fsm_prefix = ""
        if state_nodes:
            _raw_id = state_nodes[0].get("id", "")
            if "__" in _raw_id:
                _sc_id = _raw_id.split("__")[0]
                _ol_fsm_prefix = (_sc_id.upper().replace("_", "") + "_") if _sc_id else ""

        _emitted_ol_signals = set()
        for ol in ir.get("output_logic", []):
            if ol.get("type") != "state_mux":
                continue
            out_name  = ol.get("output", "")
            default   = ol.get("default", "1'b0")
            overrides = ol.get("overrides", {})
            if not out_name:
                continue
            _emitted_ol_signals.add(out_name)
            if overrides:

                parts = [f"(current_state == {_ol_fsm_prefix}{state}) ? {val}"
                         for state, val in overrides.items()]
                chain = " :\n            ".join(parts)
                top.append(f"    assign {out_name} =")
                top.append(f"            {chain} :")
                top.append(f"            {default};")
            else:
                top.append(f"    assign {out_name} = {default};")
        top.append("")


        _fsm_reg_outputs = set()
        for sn in state_nodes:
            for row in sn.get("fsmOutputs", []):
                sig = row.get("signal", "")
                if sig:
                    _fsm_reg_outputs.add(sig)

        for p in [p for p in ports if p.get("dir") == "output"]:
            pname    = p["name"]
            psrc     = src(p["id"])
            if pname in _emitted_ol_signals:
                continue
            if pname in _fsm_reg_outputs:
                continue
            if psrc == pname:
                continue
            top.append(f"    assign {pname} = {psrc};")

        top.append("\nendmodule")


        top_str = "\n".join(top)
        result = {"top.v": top_str}
        result.update(sub_files)
        return result

    except Exception:
        traceback.print_exc()
        return {"top.v": "// Code generation failed. Please check your circuit and try again."}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    try:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            ir_data = json.load(f)
        output = json.dumps(emit_verilog(ir_data), indent=2, ensure_ascii=True)
        sys.stdout.buffer.write(output.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
    except Exception as e:
        traceback.print_exc()
        err = json.dumps({"top.v": "// Code generation failed. Please check your circuit and try again."}, ensure_ascii=True)
        sys.stdout.buffer.write(err.encode("utf-8"))
        sys.exit(1)