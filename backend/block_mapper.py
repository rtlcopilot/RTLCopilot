"""
block_mapper.py — RTLCopilot Deterministic Block Mapper
========================================================
Maps generic block names (from Stage 0 LLM decomposition) to
specific RTLCopilot primitives with exact handle names and widths.

No LLM involved — pure Python lookup table.
The LLM in Stage 0 outputs generic names from GENERIC_VOCABULARY.
Python maps them here to primitives. Stage 1 receives fixed primitives
with handles already stamped — never invents handle names.

GENERIC_VOCABULARY is the closed list Stage 0 must choose from.
_GENERIC_TO_PRIMITIVE is the mapping table.
map_concepts_to_primitives() is the main entry point.
"""

from __future__ import annotations


GENERIC_VOCABULARY: list[str] = [
    "counter",              
    "byte_counter",         
    "bit_counter",          
    "timer",                
    "baud_generator",       
    "clock_divider",        
    "prescaler",            
    "watchdog_timer",       
    "pulse_generator",      

    "comparator",           
    "equality_checker",     
    "threshold_detector",   
    "delimiter_detector",   
    "zero_detector",        
    "overflow_detector",   
    "edge_detector",        
    "parity_checker",       

    "inverter",             
    "and_gate",             
    "or_gate",              
    "xor_gate",             
    "adder",                
    "subtractor",           
    "multiplexer",          
    "demultiplexer",        

    "fifo",                 
    "data_buffer",          
    "register",             
    "accumulator",          
    "shift_register",       
    "serializer",           
    "deserializer",        
    "pipeline_register",    

    "state_machine",        
    "frame_controller",    
    "protocol_controller",  
    "arbiter",              
    "handshake_controller", 
    "sequencer",            

    "priority_encoder",     
    "dual_port_ram",        
    "lookup_table",         
    "data_path_register",   

    "cdc_synchronizer",     
    "async_input_sync",     

    "multiplier",           
    "divider",              
    "accumulator_adder",    
]


