

from __future__ import annotations

import port_contract as _pc


def _ir_validate(nodes: list, edges: list, hierarchy: dict | None = None) -> list[str]:
    """
    Run all IR validation passes. Returns list of issue strings.
    Empty list means IR is valid.
    """
    issues = []
    issues += _ir_check_width_mismatch(nodes, edges)
    issues += _ir_check_multiple_drivers(nodes, edges)
    issues += _ir_check_disconnected_outputs(nodes, edges)
    if hierarchy:
        issues += _ir_check_fsm_reachability(nodes, edges, hierarchy)
        issues += _ir_check_fsm_completeness(nodes, edges, hierarchy)
    return issues


def _ir_get_node_width(node: dict, handle: str) -> str | None:
    """
    Return the declared width of a node's handle.
    Uses known handle-width mappings for macro types.
    """
    ntype = node.get("type", "")
    data  = node.get("data", {})
    w     = str(data.get("width", "8"))

    def _dw(default=8):
        try:
            return max(1, int(str(w).strip()))
        except (TypeError, ValueError):
            return default

    try:
        aw = max(1, int(str(data.get("addrWidth", 6)).strip()))
    except (TypeError, ValueError):
        aw = 6

    h = _pc.canonical(handle)
    for direction in ("outputs", "inputs"):
        try:
            resolved = _pc.resolve_width(
                ntype, h, direction=direction, data_width=_dw(),
                comb_op=data.get("op"), addr_width=aw,
                sr_mode=data.get("srMode"))
        except KeyError:
            continue
        if resolved is None:
            return None         
        return str(resolved)

    if ntype == "fsm_state":
        return "1"

    return w


def _ir_check_width_mismatch(nodes: list, edges: list) -> list[str]:
    """
    Check every edge for width mismatch between source and target.
    """
    issues    = []
    node_map  = {n["id"]: n for n in nodes}

    for e in edges:
        src_id = e.get("source", "")
        tgt_id = e.get("target", "")
        sh     = e.get("sourceHandle", "out")
        th     = e.get("targetHandle", "in")

        src_node = node_map.get(src_id)
        tgt_node = node_map.get(tgt_id)

        if not src_node or not tgt_node:
            continue

        if tgt_node.get("type") == "splitter":
            continue
        if src_node.get("type") == "concatenator":
            continue

        if src_node.get("data", {}).get("isFsmOutput"):
            continue


        src_w = _ir_get_node_width(src_node, sh)
        tgt_w = _ir_get_node_width(tgt_node, th)

        if src_w and tgt_w:
            try:
                if int(src_w) != int(tgt_w):
                    issues.append(
                        f"WIDTH MISMATCH: {src_id}[{sh}]({src_w}-bit) -> "
                        f"{tgt_id}[{th}]({tgt_w}-bit)"
                    )
            except ValueError:
                pass  

    return issues


def _ir_check_multiple_drivers(nodes: list, edges: list) -> list[str]:
    """
    Check that no input handle is driven by more than one source.
    FSM transition edges (type=fsm) are exempt.
    """
    issues  = []
    drivers: dict[tuple, list] = {}

    for e in edges:
        if e.get("type") == "fsm" or e.get("data", {}).get("isFsm"):
            continue
        tgt_id = e.get("target", "")
        th     = e.get("targetHandle", "in")
        key    = (tgt_id, th)
        drivers.setdefault(key, []).append(e.get("source", ""))

    for (tgt_id, th), srcs in drivers.items():
        if len(srcs) > 1:
            issues.append(
                f"MULTIPLE DRIVERS: {tgt_id}[{th}] driven by: {srcs}"
            )

    return issues


def _ir_check_disconnected_outputs(nodes: list, edges: list) -> list[str]:
    """
    Check that every output handle that should be driven has at least one edge.
    Focuses on macro blocks whose outputs are critical.
    """
    issues      = []
    driven_srcs = {(e.get("source"), e.get("sourceHandle")) for e in edges}
    node_map    = {n["id"]: n for n in nodes}

    critical_outputs = {
        "macro_cfgcounter": ["tc"],
        "macro_fifo":       ["dout"],
    }

    for node in nodes:
        ntype = node.get("type", "")
        nid   = node.get("id", "")
        if ntype in critical_outputs:
            for handle in critical_outputs[ntype]:
                if (nid, handle) not in driven_srcs:
                    issues.append(
                        f"DISCONNECTED OUTPUT: {nid}[{handle}] has no outgoing edge"
                    )

    for node in nodes:
        if node.get("type") != "macro_shiftreg":
            continue
        nid     = node.get("id", "")
        sr_mode = node.get("data", {}).get("srMode", "PISO").upper()
        if sr_mode in ("PISO", "SISO"):
            if (nid, "sout") not in driven_srcs:
                issues.append(f"DISCONNECTED OUTPUT: {nid}[sout] has no outgoing edge")
        elif sr_mode in ("SIPO", "PIPO"):
            if (nid, "out") not in driven_srcs:
                issues.append(f"DISCONNECTED OUTPUT: {nid}[out] has no outgoing edge")

    return issues


