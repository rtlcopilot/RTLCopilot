

from __future__ import annotations

import json
import re
import math
import subprocess
import traceback as _tb
from pathlib import Path as _Path
from collections import defaultdict
from known_circuits import (
    _KNOWN_HIERARCHIES as _KC_HIERARCHIES,
    _FSM_TRANSITION_TABLES as _KC_FSM_TABLES,
    _CIRCUIT_KEYWORDS as _KC_KEYWORDS,
    get_circuit_key as _kc_classify,
    get_circuit_key,
)
from net_ir import build_net_ir, validate_net_ir, get_driver_wire
import port_contract as _pc
from core import *
from prompts import *
from ir_checks import *
from verilog_tools import _iverilog_compile_check, _llm_fix_verilog
import state
from state import _FSM_TRANSITION_TABLES


_KNOWN_HIERARCHIES = {
    "uart_tx": {
        "description": "UART Transmitter",
        "sub_circuits": [
            {
                "id":      "baud_counter",
                "name":    "baud_counter",
                "pattern": "macro_cfgcounter",
                "role":    "Generates baud rate timing — pulses tc every N clocks",
                "data": {
                    "width":    "8",
                    "countDir": 1,
                },
                "exports": [
                    {"signal": "tc", "handle": "tc", "width": "1"},
                ],
                "imports": [
                    {"signal": "en",       "handle": "en",       "width": "1", "from": "external"},
                    {"signal": "load",     "handle": "load",     "width": "1", "from": "external"},
                    {"signal": "load_val", "handle": "load_val", "width": "8", "from": "external"},
                ],
                "position": {"x": 100, "y": 100},
            },
            {
                "id":      "data_fifo",
                "name":    "data_fifo",
                "pattern": "macro_fifo",
                "role":    "Buffers data bytes waiting to be transmitted",
                "data": {
                    "width":     "8",
                    "fifoDepth": "16",
                    "aeThresh":  "4",
                },
                "exports": [
                    {"signal": "dout",  "handle": "dout",  "width": "8"},
                    {"signal": "empty", "handle": "empty", "width": "1"},
                ],
                "imports": [
                    {"signal": "wr_en", "handle": "wr_en", "width": "1", "from": "external"},
                    {"signal": "din",   "handle": "din",   "width": "8", "from": "external"},
                    {"signal": "rd_en", "handle": "rd_en", "width": "1", "from": "tx_fsm",
                     "src_signal": "rd_en"},
                ],
                "position": {"x": 100, "y": 350},
            },
            {
                "id":      "tx_fsm",
                "name":    "tx_fsm",
                "pattern": "fsm",
                "role":    "Controls UART TX protocol — sequences start, data, stop bits",
                "fsm_states": ["idle", "start_bit", "data_bits", "stop_bit"],
                "fsm_outputs": ["shift_en", "load", "rd_en", "tx_bit"],
                "imports": [
                    {"signal": "tc",    "handle": "tc",    "width": "1", "from": "baud_counter", "src_handle": "tc"},
                    {"signal": "empty", "handle": "empty", "width": "1", "from": "data_fifo",    "src_handle": "empty"},
                ],
                "exports": [
                    {"signal": "shift_en", "width": "1"},
                    {"signal": "load",     "width": "1"},
                    {"signal": "rd_en",    "width": "1"},
                    {"signal": "tx_bit",   "width": "1"},
                ],
                "position": {"x": 600, "y": 200},
            },
            {
                "id":      "bit_counter",
                "name":    "bit_counter",
                "pattern": "macro_cfgcounter",
                "role":    "Counts 8 baud ticks to track how many data bits have been sent",
                "data": {
                    "width":    "3",
                    "countDir": 1,
                },
                "exports": [
                    {"signal": "bit_tc", "handle": "tc", "width": "1"},
                ],
                "imports": [
                    {"signal": "en",       "handle": "en",       "width": "1", "from": "tx_fsm",      "src_signal": "shift_en"},
                    {"signal": "load",     "handle": "load",     "width": "1", "from": "external"},
                    {"signal": "load_val", "handle": "load_val", "width": "3", "from": "external"},
                ],
                "position": {"x": 600, "y": 500},
            },
            {
                "id":      "shift_reg",
                "name":    "shift_reg",
                "pattern": "macro_shiftreg",
                "role":    "Serializes 8-bit data byte, shifts out LSB first (PISO mode)",
                "data": {
                    "width":    "8",
                    "srMode":   "PISO",
                    "shiftDir": "right",
                },
                "imports": [
                    {"signal": "din",  "handle": "din",  "width": "8", "from": "data_fifo",   "src_handle": "dout"},
                    {"signal": "en",   "handle": "en",   "width": "1", "from": "tx_fsm",      "src_signal": "shift_en"},
                    {"signal": "load", "handle": "load", "width": "1", "from": "tx_fsm",      "src_signal": "load"},
                ],
                "exports": [
                    {"signal": "sout", "handle": "sout", "width": "1"},
                ],
                "position": {"x": 1100, "y": 200},
            },
        ],
        "top_level_outputs": [
            {"name": "tx_out", "width": "1", "from": "shift_reg", "src_handle": "sout"},
        ],
        "top_level_inputs": [
            {"name": "wr_en", "width": "1", "to": "data_fifo", "dst_handle": "wr_en"},
            {"name": "din",   "width": "8", "to": "data_fifo", "dst_handle": "din"},
        ],
    },

    "spi_master": {
        "description": "SPI Master Controller",
        "sub_circuits": [
            {
                "id":      "spi_clk_div",
                "name":    "spi_clk_div",
                "pattern": "macro_cfgcounter",
                "role":    "Divides system clock to generate SPI clock",
                "data":    {"width": "8", "countDir": 1},
                "exports": [{"signal": "tc", "handle": "tc", "width": "1"}],
                "imports": [],
                "position": {"x": 100, "y": 100},
            },
            {
                "id":      "tx_data_reg",
                "name":    "tx_data_reg",
                "pattern": "macro_shiftreg",
                "role":    "Holds and shifts out MOSI data",
                "data":    {"width": "8"},
                "imports": [
                    {"signal": "din",  "handle": "din",  "width": "8", "from": "external"},
                    {"signal": "load", "handle": "load", "width": "1", "from": "spi_fsm", "src_signal": "load"},
                    {"signal": "en",   "handle": "en",   "width": "1", "from": "spi_fsm", "src_signal": "shift_en"},
                ],
                "exports": [{"signal": "out", "handle": "out", "width": "8"}],
                "position": {"x": 100, "y": 350},
            },
            {
                "id":      "spi_fsm",
                "name":    "spi_fsm",
                "pattern": "fsm",
                "role":    "Controls SPI transaction — CS, SCLK, MOSI sequencing",
                "fsm_states":   ["idle", "cs_assert", "transfer", "cs_deassert"],
                "fsm_outputs":  ["cs_n", "sclk", "shift_en", "load", "done"],
                "imports": [
                    {"signal": "tc",    "handle": "tc",    "width": "1", "from": "spi_clk_div"},
                    {"signal": "start", "handle": "start", "width": "1", "from": "external"},
                ],
                "exports": [
                    {"signal": "cs_n",     "width": "1"},
                    {"signal": "sclk",     "width": "1"},
                    {"signal": "shift_en", "width": "1"},
                    {"signal": "load",     "width": "1"},
                    {"signal": "done",     "width": "1"},
                ],
                "position": {"x": 600, "y": 200},
            },
        ],
        "top_level_outputs": [
            {"name": "mosi",  "width": "1", "from": "tx_data_reg", "src_handle": "out"},
            {"name": "cs_n",  "width": "1", "from": "spi_fsm",     "src_signal": "cs_n"},
            {"name": "sclk",  "width": "1", "from": "spi_fsm",     "src_signal": "sclk"},
            {"name": "done",  "width": "1", "from": "spi_fsm",     "src_signal": "done"},
        ],
        "top_level_inputs": [
            {"name": "din",   "width": "8", "to": "tx_data_reg", "dst_handle": "din"},
            {"name": "start", "width": "1", "to": "spi_fsm",     "dst_handle": "start"},
            {"name": "miso",  "width": "1", "to": None},
        ],
    },

    "pwm": {
        "description": "PWM Generator",
        "sub_circuits": [
            {
                "id":      "period_counter",
                "name":    "period_counter",
                "pattern": "macro_cfgcounter",
                "role":    "Counts the full PWM period",
                "data":    {"width": "8", "countDir": 1},
                "exports": [{"signal": "count", "handle": "count", "width": "8"},
                            {"signal": "tc",    "handle": "tc",    "width": "1"}],
                "imports": [],
                "position": {"x": 100, "y": 100},
            },
            {
                "id":      "duty_compare",
                "name":    "duty_compare",
                "pattern": "comb",
                "role":    "Compares counter to duty cycle threshold",
                "data":    {"op": "lt", "width": "1"},
                "imports": [
                    {"signal": "in0", "handle": "in0", "width": "8", "from": "period_counter", "src_handle": "count"},
                    {"signal": "in1", "handle": "in1", "width": "8", "from": "external",       "src_name":  "duty"},
                ],
                "exports": [{"signal": "out", "handle": "out", "width": "1"}],
                "position": {"x": 500, "y": 100},
            },
        ],
        "top_level_outputs": [
            {"name": "pwm_out", "width": "1", "from": "duty_compare", "src_handle": "out"},
        ],
        "top_level_inputs": [
            {"name": "duty", "width": "8", "to": "duty_compare", "dst_handle": "in1"},
        ],
    },

    "debouncer": {
        "description": "Button Debouncer",
        "sub_circuits": [
            {
                "id":      "sample_counter",
                "name":    "sample_counter",
                "pattern": "macro_cfgcounter",
                "role":    "Counts stable samples before accepting button state",
                "data":    {"width": "16", "countDir": 1},
                "exports": [{"signal": "tc", "handle": "tc", "width": "1"}],
                "imports": [],
                "position": {"x": 100, "y": 100},
            },
            {
                "id":      "debounce_fsm",
                "name":    "debounce_fsm",
                "pattern": "fsm",
                "role":    "Waits for stable input before registering button press",
                "fsm_states":  ["idle", "counting", "stable"],
                "fsm_outputs": ["btn_out", "cnt_en"],
                "imports": [
                    {"signal": "tc",      "handle": "tc",      "width": "1", "from": "sample_counter"},
                    {"signal": "btn_raw", "handle": "btn_raw", "width": "1", "from": "external"},
                ],
                "exports": [
                    {"signal": "btn_out", "width": "1"},
                    {"signal": "cnt_en",  "width": "1"},
                ],
                "position": {"x": 500, "y": 100},
            },
        ],
        "top_level_outputs": [
            {"name": "btn_out", "width": "1", "from": "debounce_fsm", "src_signal": "btn_out"},
        ],
        "top_level_inputs": [
            {"name": "btn_raw", "width": "1", "to": "debounce_fsm", "dst_handle": "btn_raw"},
        ],
    },
}