_GENERIC_TO_PRIMITIVE: dict[str, dict] = {

    "counter": {
        "pattern": "macro_cfgcounter",
        "handles": {
            "inputs":  ["en", "load", "load_val"],
            "outputs": ["count", "tc"],
        },
        "width_rule": "data",
        "notes": "Set width=DATA_WIDTH, terminal_value as needed, countDir=1 for up",
    },
    "byte_counter": {
        "pattern": "macro_cfgcounter",
        "handles": {
            "inputs":  ["en", "load", "load_val"],
            "outputs": ["count", "tc"],
        },
        "width_rule": "data",
        "notes": "Set width=DATA_WIDTH, terminal_value=max_bytes-1",
    },
    "bit_counter": {
        "pattern": "macro_cfgcounter",
        "handles": {
            "inputs":  ["en", "load", "load_val"],
            "outputs": ["count", "tc"],
        },
        "width_rule": "data",
        "notes": "Set width=4, terminal_value=DATA_WIDTH-1",
    },
    "timer": {
        "pattern": "macro_cfgcounter",
        "handles": {
            "inputs":  ["en", "load", "load_val"],
            "outputs": ["count", "tc"],
        },
        "width_rule": "data",
        "notes": "Set terminal_value to timeout period in clock cycles",
    },
    "baud_generator": {
        "pattern": "macro_cfgcounter",
        "handles": {
            "inputs":  ["en", "load", "load_val"],
            "outputs": ["count", "tc"],
        },
        "width_rule": "data",
        "notes": "Set terminal_value=BAUD_DIV (clock_freq/baud_rate)",
    },
    "clock_divider": {
        "pattern": "macro_cfgcounter",
        "handles": {
            "inputs":  ["en", "load", "load_val"],
            "outputs": ["count", "tc"],
        },
        "width_rule": "data",
        "notes": "tc output toggles at clock_freq/(2*terminal_value)",
    },
    "prescaler": {
        "pattern": "macro_cfgcounter",
        "handles": {
            "inputs":  ["en", "load", "load_val"],
            "outputs": ["count", "tc"],
        },
        "width_rule": "data",
        "notes": "Prescaler divides clock — set terminal_value to division ratio",
    },
    "watchdog_timer": {
        "pattern": "macro_cfgcounter",
        "handles": {
            "inputs":  ["en", "load", "load_val"],
            "outputs": ["count", "tc"],
        },
        "width_rule": "data",
        "notes": "tc fires system reset on timeout — FSM reloads on kick signal",
    },
    "pulse_generator": {
        "pattern": "macro_cfgcounter",
        "handles": {
            "inputs":  ["en", "load", "load_val"],
            "outputs": ["count", "tc"],
        },
        "width_rule": "data",
        "notes": "tc output is the pulse — set terminal_value to pulse period",
    },

    "comparator": {
        "pattern": "comb",
        "comb_op": "eq",
        "handles": {
            "inputs":  ["in0", "in1"],
            "outputs": ["out"],
        },
        "width_rule": "1",
        "notes": "comb_op=eq produces 1-bit output — 1 if in0==in1",
    },
    "equality_checker": {
        "pattern": "comb",
        "comb_op": "eq",
        "handles": {
            "inputs":  ["in0", "in1"],
            "outputs": ["out"],
        },
        "width_rule": "1",
        "notes": "comb_op=eq — output 1 when inputs match",
    },
    "threshold_detector": {
        "pattern": "comb",
        "comb_op": "gt",
        "handles": {
            "inputs":  ["in0", "in1"],
            "outputs": ["out"],
        },
        "width_rule": "1",
        "notes": "comb_op=gt or lt depending on direction",
    },
    "delimiter_detector": {
        "pattern": "comb",
        "comb_op": "eq",
        "handles": {
            "inputs":  ["in0", "in1"],
            "outputs": ["out"],
        },
        "width_rule": "1",
        "notes": "comb_op=eq — in0=data_in, in1=delimiter constant; out=1 on match",
    },
    "zero_detector": {
        "pattern": "comb",
        "comb_op": "eq",
        "handles": {
            "inputs":  ["in0", "in1"],
            "outputs": ["out"],
        },
        "width_rule": "1",
        "notes": "comb_op=eq — in1 tied to 0 constant",
    },
    "overflow_detector": {
        "pattern": "comb",
        "comb_op": "eq",
        "handles": {
            "inputs":  ["in0", "in1"],
            "outputs": ["out"],
        },
        "width_rule": "1",
        "notes": "comb_op=eq — compare count to max value",
    },
    "edge_detector": {
        "pattern": "comb",
        "comb_op": "not",
        "handles": {
            "inputs":  ["in0"],
            "outputs": ["out"],
        },
        "width_rule": "1",
        "notes": "Use comb not + register to detect rising edge: out = in & ~reg_q",
    },
    "parity_checker": {
        "pattern": "comb",
        "comb_op": "xor",
        "handles": {
            "inputs":  ["in0", "in1"],
            "outputs": ["out"],
        },
        "width_rule": "1",
        "notes": "comb_op=xor across all data bits",
    },

    "inverter": {
        "pattern": "comb",
        "comb_op": "not",
        "handles": {
            "inputs":  ["in0"],
            "outputs": ["out"],
        },
        "width_rule": "1",
        "notes": "comb_op=not — single input inversion",
    },
    "and_gate": {
        "pattern": "comb",
        "comb_op": "and",
        "handles": {
            "inputs":  ["in0", "in1"],
            "outputs": ["out"],
        },
        "width_rule": "1",
        "notes": "comb_op=and — gating or masking",
    },
    "or_gate": {
        "pattern": "comb",
        "comb_op": "or",
        "handles": {
            "inputs":  ["in0", "in1"],
            "outputs": ["out"],
        },
        "width_rule": "1",
        "notes": "comb_op=or",
    },
    "xor_gate": {
        "pattern": "comb",
        "comb_op": "xor",
        "handles": {
            "inputs":  ["in0", "in1"],
            "outputs": ["out"],
        },
        "width_rule": "1",
        "notes": "comb_op=xor",
    },
    "adder": {
        "pattern": "comb",
        "comb_op": "add",
        "handles": {
            "inputs":  ["in0", "in1"],
            "outputs": ["out"],
        },
        "width_rule": "data",
        "notes": "comb_op=add — output width = DATA_WIDTH",
    },
    "subtractor": {
        "pattern": "comb",
        "comb_op": "sub",
        "handles": {
            "inputs":  ["in0", "in1"],
            "outputs": ["out"],
        },
        "width_rule": "data",
        "notes": "comb_op=sub",
    },
    "multiplexer": {
        "pattern": "mux",
        "handles": {
            "inputs":  ["in0", "in1", "sel"],
            "outputs": ["out"],
        },
        "width_rule": "data",
        "notes": "sel=1-bit; in0/in1=DATA_WIDTH",
    },
    "demultiplexer": {
        "pattern": "mux",
        "handles": {
            "inputs":  ["in0", "in1", "sel"],
            "outputs": ["out"],
        },
        "width_rule": "data",
        "notes": "Use mux in reverse routing context",
    },

    "fifo": {
        "pattern": "macro_fifo",
        "handles": {
            "inputs":  ["wr_en", "din", "rd_en"],
            "outputs": ["dout", "full", "empty", "ae"],
        },
        "width_rule": "data",
        "notes": "Set width=DATA_WIDTH, fifoDepth as needed",
    },
    "data_buffer": {
        "pattern": "macro_fifo",
        "handles": {
            "inputs":  ["wr_en", "din", "rd_en"],
            "outputs": ["dout", "full", "empty", "ae"],
        },
        "width_rule": "data",
        "notes": "Same as fifo — buffer between producer and consumer",
    },
    "register": {
        "pattern": "reg",
        "handles": {
            "inputs":  ["d"],
            "outputs": ["q"],
        },
        "width_rule": "data",
        "notes": "Single D flip-flop — clk/rst implicit",
    },
    "accumulator": {
        "pattern": "reg",
        "handles": {
            "inputs":  ["d"],
            "outputs": ["q"],
        },
        "width_rule": "data",
        "notes": "Register that accumulates — d = q + new_value via adder",
    },
    "shift_register": {
        "pattern": "macro_shiftreg",
        "handles": {
            "inputs":  ["din", "en", "load"],
            "outputs": ["sout", "q"],
        },
        "width_rule": "data",
        "notes": "Set srMode: PISO for TX, SIPO for RX, width=DATA_WIDTH",
    },
    "serializer": {
        "pattern": "macro_shiftreg",
        "handles": {
            "inputs":  ["din", "en", "load"],
            "outputs": ["sout"],
        },
        "width_rule": "data",
        "notes": "srMode=PISO — parallel in, serial out. din width=DATA_WIDTH (parallel byte), sout width=1 (serial bit). Set width=DATA_WIDTH in parameters.",
    },
    "deserializer": {
        "pattern": "macro_shiftreg",
        "handles": {
            "inputs":  ["din", "en", "load"],
            "outputs": ["q"],
        },
        "width_rule": "data",
        "notes": "srMode=SIPO — serial in, parallel out. din width=1 (serial bit), q width=DATA_WIDTH (parallel byte). Set width=DATA_WIDTH in parameters.",
    },
    "pipeline_register": {
        "pattern": "reg",
        "handles": {
            "inputs":  ["d"],
            "outputs": ["q"],
        },
        "width_rule": "data",
        "notes": "Single pipeline stage — delays signal by one clock",
    },

    "state_machine": {
        "pattern": "fsm",
        "handles": {
            "inputs":  ["<condition_signals>"],
            "outputs": ["<fsm_output_signals>"],
        },
        "width_rule": "1",
        "notes": "Define fsm_states and fsm_outputs in Stage 0; transitions in Stage 3",
    },
    "frame_controller": {
        "pattern": "fsm",
        "handles": {
            "inputs":  ["<condition_signals>"],
            "outputs": ["<fsm_output_signals>"],
        },
        "width_rule": "1",
        "notes": "FSM for frame sync — typical states: idle, header, payload, end",
    },
    "protocol_controller": {
        "pattern": "fsm",
        "handles": {
            "inputs":  ["<condition_signals>"],
            "outputs": ["<fsm_output_signals>"],
        },
        "width_rule": "1",
        "notes": "FSM for protocol — start/address/data/stop phases",
    },
    "arbiter": {
        "pattern": "fsm",
        "handles": {
            "inputs":  ["<condition_signals>"],
            "outputs": ["<fsm_output_signals>"],
        },
        "width_rule": "1",
        "notes": "Round-robin or priority arbitration FSM",
    },
    "handshake_controller": {
        "pattern": "fsm",
        "handles": {
            "inputs":  ["<condition_signals>"],
            "outputs": ["<fsm_output_signals>"],
        },
        "width_rule": "1",
        "notes": "FSM for req/ack or valid/ready handshakes",
    },
    "sequencer": {
        "pattern": "fsm",
        "handles": {
            "inputs":  ["<condition_signals>"],
            "outputs": ["<fsm_output_signals>"],
        },
        "width_rule": "1",
        "notes": "Multi-step operation sequencer FSM",
    },

    "priority_encoder": {
        "pattern": "macro_penc",
        "handles": {
            "inputs":  ["data_in"],
            "outputs": ["index", "valid"],
        },
        "width_rule": "data",
        "notes": "Finds highest-priority set bit index",
    },
    "dual_port_ram": {
        "pattern": "macro_dpram",
        "handles": {
            "inputs":  ["we_a", "addr_a", "din_a", "we_b", "addr_b", "din_b"],
            "outputs": ["dout_a", "dout_b"],
        },
        "width_rule": "data",
        "notes": "Set width=DATA_WIDTH, addrWidth as needed",
    },
    "lookup_table": {
        "pattern": "macro_dpram",
        "handles": {
            "inputs":  ["we_a", "addr_a", "din_a", "we_b", "addr_b", "din_b"],
            "outputs": ["dout_a", "dout_b"],
        },
        "width_rule": "data",
        "notes": "Use port B for read-only LUT access; port A for initialization",
    },
    "data_path_register": {
        "pattern": "reg",
        "handles": {
            "inputs":  ["d"],
            "outputs": ["q"],
        },
        "width_rule": "data",
        "notes": "Register in the data path",
    },

    "cdc_synchronizer": {
        "pattern": "macro_sync",
        "handles": {
            "inputs":  ["d"],
            "outputs": ["q"],
        },
        "width_rule": "1",
        "notes": "2-FF synchronizer — one per bit crossing clock domain",
    },
    "async_input_sync": {
        "pattern": "macro_sync",
        "handles": {
            "inputs":  ["d"],
            "outputs": ["q"],
        },
        "width_rule": "1",
        "notes": "Synchronize external async input to system clock",
    },

    "multiplier": {
        "pattern": "comb",
        "comb_op": "mul",
        "handles": {
            "inputs":  ["in0", "in1"],
            "outputs": ["out"],
        },
        "width_rule": "data",
        "notes": "comb_op=mul — output width = 2*DATA_WIDTH for full product",
    },
    "divider": {
        "pattern": "fsm",
        "handles": {
            "inputs":  ["<condition_signals>"],
            "outputs": ["<fsm_output_signals>"],
        },
        "width_rule": "data",
        "notes": "Restoring division needs FSM + shift register — multi-cycle",
    },
    "accumulator_adder": {
        "pattern": "comb",
        "comb_op": "add",
        "handles": {
            "inputs":  ["in0", "in1"],
            "outputs": ["out"],
        },
        "width_rule": "data",
        "notes": "Add new value to register q; feed back through register",
    },
}


