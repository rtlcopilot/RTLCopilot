"""
emit_fsm.py
Generates inline Moore FSM Verilog logic to be embedded directly in top.v.

Industry practice: FSM always/case blocks live inside the module that uses
them — not in a separate sub-module. This avoids port-passing for condition
signals and eliminates the duplicate clk/rst problem.

Returns a list of Verilog lines (no module wrapper, no endmodule).
emit_verilog.py embeds these directly into top.v.
"""
import math


def emit_fsm_inline(state_nodes: list, name_map: dict,
                    edges: list, all_output_signals: list,
                    gated_signals: dict = None,
                    fsm_prefix: str = "") -> list:
    """
    Returns a list of Verilog lines to embed inline in top.v.

    state_nodes        : list of FSM state node dicts
    name_map           : { node_id -> safe_signal_name }
    edges              : all canvas edges (for transition conditions)
    all_output_signals : list of unique output signal names across all states
    gated_signals      : { signal_name -> gate_signal } for baud-gated outputs
    fsm_prefix         : prefix for localparams to avoid collisions when
                         multiple FSMs are in the same module.
                         e.g. "TXFSM_" → TXFSM_IDLE, TXFSM_START_BIT, ...
                         Defaults to "" (no prefix) for single-FSM modules.
    """
    num_states  = len(state_nodes)
    state_bits  = max(1, math.ceil(math.log2(max(num_states, 2))))
    reset_raw   = name_map[state_nodes[0]["id"]]
    reset_state = f"{fsm_prefix}{reset_raw}" if fsm_prefix else reset_raw

    L = []
    L.append(f"    // FSM: {num_states} states")

    for i, sn in enumerate(state_nodes):
        raw_name    = name_map[sn["id"]]
        param_name  = f"{fsm_prefix}{raw_name}" if fsm_prefix else raw_name
        L.append(f"    localparam {param_name} = {state_bits}'d{i};")
    L.append(f"    reg [{state_bits}-1:0] current_state, next_state;")

    gated_signals = gated_signals or {}
    for sig in all_output_signals:
        reg_name = f"{sig}_raw" if sig in gated_signals else sig
        L.append(f"    reg {reg_name};")

    L.append("")

    L.append(f"    // State register")
    L.append(f"    always @(posedge clk or posedge rst) begin")
    L.append(f"        if (rst) current_state <= {reset_state};")
    L.append(f"        else     current_state <= next_state;")
    L.append(f"    end")
    L.append("")


    L.append(f"    // Next-state logic")
    L.append(f"    always @(*) begin")
    L.append(f"        next_state = current_state;")
    L.append(f"        case (current_state)")
    for sn in state_nodes:
        raw_sname = name_map[sn["id"]]
        sname      = f"{fsm_prefix}{raw_sname}" if fsm_prefix else raw_sname
        transitions = [e for e in edges if e.get("src") == sn["id"]]
        L.append(f"            {sname}: begin")

        has_priority = any(e.get("priority") is not None for e in transitions)
        transitions = sorted(
            transitions,
            key=lambda e: (
                (1 if (e.get("condition") or "1").strip() == "1" else 0),
                e.get("priority") if e.get("priority") is not None else 99
            )
        )

        first = True
        for e in transitions:
            tgt_id   = e.get("dst", "")
            tgt_node = next((n for n in state_nodes if n["id"] == tgt_id), None)
            if tgt_node:
                cond     = (e.get("condition", "1") or "1").strip()

                if "." in cond and not any(op in cond for op in ["==", "!=", "<=", ">="]):
                    cond = cond.split(".")[0].strip()
                raw_tgt = name_map[tgt_id]
                tgt_name = f"{fsm_prefix}{raw_tgt}" if fsm_prefix else raw_tgt
                if cond == "1":

                    if not first:
                        L.append(f"                else next_state = {tgt_name};")
                    else:
                        L.append(f"                next_state = {tgt_name};")
                else:

                    if first:
                        L.append(f"                if ({cond}) next_state = {tgt_name};")
                        first = False
                    else:
                        L.append(f"                else if ({cond}) next_state = {tgt_name};")
        L.append(f"            end")
    L.append(f"        endcase")
    L.append(f"    end")
    L.append("")


    if all_output_signals:
        L.append(f"    // Moore output logic")
        L.append(f"    always @(*) begin")
        for sig in all_output_signals:
            reg_name = f"{sig}_raw" if sig in gated_signals else sig
            L.append(f"        {reg_name} = 1'b0;")
        L.append(f"        case (current_state)")
        for sn in state_nodes:
            outs  = sn.get("fsmOutputs", [])
            valid = [
                (r.get("signal", "").strip(), r.get("value", "0").strip())
                for r in outs if r.get("signal", "").strip()
            ]
            if valid:
                raw_moore = name_map[sn["id"]]
                moore_name = f"{fsm_prefix}{raw_moore}" if fsm_prefix else raw_moore
                L.append(f"            {moore_name}: begin")
                for sig, val in valid:
                    reg_name = f"{sig}_raw" if sig in gated_signals else sig
                    L.append(f"                {reg_name} = {val};")
                L.append(f"            end")
        L.append(f"        endcase")
        L.append(f"    end")

    L.append("")
    return L


def emit_fsm(inst_name, state_nodes, name_map, edges, all_output_signals):
    """Shim — not used by emit_verilog.py anymore."""
    lines = emit_fsm_inline(state_nodes, name_map, edges, all_output_signals)
    return f"fsm_{inst_name}", "\n".join(lines)


def fsm_instantiation(inst_name, all_output_signals):
    """Shim — returns empty string, no instantiation needed."""
    return ""