_CIRCUIT_KEYWORDS = {
    "uart_tx":   ["uart tx", "uart transmit", "uart transmitter"],
    "spi_master":["spi master", "spi controller", "spi"],
    "pwm":       ["pwm", "pulse width", "pulse-width"],
    "debouncer": ["debounce", "debouncer", "button debounce"],
}


def _v2_classify(prompt: str) -> tuple[str | None, dict | None]:
    """
    Returns (circuit_key, hierarchy_dict) if known, else (None, None).
    Checks both the inline _KNOWN_HIERARCHIES and the expanded known_circuits library.
    """
    key, hier = _kc_classify(prompt)
    if key:
        return key, hier
    p = prompt.lower().strip()
    for key, keywords in _CIRCUIT_KEYWORDS.items():
        if any(kw in p for kw in keywords):
            return key, _KNOWN_HIERARCHIES[key]
    return None, None


def _v2_make_node(sc_id: str, sc: dict, x_off: float = 0, y_off: float = 0) -> dict:
    """
    Build a canvas node dict from a sub-circuit definition.
    For macro types, creates the macro node directly.
    For fsm, creates a placeholder — FSM nodes are generated separately.
    For comb, creates a comb node.
    """
    pattern = sc["pattern"]
    pos_x   = sc.get("position", {}).get("x", 100) + x_off
    pos_y   = sc.get("position", {}).get("y", 100) + y_off
    data    = sc.get("data", {})
    name    = sc.get("name", sc_id)

    base = {
        "id":       sc_id,
        "position": {"x": pos_x, "y": pos_y},
        "data": {
            "name":        name,
            "width":       data.get("width", "8"),
            "op":          data.get("op", "add"),
            "value":       data.get("value", "0"),
            "muxSize":     data.get("muxSize", "2"),
            "bitIndex":    data.get("bitIndex", "0"),
            "fifoDepth":   data.get("fifoDepth", "16"),
            "aeThresh":    data.get("aeThresh", "4"),
            "lsbPriority": int(data.get("lsbPriority", 0)),
            "edgeType":    int(data.get("edgeType", 0)),
            "addrWidth":   data.get("addrWidth", "6"),
            "countDir":    int(data.get("countDir", 1)),
            "terminalValue": data.get("terminalValue", None),
            "fsmOutputs":  [],
            "subCircuit":  sc_id,
        },
    }

    if pattern == "macro_cfgcounter":
        base["type"] = "macro_cfgcounter"
    elif pattern == "macro_fifo":
        base["type"] = "macro_fifo"
    elif pattern == "macro_cordic":
        base["type"] = "macro_cordic"
    elif pattern == "macro_shiftreg":
        base["type"] = "macro_shiftreg"
        base["data"]["srMode"]   = data.get("srMode",   "PISO")
        base["data"]["shiftDir"] = data.get("shiftDir", "right")
    elif pattern == "comb":
        base["type"] = "comb"
        _cop = sc.get("comb_op") or data.get("comb_op") or data.get("op", "add")
        base["op"]         = _cop
        base["data"]["op"] = _cop
        try:
            _dw = max(1, int(str(data.get("width", "8")).strip()))
        except (TypeError, ValueError):
            _dw = 8
        # A comb node's width is its OPERAND width. Overwriting it with the
        # output width (1 for eq/lt/...) made the IR checker and canvas DRC
        # resolve the INPUTS to 1 bit too — which is what produced
        # "result_reg[q](8-bit) -> zero_det[in0](1-bit)". The emitter derives
        # the output wire width from the op independently.
        base["width"]         = str(_dw)
        base["data"]["width"] = str(_dw)
    elif pattern == "mux":
        # Previously fell through to the `else` branch and became a comb node,
        # which silently dropped the select logic. muxSize drives both the data
        # handle count and the number of 1-bit sel handles.
        base["type"] = "mux"
        base["data"]["muxSize"] = str(data.get("muxSize", "2"))
        base["width"]         = str(data.get("width", "8"))
        base["data"]["width"] = str(data.get("width", "8"))
    elif pattern == "reg":
        base["type"] = "reg"
    elif pattern == "splitter":
        base["type"] = "splitter"
        base["data"]["bitIndex"] = data.get("bitIndex", "0")
    elif pattern == "fsm":
        base["type"] = "fsm_state"  
        base["data"]["fsmOutputs"] = [
            {"signal": sig, "value": "0"}
            for sig in sc.get("fsm_outputs", [])
        ]
    else:
        base["type"] = "comb"

    return base