def map_concepts_to_primitives(
    concepts: list[dict],
) -> tuple[list[dict] | None, str | None]:
    """
    Map Stage 0 generic concept list to RTLCopilot primitives.

    Each concept dict from Stage 0 has:
        generic_type:      str  — must be in GENERIC_VOCABULARY
        role:              str  — one-sentence functional description
        suggested_id:      str  — snake_case block id
        width_hint:        str  — optional data width hint
        connection_hints:  str  — optional wiring hint for Stage 1
        fsm_states:        list — required if generic_type is an FSM type
        fsm_outputs:       list — required if generic_type is an FSM type

    Returns:
        (mapped_concepts, None)       on success
        (None, clarification_message) if any concept is unmappable
    """
    mapped = []
    unknown = []

    for c in concepts:
        gtype = c.get("generic_type", "").lower().strip()
        rule  = _GENERIC_TO_PRIMITIVE.get(gtype)

        if not rule:
            unknown.append(gtype)
            continue

        mapped_concept = {
            "id":               c.get("suggested_id", gtype),
            "name":             c.get("suggested_id", gtype),
            "role":             c.get("role", ""),
            "width_hint":       c.get("width_hint", "8"),
            "connection_hints": c.get("connection_hints", ""),
            "fsm_states":       c.get("fsm_states", []),
            "fsm_outputs":      c.get("fsm_outputs", []),

            "pattern":          rule["pattern"],
            "comb_op":          rule.get("comb_op"),        
            "handles":          rule["handles"],            
            "width_rule":       rule["width_rule"],
            "mapper_notes":     rule["notes"],
        }
        mapped.append(mapped_concept)
        print(
            f"[MAPPER] '{gtype}' → {rule['pattern']}"
            + (f" (comb_op={rule['comb_op']})" if rule.get("comb_op") else ""),
            flush=True,
        )

    if unknown:
        clarification = (
            f"I couldn't map these concepts to available RTL primitives: "
            f"{unknown}.\n\n"
            "Could you clarify what these blocks should do? For example:\n"
            + "\n".join(f"  - What does '{u}' do in your circuit?" for u in unknown)
        )
        print(f"[MAPPER] Unmappable concepts: {unknown}", flush=True)
        return None, clarification

    return mapped, None