def _ir_check_fsm_reachability(nodes: list, edges: list, hierarchy: dict) -> list[str]:
    """
    Check that every FSM state is reachable from the reset state.
    Uses BFS on FSM transition edges.
    """
    issues = []
    scs    = {sc["id"]: sc for sc in hierarchy.get("sub_circuits", [])}

    for sc in hierarchy.get("sub_circuits", []):
        if sc["pattern"] != "fsm":
            continue
        sc_id  = sc["id"]
        states = sc.get("fsm_states", [])
        if not states:
            continue

        reset_state = states[0]
        reset_node  = f"{sc_id}__{reset_state}"

        fsm_edges = [
            e for e in edges
            if e.get("source", "").startswith(f"{sc_id}__")
            and (e.get("type") == "fsm" or e.get("data", {}).get("isFsm"))
        ]
        adj: dict[str, set] = {}
        for e in fsm_edges:
            src = e["source"]
            tgt = e["target"]
            adj.setdefault(src, set()).add(tgt)

        visited = {reset_node}
        queue   = [reset_node]
        while queue:
            cur = queue.pop(0)
            for nxt in adj.get(cur, set()):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)

        for state in states:
            node_id = f"{sc_id}__{state}"
            if node_id not in visited:
                issues.append(
                    f"UNREACHABLE FSM STATE: {sc_id}.{state} "
                    f"not reachable from reset state {reset_state}"
                )

    return issues


def _ir_check_fsm_completeness(nodes: list, edges: list, hierarchy: dict) -> list[str]:
    """
    Check that every FSM state has at least one outgoing transition.
    States with no outgoing edge are dead ends (FSM gets stuck).
    """
    issues    = []
    node_srcs = {e.get("source") for e in edges
                 if e.get("type") == "fsm" or e.get("data", {}).get("isFsm")}

    for sc in hierarchy.get("sub_circuits", []):
        if sc["pattern"] != "fsm":
            continue
        sc_id  = sc["id"]
        states = sc.get("fsm_states", [])
        for state in states:
            node_id = f"{sc_id}__{state}"
            if node_id not in node_srcs:
                issues.append(
                    f"DEAD END FSM STATE: {sc_id}.{state} has no outgoing transition"
                )

    return issues


_CONTROL_SIGNALS = {
    "en", "load", "wr_en", "rd_en", "shift_en", "we", "valid",
    "start", "done", "tc", "full", "empty", "a_empty", "cs_n",
    "sclk", "cnt_en", "btn_out", "tx_bit", "not_empty",
}


_CLOCK_SIGNALS = {"clk", "rst", "clock", "reset"}


def _sem_classify_signal(name: str, width: str) -> str:
    """
    Classify a signal into clock | control | data domain.
    """
    n = name.lower().strip()
    if n in _CLOCK_SIGNALS or "clk" in n or "rst" in n:
        return "clock"
    if n in _CONTROL_SIGNALS or width == "1":
        return "control"
    return "data"


def _sem_annotate_nodes(nodes: list) -> list[dict]:
    """
    Add semantic metadata to every node.
    Modifies nodes in-place and returns them.
    """
    for node in nodes:
        ntype  = node.get("type", "")
        data   = node.get("data", {})
        name   = str(data.get("name", "")).lower()
        width  = str(data.get("width", "8"))
        sc     = data.get("subCircuit", "")

        if ntype in ("input", "output", "const"):
            domain = _sem_classify_signal(name, width)
        elif ntype == "fsm_state":
            domain = "control"
        elif ntype in ("macro_cfgcounter", "macro_counter"):
            domain = "control"  # counters generate control ticks
        elif ntype == "macro_fifo":
            domain = "data"
        elif ntype == "macro_shiftreg":
            domain = "data"
        elif ntype == "comb":
            op = str(data.get("op", "")).lower()
            domain = "control" if op in ("not", "and", "or", "xor", "eq", "neq", "lt", "lte", "gt", "gte") else "data"
        else:
            domain = "data"


        if ntype == "input":
            signal_type = "port"
        elif ntype == "output":
            signal_type = "port"
        elif ntype == "const":
            signal_type = "wire"
        elif ntype == "reg":
            signal_type = "reg"
        elif ntype == "fsm_state":
            signal_type = "reg"
        else:
            signal_type = "wire"


        node["data"]["sem_domain"]      = domain
        node["data"]["sem_owner"]       = sc or "top"
        node["data"]["sem_signal_type"] = signal_type

    return nodes


def _sem_annotate_edges(edges: list, nodes: list) -> list[dict]:
    """
    Add semantic metadata to every edge based on source node domain.
    """
    node_map = {n["id"]: n for n in nodes}

    for edge in edges:
        src_node = node_map.get(edge.get("source", ""), {})
        src_data = src_node.get("data", {})
        sh       = edge.get("sourceHandle", "out")

        src_domain = src_data.get("sem_domain", "data")
        if sh in _CONTROL_SIGNALS or sh == "tc":
            edge_domain = "control"
        elif sh in _CLOCK_SIGNALS:
            edge_domain = "clock"
        else:
            edge_domain = src_domain

        edge["data"] = edge.get("data") or {}
        edge["data"]["sem_domain"] = edge_domain
        edge["data"]["sem_owner"]  = src_data.get("sem_owner", "top")

    return edges


def _ir_annotate_and_validate(
    nodes: list, edges: list, hierarchy: dict | None = None
) -> tuple[list, list, list[str]]:
    """
    Combined pass: annotate nodes/edges with semantic metadata,
    then run all validation checks.
    Returns (annotated_nodes, annotated_edges, issues).
    """

    nodes = _sem_annotate_nodes(nodes)
    edges = _sem_annotate_edges(edges, nodes)


    issues = _ir_validate(nodes, edges, hierarchy)

    return nodes, edges, issues

__all__ = [_n for _n in dir() if not _n.startswith("__")]