def _v2_build_fsm_nodes(sc_id: str, sc: dict, schema: dict,
                         x_off: float = 0, y_off: float = 0,
                         output_logic_signals: set = None) -> list[dict]:
    """
    Build FSM state nodes + dedicated output port nodes.

    FSM outputs are behavioral (Moore assignments), not physical per-state outputs.
    We create:
      - One fsm_state node per state (internal behavior)
      - One output node per FSM export signal (structural port)
    Cross-boundary wiring uses the output nodes, not state nodes directly.

    output_logic_signals: set of signal names already covered by output_logic
      entries. These are driven by a state_mux assign in emit_verilog, so they
      must be stripped from fsmOutputs — otherwise they generate a dead reg
      that nobody reads.
    """
    config       = schema.get("config", {})
    states       = config.get("states", sc.get("fsm_states", []))
    outputs_map  = config.get("outputs_per_state", {})
    fsm_outputs  = config.get("fsm_outputs", sc.get("fsm_outputs", []))
    base_x       = sc.get("position", {}).get("x", 600) + x_off
    base_y       = sc.get("position", {}).get("y", 200) + y_off

    if output_logic_signals:
        fsm_outputs = [s for s in fsm_outputs if s not in output_logic_signals]

    nodes = []

    for i, state in enumerate(states):
        state_outputs = outputs_map.get(state, {})
        fsm_out_list  = [
            {"signal": sig, "value": state_outputs.get(sig, "0")}
            for sig in fsm_outputs
        ]
        nodes.append({
            "id":       f"{sc_id}__{state}",
            "type":     "fsm_state",
            "position": {"x": base_x + i * 300, "y": base_y},
            "data": {
                "name":       state,
                "width":      "1",
                "fsmOutputs": fsm_out_list,
                "subCircuit": sc_id,
            },
        })

    fsm_edges_out = []
    first_state_id = f"{sc_id}__{states[0]}" if states else None

    for j, sig in enumerate(fsm_outputs):
        out_node_id = f"{sc_id}__out_{sig}"
        nodes.append({
            "id":       out_node_id,
            "type":     "comb",
            "position": {"x": base_x + len(states) * 300 + 100, "y": base_y + j * 100},
            "data": {
                "name":        sig,
                "op":          "buf",
                "width":       "1",
                "subCircuit":  sc_id,
                "isFsmOutput": True,
            },
        })

        if first_state_id:
            fsm_edges_out.append({
                "id":           f"fsm_out_{sc_id}_{sig}",
                "type":         "default",
                "source":       first_state_id,
                "sourceHandle": sig,
                "target":       out_node_id,
                "targetHandle": "in0",
                "animated":     False,
                "data":         {"isFsmOutput": True},
            })

    return nodes, fsm_edges_out