def get_stage0_vocabulary_prompt() -> str:
    """
    Build the closed vocabulary string injected into Stage 0 system prompt.
    Stage 0 must choose generic_type values ONLY from this list.
    """
    lines = [
        "GENERIC BLOCK VOCABULARY — you MUST use ONLY these generic_type values:",
        "(grouped by function — pick the closest match to each concept)",
        "",
    ]

    categories = {
        "Counting & Timing": [
            "counter", "byte_counter", "bit_counter", "timer",
            "baud_generator", "clock_divider", "prescaler",
            "watchdog_timer", "pulse_generator",
        ],
        "Comparison & Detection": [
            "comparator", "equality_checker", "threshold_detector",
            "delimiter_detector", "zero_detector", "overflow_detector",
            "edge_detector", "parity_checker",
        ],
        "Logic & Combinational": [
            "inverter", "and_gate", "or_gate", "xor_gate",
            "adder", "subtractor", "multiplexer", "demultiplexer",
        ],
        "Storage & Buffering": [
            "fifo", "data_buffer", "register", "accumulator",
            "shift_register", "serializer", "deserializer", "pipeline_register",
        ],
        "Control & Sequencing": [
            "state_machine", "frame_controller", "protocol_controller",
            "arbiter", "handshake_controller", "sequencer",
        ],
        "Data Path": [
            "priority_encoder", "dual_port_ram",
            "lookup_table", "data_path_register",
        ],
        "Clock Domain Crossing": [
            "cdc_synchronizer", "async_input_sync",
        ],
        "Arithmetic": [
            "multiplier", "divider", "accumulator_adder",
        ],
    }

    for cat, names in categories.items():
        lines.append(f"  {cat}:")
        lines.append("    " + ", ".join(names))
        lines.append("")

    lines.append(
        "RULE: generic_type must be EXACTLY one of the above strings.\n"
        "NEVER invent a new generic_type. If unsure, pick the closest match\n"
        "and explain in the role field."
    )
    return "\n".join(lines)