def _v2_build_fsm_edges(sc_id: str, sc: dict, schema: dict) -> list[dict]:
    """
    Build FSM transition edges from schema transitions.

    Tautological self-loops are pruned: if a state has a self-loop whose
    condition is the logical complement (~X) of another outgoing transition
    (X), the self-loop adds no information — the FSM stays implicitly when
    no other condition fires. Keeping it generates a redundant else-if branch.
    """
    config      = schema.get("config", {})
    transitions = config.get("transitions", [])

    from_map: dict = {}
    for t in transitions:
        from_map.setdefault(t.get("from", ""), []).append(t)

    pruned = set()
    for state, ts in from_map.items():

        outgoing_priorities = {
            t["priority"] for t in ts
            if t.get("to") != state and "priority" in t
        }
        for t in ts:
            if t.get("to") != state:
                continue  
            if "priority" not in t:
                continue  
            self_priority = t["priority"]
            
            if any(p < self_priority for p in outgoing_priorities):
                pruned.add(id(t))

    edges = []
    for i, t in enumerate(transitions):
        if id(t) in pruned:
            continue
        from_state = t.get("from", "")
        to_state   = t.get("to", "")
        condition  = t.get("condition", "1")
        edge = {
            "id":           f"fsm_e_{sc_id}_{i}",
            "type":         "fsm",
            "source":       f"{sc_id}__{from_state}",
            "sourceHandle": "out",
            "target":       f"{sc_id}__{to_state}",
            "targetHandle": "in",
            "animated":     False,
            "data": {
                "condition":  condition,
                "isFsm":      True,
                "isEditing":  False,
            },
        }

        if "priority" in t:
            edge["priority"] = t["priority"]
            edge["src"]      = f"{sc_id}__{from_state}"
        edges.append(edge)
    return edges


def _v2_build_cross_edges(hierarchy: dict, sc_node_map: dict) -> list[dict]:
    """
    Build cross-boundary edges from the known hierarchy definition.
    sc_node_map: {sc_id -> primary_node_id} for non-FSM blocks
                 {sc_id -> {signal -> node_id}} for FSM blocks
    """
    edges   = []
    edge_id = 0
    scs     = {sc["id"]: sc for sc in hierarchy["sub_circuits"]}

    for sc in hierarchy["sub_circuits"]:
        sc_id = sc["id"]
        for imp in sc.get("imports", []):
            if imp.get("from") == "external":
                continue

            src_sc_id  = imp.get("from", "")

            src_signal = imp.get("src_signal", "")
            if not src_signal:
                raw_sig = imp.get("signal", "")

                if raw_sig.startswith(src_sc_id + "_"):
                    src_signal = raw_sig[len(src_sc_id) + 1:]
                else:
                    src_signal = raw_sig
            src_handle = imp.get("src_handle", "")
            dst_handle = imp.get("handle", "in")

            if src_sc_id not in scs:
                continue

            src_sc      = scs[src_sc_id]
            src_pattern = src_sc["pattern"]


            if src_pattern == "fsm":

                sig_name = src_signal or src_handle

                if not sig_name or sig_name.startswith("<"):
                    print(f"[V2] SKIP cross-edge: FSM {src_sc_id} has empty/placeholder sig_name for import {imp.get('signal', '?')}", flush=True)
                    continue
                
                _fsm_exports = {e.get("handle"): e.get("signal", e.get("handle"))
                                for e in src_sc.get("exports", [])}
                if sig_name in _fsm_exports and sig_name != _fsm_exports[sig_name]:
                    sig_name = _fsm_exports[sig_name]
                    print(f"[V2] P3: resolved bare sig_name to '{sig_name}' via FSM exports", flush=True)
                src_node_id       = f"{src_sc_id}__out_{sig_name}"
                actual_src_handle = "out"  
            elif src_pattern == "macro_fifo":
                src_node_id       = src_sc_id
                actual_src_handle = src_handle or "dout"
            elif src_pattern == "macro_cfgcounter":
                src_node_id       = src_sc_id
                actual_src_handle = src_handle or "tc"
            else:
                src_node_id       = src_sc_id
                actual_src_handle = src_handle or "out"


            tgt_sc      = scs.get(sc_id, {})
            tgt_pattern = tgt_sc.get("pattern", "")
            if tgt_pattern == "fsm":

                tgt_node_id    = f"{sc_id}__{imp['signal']}_input"
                actual_dst_handle = "in"
            else:
                tgt_node_id    = sc_id
                actual_dst_handle = dst_handle

            edges.append({
                "id":           f"cross_{edge_id}",
                "source":       src_node_id,
                "sourceHandle": actual_src_handle,
                "target":       tgt_node_id,
                "targetHandle": actual_dst_handle,
                "animated":     False,
            })
            edge_id += 1


    for out in hierarchy.get("top_level_outputs", []):
        src_sc_id  = out.get("from", "")

        src_signal = out.get("src_signal", "") or out.get("src_handle", "")
        out_name   = out.get("name", "out")

        src_sc = scs.get(src_sc_id, {})
        src_pat = src_sc.get("pattern", "")

        _tlo_norm = {
            "macro_fifo":       {"out": "dout", "": "dout"},
            "macro_cfgcounter": {"out": "tc", "": "tc",
                                 "terminal_count": "tc"},
            "macro_shiftreg":   {"out": "q", "": "q"},
        }
        if src_pat in _tlo_norm and src_signal in _tlo_norm[src_pat]:
            old_sig = src_signal
            src_signal = _tlo_norm[src_pat][src_signal]
            if old_sig != src_signal:
                print(f"[V2] TLO normalize: {src_sc_id}[{old_sig}] → [{src_signal}]", flush=True)

        if src_pat == "fsm":
            sig_name = src_signal

            if not sig_name or sig_name.startswith("<"):
                print(f"[V2] SKIP tlo edge: FSM {src_sc_id} empty sig_name for output {out_name}", flush=True)
                continue
            src_node_id       = f"{src_sc_id}__out_{sig_name}"
            actual_src_handle = "out"
        else:
            src_node_id       = src_sc_id
            actual_src_handle = src_signal or "out"

        out_node_id = f"port_out_{out_name}"
        edges.append({
            "id":           f"out_{edge_id}",
            "source":       src_node_id,
            "sourceHandle": actual_src_handle,
            "target":       out_node_id,
            "targetHandle": "in",
            "animated":     False,
        })
        edge_id += 1

    for inp in hierarchy.get("top_level_inputs", []):
        tgt_sc_id  = inp.get("to")
        dst_handle = inp.get("dst_handle", "in")
        inp_name   = inp.get("name", "")
        if not tgt_sc_id:
            continue
        src_node_id = f"port_in_{inp_name}"
        tgt_sc = scs.get(tgt_sc_id, {})
        if tgt_sc.get("pattern") == "fsm":
            tgt_node_id = f"{tgt_sc_id}__{inp_name}_input"
        else:
            tgt_node_id = tgt_sc_id
        edges.append({
            "id":           f"inp_{edge_id}",
            "source":       src_node_id,
            "sourceHandle": "out",
            "target":       tgt_node_id,
            "targetHandle": dst_handle,
            "animated":     False,
        })
        edge_id += 1

    return edges


def _v2_build_io_nodes(hierarchy: dict) -> list[dict]:
    """
    Build top-level input and output nodes from hierarchy definition.
    Uses canonical net naming: {signal_name} for ports.
    """
    nodes  = []
    inp_y  = 100
    out_y  = 100
    # top_level_inputs is a list of ROUTES, so one port can appear several
    # times (an ALU's `a` feeds eight operation units). Build one node per
    # unique name — duplicates would collide on node id.
    _seen_inputs = set()
    for inp in hierarchy.get("top_level_inputs", []):
        if inp["name"] in _seen_inputs:
            continue
        _seen_inputs.add(inp["name"])
        nodes.append({
            "id":       f"port_in_{inp['name']}",
            "type":     "input",
            "position": {"x": -350, "y": inp_y},
            "data": {
                "name":  inp["name"],
                "width": inp.get("width", "8"),
                "value": "0",
            },
        })
        inp_y += 150
    for out in hierarchy.get("top_level_outputs", []):
        nodes.append({
            "id":       f"port_out_{out['name']}",
            "type":     "output",
            "position": {"x": 1700, "y": out_y},
            "data": {
                "name":  out["name"],
                "width": out.get("width", "1"),
            },
        })
        out_y += 150
    return nodes


async def _v2_generate_fsm(sc_id: str, sc: dict,
                            output_logic_signals: set = None) -> tuple[list, list]:
    """
    Generate FSM nodes and edges.
    For known FSMs: uses deterministic transition table — zero LLM.
    For unknown FSMs: falls back to LLM schema generation.
    Returns (fsm_nodes, fsm_edges).

    output_logic_signals: set of signal names covered by output_logic entries.
      These are stripped from fsmOutputs so emit_fsm doesn't generate dead regs.
    """
    # Check both inline and expanded FSM tables
    _combined_tables = {**_FSM_TRANSITION_TABLES, **_KC_FSM_TABLES}
    if sc_id in _combined_tables:
        print(f"  [{sc_id}] Using deterministic FSM transition table", flush=True)
        table  = _combined_tables[sc_id]
        schema = {
            "config": {
                "states":            table["states"],
                "reset_state":       table["reset_state"],
                "fsm_outputs":       table["fsm_outputs"],
                "transitions":       table["transitions"],
                "outputs_per_state": table["outputs_per_state"],
            }
        }
        fsm_nodes, fsm_output_edges = _v2_build_fsm_nodes(sc_id, sc, schema,
                                         output_logic_signals=output_logic_signals)
        fsm_edges = _v2_build_fsm_edges(sc_id, sc, schema) + fsm_output_edges
        state_nodes  = [n for n in fsm_nodes if n["type"] == "fsm_state"]
        output_nodes = [n for n in fsm_nodes if n["type"] == "comb"
                        and n.get("data", {}).get("isFsmOutput")]
        print(f"  [{sc_id}] Deterministic FSM: {len(state_nodes)} states, "
              f"{len([e for e in fsm_edges if e.get('type')=='fsm'])} transitions, "
              f"{len(output_nodes)} output port nodes", flush=True)
        return fsm_nodes, fsm_edges

    print(f"  [{sc_id}] No transition table -- falling back to LLM schema", flush=True)
    return await _v2_generate_fsm_llm(sc_id, sc)


async def _v2_generate_fsm_llm(sc_id: str, sc: dict) -> tuple[list, list]:
    """LLM fallback for unknown FSMs."""

    fsm_states  = sc.get("fsm_states",  [])
    fsm_outputs = sc.get("fsm_outputs", [])
    imports     = sc.get("imports", [])

    cond_inputs = "\n".join(
        f"  - {imp['signal']} (1-bit condition signal)"
        for imp in imports
    )
    output_list = "\n".join(f"  - {sig} (1-bit Moore output)" for sig in fsm_outputs)
    states_str  = ", ".join(fsm_states)

    user_msg = f"""
FSM block: {sc.get('name', sc_id)}
Role: {sc.get('role', '')}

States: {states_str}
Reset state: {fsm_states[0] if fsm_states else 'idle'}

Condition inputs (create as input ports):
{cond_inputs}

Moore output signals (create as output ports AND declare in fsm_outputs config):
{output_list}

State transition rules:
- States go in sequence: {' -> '.join(fsm_states)} -> back to {fsm_states[0] if fsm_states else 'idle'}
- idle: wait for NOT empty (if 'empty' is an input), then transition to next state
- Each data/active state: transition on tc (terminal count) if tc is an input
- Last state transitions back to idle unconditionally or on tc

Output values per state:
- {fsm_states[0] if fsm_states else 'idle'} (reset): all outputs = 0
- Other states: set outputs to 1 as appropriate for that phase

Output the JSON schema now:
"""

    try:
        completion = _llm_client.chat.completions.create(
            model=_LLM_MODEL,
            messages=[
                {"role": "system", "content": _CUSTOM_BLOCK_SCHEMA_FSM},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=1500,
        )
        raw = completion.choices[0].message.content.strip()


        json_str = None
        if "```json" in raw:
            s = raw.find("```json") + 7
            e = raw.find("```", s)
            json_str = raw[s:e].strip()
        elif "{" in raw:
            depth, start, end = 0, raw.find("{"), -1
            for ci, ch in enumerate(raw[start:], start):
                if ch == "{":   depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0: end = ci; break
            if end != -1:
                json_str = raw[start:end+1]

        if not json_str:
            print(f"  [{sc_id}] FSM schema extraction failed", flush=True)
            return [], []

        schema = json.loads(json_str)
        fsm_nodes, fsm_output_edges = _v2_build_fsm_nodes(sc_id, sc, schema)
        fsm_edges = _v2_build_fsm_edges(sc_id, sc, schema) + fsm_output_edges

        print(f"  [{sc_id}] FSM generated: {len(fsm_nodes)} states, {len(fsm_edges)} transitions", flush=True)
        return fsm_nodes, fsm_edges

    except Exception:
        _tb.print_exc()
        return [], []


def _v2_build_signal_nodes(hierarchy: dict) -> tuple[list, list]:
    """
    Reads hierarchy["signal_list"] and creates comb nodes for any signal
    that has a "comb_op" field (e.g. not_bit_tc, not_empty).

    For each such signal it creates:
      - A comb node with the specified op
      - A placeholder const input node (so the FSM condition resolver finds it)
      - Edges: driver -> comb node -> placeholder const input

    This replaces all hardcoded per-circuit comb node creation.
    Returns (nodes_to_add, edges_to_add).
    """
    nodes = []
    edges = []
    seen  = set()

    for sig in hierarchy.get("signal_list", []):
        comb_op = sig.get("comb_op")
        if not comb_op:
            continue

        sig_name   = sig["name"]
        comb_input = sig.get("comb_input", "")
        width      = sig.get("width", "1")

        sc_id = None
        for sc in hierarchy.get("sub_circuits", []):
            if sc.get("pattern") == "fsm":
                sc_id = sc["id"]
                break
        sc_id = sc_id or "top"

        comb_node_id  = f"{sc_id}__{sig_name}"
        input_node_id = f"{sc_id}__{sig_name}_input"

        if comb_node_id in seen:
            continue
        seen.add(comb_node_id)

        nodes.append({
            "id":   comb_node_id,
            "type": "comb",
            "position": {"x": 750, "y": 500 + len(nodes) * 80},
            "data": {
                "name":       sig_name,
                "op":         comb_op,
                "width":      width,
                "subCircuit": sc_id,
            },
        })

        nodes.append({
            "id":   input_node_id,
            "type": "const",
            "position": {"x": 750, "y": 600 + len(nodes) * 80},
            "data": {
                "name":       sig_name,
                "width":      width,
                "value":      "0",
                "subCircuit": sc_id,
            },
        })


        sig_map = {s["name"]: s for s in hierarchy.get("signal_list", [])}
        comb_inputs_list = sig.get("comb_inputs", [])
        if not comb_inputs_list and comb_input:
            comb_inputs_list = [comb_input]

        for inp_idx, inp_name in enumerate(comb_inputs_list):
            inp_sig = sig_map.get(inp_name)
            if inp_sig:
                drv_node_id = inp_sig["driver"]
                drv_handle  = inp_sig.get("driver_handle", "out")
            else:
                drv_node_id = inp_name
                drv_handle  = "out"
            edges.append({
                "id":           f"{comb_node_id}_drv{inp_idx}",
                "source":       drv_node_id,
                "sourceHandle": drv_handle,
                "target":       comb_node_id,
                "targetHandle": f"in{inp_idx}",
                "animated":     False,
            })

        edges.append({
            "id":           f"{comb_node_id}_to_input",
            "source":       comb_node_id,
            "sourceHandle": "out",
            "target":       input_node_id,
            "targetHandle": "in",
            "animated":     False,
        })

    return nodes, edges


def _v2_build_output_logic(hierarchy: dict) -> tuple[list, list]:
    """
    Reads hierarchy["output_logic"] and instantiates the required structural
    nodes and edges for combinational output muxing.

    Currently supports type="state_mux" which generates a comb mux node
    driven by FSM current_state. The emitter sees this as a regular comb
    node with a special "__state_mux__" op that emit_verilog handles by
    emitting a ternary assign chain based on the overrides dict.

    Returns (nodes_to_add, edges_to_add).
    """
    print(f"[V2] output_logic entries: {json.dumps(hierarchy.get('output_logic', []))}", flush=True)
    nodes = []
    edges = []

    for i, ol in enumerate(hierarchy.get("output_logic", [])):
        out_name = ol.get("output", "")
        ol_type  = ol.get("type", "")

        if ol_type == "state_mux":

            node_id = "_output_mux" if i == 0 else f"_output_mux_{out_name}"
            nodes.append({
                "id":   node_id,
                "type": "comb",
                "position": {"x": 1500, "y": 100 + i * 150},
                "overrides":  ol.get("overrides", {}),   
                "default":    ol.get("default", "1'b1"),
                "data": {
                    "name":        out_name,
                    "op":          "__state_mux__",
                    "width":       ol.get("width", "1"),
                    "fsm":         ol.get("fsm", ""),
                    "default":     ol.get("default", "1'b0"),
                    "overrides":   ol.get("overrides", {}),
                    "subCircuit":  "top",
                    "isMux":       True,
                },
            })

            default_wire = ol.get("default", "")
            if default_wire and not default_wire.startswith("1'"):
                sigs = {s["name"]: s for s in hierarchy.get("signal_list", [])}
                sig  = sigs.get(default_wire)
                if sig:
                    src_node_id = sig["driver"]
                    src_handle  = sig.get("driver_handle", "out")
                else:
                    src_node_id = default_wire
                    src_handle  = "out"
                edges.append({
                    "id":           f"out_mux_{out_name}_default",
                    "source":       src_node_id,
                    "sourceHandle": src_handle,
                    "target":       node_id,
                    "targetHandle": "default",
                    "animated":     False,
                })

    return nodes, edges


async def _run_hierarchical_v2(prompt: str, current_user: str, byok: bool = False) -> dict:
    """
    Classifier entry point — looks up known hierarchy then delegates to
    _run_hierarchical_v2_from_hierarchy for all emission passes.
    """
    circuit_key, hierarchy = _v2_classify(prompt)

    if not circuit_key:
        return {
            "explanation": "Circuit not in known hierarchy library. Try a simpler prompt.",
            "nodes": [], "edges": [], "fallback": True,
        }

    return await _run_hierarchical_v2_from_hierarchy(circuit_key, hierarchy, prompt, current_user, byok=byok)


async def _run_hierarchical_v2_from_hierarchy(
    circuit_key: str, hierarchy: dict, prompt: str, current_user: str, byok: bool = False
) -> dict:
    """
    Core v2 emission pipeline — takes a hierarchy dict directly.
    Works for both known circuits (looked up from _KNOWN_HIERARCHIES)
    and LLM-generated hierarchies (RTL Brain unknown circuit path).
    All 8 build passes live here. Zero LLM involvement in Verilog gen.
    """
    print(f"[V2] Known circuit: {circuit_key} ({hierarchy['description']})", flush=True)

    all_nodes = []
    all_edges = []


    io_nodes = _v2_build_io_nodes(hierarchy)
    all_nodes.extend(io_nodes)
    print(f"[V2] IO nodes: {[n['id'] for n in io_nodes]}", flush=True)


    for sc in hierarchy["sub_circuits"]:
        sc_id   = sc["id"]
        pattern = sc["pattern"]
        print(f"\n[V2] Building [{sc_id}] pattern={pattern}", flush=True)

        if pattern == "fsm":

            _ol_covered = set()
            for sig in hierarchy.get("signal_list", []):
                if sig.get("driver") != sc_id:
                    continue
                consumers = sig.get("consumers", [])
                if consumers and all(c == "_output_mux" for c in consumers):
                    _ol_covered.add(sig.get("driver_handle", ""))
            fsm_nodes, fsm_edges = await _v2_generate_fsm(
                sc_id, sc, output_logic_signals=_ol_covered
            )
            all_nodes.extend(fsm_nodes)
            all_edges.extend(fsm_edges)

            for i, imp in enumerate(sc.get("imports", [])):
                if imp.get("from") == "external":
                    continue
                signal = imp["signal"]
                all_nodes.append({
                    "id":   f"{sc_id}__{signal}_input",
                    "type": "const",
                    "position": {
                        "x": sc.get("position", {}).get("x", 600) + i * 160,
                        "y": sc.get("position", {}).get("y", 200) - 220,
                    },
                    "data": {
                        "name":       signal,
                        "width":      imp.get("width", "1"),
                        "value":      "0",
                        "subCircuit": sc_id,
                    },
                })

        else:
            node = _v2_make_node(sc_id, sc)
            all_nodes.append(node)
            print(f"[V2] [{sc_id}] placed as {node['type']}", flush=True)


    signal_nodes, signal_edges = _v2_build_signal_nodes(hierarchy)
    all_nodes.extend(signal_nodes)
    all_edges.extend(signal_edges)
    if signal_nodes:
        print(f"[V2] Signal nodes: {[n['id'] for n in signal_nodes]}", flush=True)


    output_logic_nodes, output_logic_edges = _v2_build_output_logic(hierarchy)
    all_nodes.extend(output_logic_nodes)
    all_edges.extend(output_logic_edges)
    if output_logic_nodes:
        print(f"[V2] Output logic: {[n['id'] for n in output_logic_nodes]}", flush=True)


    print(f"\n[V2] Building cross-boundary edges...", flush=True)
    node_ids    = {n["id"] for n in all_nodes}
    cross_edges = _v2_build_cross_edges(hierarchy, {})


    placeholder_wire_map = {}

    all_edges_so_far = list(all_edges) + list(cross_edges)
    for e in all_edges_so_far:
        tgt_id = e.get("target", "")
        src_id = e.get("source", "")
        src_h  = e.get("sourceHandle", "")
        tgt_node = next((n for n in all_nodes if n["id"] == tgt_id), None)
        if not tgt_node or tgt_node.get("type") != "const":
            continue
        src_node = next((n for n in all_nodes if n["id"] == src_id), None)
        if not src_node:
            continue
        src_type = src_node.get("type", "")
        if src_type == "macro_cfgcounter":
            real_wire = f"{src_id}_tc" if src_h == "tc" else f"{src_id}_{src_h}"
        elif src_type == "macro_fifo":
            real_wire = f"{src_id}_{src_h}"
        elif src_type == "comb":

            real_wire = src_node.get("data", {}).get("name") or src_id
        else:
            real_wire = src_node.get("data", {}).get("name") or src_id
        placeholder_wire_map[tgt_id] = real_wire
        print(f"  [V2] wire map: {tgt_id} -> {real_wire}", flush=True)

    for e in all_edges:
        if e.get("data", {}).get("isFsm") or e.get("type") == "fsm":
            cond = e.get("data", {}).get("condition", "")
            if cond:

                matching_placeholder = next(
                    (nid for nid, wire in placeholder_wire_map.items()
                     if any(n["id"] == nid and n.get("data", {}).get("name", "") == cond
                            for n in all_nodes)),
                    None
                )
                if matching_placeholder:
                    e["data"]["condition"] = placeholder_wire_map[matching_placeholder]

    for e in cross_edges:
        if e["source"] in node_ids and e["target"] in node_ids:
            all_edges.append(e)
            print(f"[V2] WIRED: {e['source']}[{e['sourceHandle']}] -> {e['target']}[{e['targetHandle']}]", flush=True)
        else:
            missing = [x for x in [e["source"], e["target"]] if x not in node_ids]
            print(f"[V2] SKIP (missing: {missing})", flush=True)


    print(f"\n[V2] Running IR validation...", flush=True)
    all_nodes, all_edges, issues = _ir_annotate_and_validate(
        all_nodes, all_edges, hierarchy
    )
    if issues:
        print(f"[V2] IR issues found ({len(issues)}):", flush=True)
        for issue in issues:
            print(f"  ISSUE: {issue}", flush=True)
    else:
        print(f"[V2] IR validation passed -- no issues", flush=True)

    print(f"\n[V2] Running iverilog compile check...", flush=True)
    try:
        import tempfile as _tf, subprocess as _sp
        from pathlib import Path as _Path


        _ol_entries = []
        for _n in all_nodes:
            if _n.get("id", "").startswith("_output_mux"):
                _ol_entries.append({
                    "output":    _n.get("data", {}).get("name") or _n.get("name", ""),
                    "type":      "state_mux",
                    "fsm":       _n.get("fsm") or _n.get("data", {}).get("fsm", ""),
                    "default":   _n.get("default") or _n.get("data", {}).get("default", "1'b1"),
                    "overrides": _n.get("overrides") or _n.get("data", {}).get("overrides", {}),
                })
        if not _ol_entries:
            _ol_entries = hierarchy.get("output_logic", [])

        compile_ir = {
            "nodes": all_nodes,
            "edges": [
                {
                    "src":      e.get("source", ""),
                    "dst":      e.get("target", ""),
                    "src_port": e.get("sourceHandle", ""),
                    "dst_port": e.get("targetHandle", ""),
                    "condition": e.get("data", {}).get("condition", "1"),
                    **( {"priority": e["priority"]} if "priority" in e else {} ),
                }
                for e in all_edges
            ],
            "ports": [
                {
                    "id":    n.get("id", ""),
                    "name":  n.get("data", {}).get("name", n.get("name", "")),
                    "dir":   n.get("type", "input"),
                    "width": n.get("data", {}).get("width", n.get("width", 1)),
                }
                for n in all_nodes
                if n.get("type") in ("input", "output")
                and "__" not in n.get("id", "")
            ],
            "parameters": hierarchy.get("parameters", {}),
            "output_logic": _ol_entries,
            "signal_list":  hierarchy.get("signal_list", []),
        }

        with _tf.NamedTemporaryFile(
            mode="w", suffix=".json", dir=str(CODEGEN_DIR),
            delete=False, encoding="utf-8"
        ) as tf:
            json.dump(compile_ir, tf, indent=2)
            ir_path = tf.name



        vg = _sp.run(
            ["python", str(EMIT_SCRIPT), ir_path],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=str(CODEGEN_DIR)
        )
        _Path(ir_path).unlink(missing_ok=True)

        if vg.stderr.strip():
            print(f"[emit_verilog] {vg.stderr.strip()}", flush=True)

        if vg.returncode == 0:
            try:
                verilog_files = json.loads(vg.stdout)
            except Exception:
                verilog_files = {"top.v": vg.stdout}


            ok, err = await _iverilog_compile_check(verilog_files)
            if not ok:
                print(f"[V2] iverilog error (emitter bug — NOT sending to LLM):", flush=True)
                print(f"[V2] {err}", flush=True)
            else:
                print(f"[V2] iverilog compile OK on first pass", flush=True)
        else:
            print(f"[V2] Verilog generation failed: {vg.stderr[:200]}", flush=True)
            verilog_files = {}

    except Exception:
        _tb.print_exc()
        verilog_files = {}


    if verilog_files.get("top.v"):
        with open(TOP_VERILOG, "w") as f:
            f.write(verilog_files["top.v"])
        for fname, code in verilog_files.items():
            if fname != "top.v":
                with open(CODEGEN_DIR / fname, "w") as f:
                    f.write(code)


    sc_names = [sc["id"] for sc in hierarchy["sub_circuits"]]


    print(f"\n[V2] DONE: {len(all_nodes)} nodes, {len(all_edges)} edges", flush=True)
    print(f"[V2:verify] Sub-circuits: {sc_names}", flush=True)


    fsm_nodes = [n for n in all_nodes if n.get("type") == "fsm_state"]
    if fsm_nodes:
        from collections import defaultdict
        fsm_states_by_sc = defaultdict(list)
        for n in fsm_nodes:
            sc_prefix = n["id"].split("__")[0] if "__" in n["id"] else "unknown"
            state_name = n["id"].split("__")[-1] if "__" in n["id"] else n["id"]
            fsm_states_by_sc[sc_prefix].append(state_name)
        for sc_id, states in fsm_states_by_sc.items():
            print(f"[V2:verify] FSM '{sc_id}' states: {states}", flush=True)


    fsm_output_nodes = [n for n in all_nodes if n.get("data", {}).get("isFsmOutput")]
    if fsm_output_nodes:
        output_sigs = [n.get("data", {}).get("name") for n in fsm_output_nodes]
        print(f"[V2:verify] FSM output signals: {output_sigs}", flush=True)


    gated = [s for s in hierarchy.get("signal_list", []) if "gated_by" in s]
    if gated:
        for g in gated:
            print(f"[V2:verify] Gated signal: '{g['name']}' gated by '{g['gated_by']}'", flush=True)

    for sc in hierarchy.get("sub_circuits", []):
        tv = sc.get("data", {}).get("terminalValue")
        if tv:
            print(f"[V2:verify] Counter '{sc['id']}' TERMINAL_VALUE={tv}", flush=True)

    port_nodes = [n for n in all_nodes if n.get("type") in ("input", "output") and "__" not in n.get("id", "")]
    print(f"[V2:verify] Top ports: {[(n.get('data',{}).get('name'), n.get('type'), n.get('data',{}).get('width')) for n in port_nodes]}", flush=True)

    return {
        "explanation":       f"Built {hierarchy['description']}: {', '.join(sc_names)}.",
        "nodes":             all_nodes,
        "edges":             all_edges,
        "hierarchical":      True,
        "circuit_key":       circuit_key,
        "sub_circuit_names": sc_names,
        "ir_issues":         issues,
        "verilog_files":     verilog_files,
    }

__all__ = [_n for _n in dir() if not _n.startswith("__")]