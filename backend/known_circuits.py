"""
known_circuits.py
=================
Canonical hardware architecture templates for RTLCopilot.

Each entry defines the exact sub-circuits, signal names, widths,
and FSM transition tables. The LLM never invents topology for
known circuits — it only fills in parameters.

Schema layers per circuit (fully specified for uart_tx, others TBD):
  Layer 0 — description, sub_circuits, top_level_inputs/outputs  (block diagram)
  Layer 1 — signal_list       (every signal, driver, consumers, reset value)
  Layer 2 — output_logic      (combinational output muxing — e.g. UART tx_out)
  Layer 3 — reset             (polarity and type — enforced across all submodules)
  Layer 4 — timing            (per-state control actions — counter resets, enables)

Import in api_final.py:
    from known_circuits import (
        _KNOWN_HIERARCHIES,
        _FSM_TRANSITION_TABLES,
        _CIRCUIT_KEYWORDS,
        PRIMITIVE_BLOCK_SPECS,
    )
"""


_CIRCUIT_KEYWORDS: dict[str, list[str]] = {

    "uart_tx":          ["uart tx", "uart transmit", "uart transmitter"],
    "uart_rx":          ["uart rx", "uart receive", "uart receiver"],
    "spi_master":       ["spi master", "spi controller"],
    "spi_slave":        ["spi slave"],
    "i2c_master":       ["i2c master", "i2c controller"],
    "i2c_slave":        ["i2c slave"],
    
    "fifo_ctrl":        ["fifo controller", "fifo control"],
    "ping_pong":        ["ping pong buffer", "ping-pong"],
    "sram_ctrl":        ["sram controller", "sram control"],
    "dma_ctrl":         ["dma controller", "dma control", "direct memory"],
    "circ_buffer":      ["circular buffer", "ring buffer"],

    "pwm":              ["pwm", "pulse width modulation"],
    "fir_filter":       ["fir filter", "finite impulse"],
    "moving_avg":       ["moving average", "running average"],
    "cic_filter":       ["cic filter", "cic decimat"],
    "nco":              ["nco", "numerically controlled oscillator", "dds"],

    "alu":              ["alu", "arithmetic logic unit"],
    "multiplier":       ["multiplier", "shift add multiply"],
    "divider":          ["divider", "restoring division"],
    "accumulator":      ["accumulator", "running sum"],
    "mac_unit":         ["mac unit", "multiply accumulate", "mac"],

    "clk_divider":      ["clock divider", "clk divider", "frequency divider"],
    "cdc_sync":         ["cdc synchronizer", "clock domain crossing", "cdc sync"],
    "debouncer":        ["debounce", "debouncer", "button debounce"],
    "pulse_stretch":    ["pulse stretcher", "pulse extender"],

    "crc_gen":          ["crc generator", "crc8", "crc16", "crc32", "crc"],
    "hamming_enc":      ["hamming encoder", "hamming code encoder"],
    "hamming_dec":      ["hamming decoder", "hamming code decoder"],
    "parity_chk":       ["parity checker", "parity check"],

    "manchester_enc":   ["manchester encoder", "manchester encoding"],
    "manchester_dec":   ["manchester decoder", "manchester decoding"],
    "enc_8b10b":        ["8b10b encoder", "8b/10b"],
    "gray_conv":        ["gray code", "gray converter"],

    "axi_lite_slave":   ["axi lite slave", "axi-lite slave", "axi slave"],
    "apb_master":       ["apb master", "apb controller"],
    "rr_arbiter":       ["round robin arbiter", "round-robin"],
    "priority_arbiter": ["priority arbiter", "fixed priority"],

    "spi_adc":          ["spi adc", "adc interface", "analog digital interface"],
    "i2c_sensor":       ["i2c sensor", "sensor interface"],
    "uart_gps":         ["gps parser", "nmea parser", "gps uart"],

    "cordic":           ["cordic", "sine cosine", "trigonometric"],
    "iir_filter":       ["iir filter", "biquad", "infinite impulse"],
    "sigma_delta":      ["sigma delta", "sigma-delta modulator"],

    "reg_file":         ["register file", "regfile"],
    "prog_counter":     ["program counter", "pc with branch"],
    "accum_cpu":        ["accumulator cpu", "simple cpu", "simple processor"],
}


PRIMITIVE_BLOCK_SPECS: dict[str, dict] = {

    "macro_cfgcounter": {
        "description": "Configurable up/down counter with terminal count pulse",
        "ports": {
            "inputs":  [
                {"name": "en",       "width": "1", "note": "count enable — 1 to count"},
                {"name": "load",     "width": "1", "note": "synchronous load — 1 to load load_val"},
                {"name": "load_val", "width": "N", "note": "value to load on load=1"},
            ],
            "outputs": [
                {"name": "count", "width": "N", "note": "current count value"},
                {"name": "tc",    "width": "1", "note": "terminal count — 1-cycle pulse when count reaches TERMINAL_VALUE"},
            ],
        },
        "typical_params": ["width (bit width of counter)", "terminal_value (count target)", "countDir (1=up, 0=down)"],
        "usage": "Use for baud rate generation, bit counting, timeout periods, PWM periods — anywhere you need 'count N cycles then pulse'.",
        "triggers": [
            "count", "counter", "timer", "timeout", "byte counter", "bit counter",
            "period", "baud", "frequency divide", "N cycles", "pulse after N"
        ],
        "common_exports": ["tc"],
        "common_imports": ["en (from FSM)", "load (from FSM)", "load_val (constant or external)"],
    },

    "macro_fifo": {
        "description": "Synchronous FIFO with full/empty/almost-empty flags",
        "ports": {
            "inputs":  [
                {"name": "wr_en", "width": "1", "note": "write enable"},
                {"name": "din",   "width": "N", "note": "write data"},
                {"name": "rd_en", "width": "1", "note": "read enable"},
            ],
            "outputs": [
                {"name": "dout",  "width": "N", "note": "read data"},
                {"name": "full",  "width": "1", "note": "FIFO full flag"},
                {"name": "empty", "width": "1", "note": "FIFO empty flag"},
                {"name": "ae",    "width": "1", "note": "almost-empty flag"},
            ],
        },
        "typical_params": ["width (data width)", "fifoDepth (number of entries)", "aeThresh (almost-empty threshold)"],
        "usage": "Use to buffer data between a producer and consumer running at different rates — e.g. host writes, UART TX reads.",
        "triggers": [
            "fifo", "buffer", "queue", "store", "data buffer", "byte buffer",
            "ping pong", "producer consumer", "elastic buffer"
        ],
        "common_exports": ["dout", "empty", "full"],
        "common_imports": ["wr_en (external)", "din (external)", "rd_en (from FSM)"],
    },

    "macro_shiftreg": {
        "description": "Shift register supporting PISO / SISO / SIPO / PIPO modes",
        "ports": {
            "inputs":  [
                {"name": "din",  "width": "N", "note": "parallel data in (PISO/PIPO) or serial data in (SISO/SIPO)"},
                {"name": "en",   "width": "1", "note": "shift enable"},
                {"name": "load", "width": "1", "note": "parallel load strobe"},
            ],
            "outputs": [
                {"name": "sout", "width": "1", "note": "serial output (PISO/SISO modes)"},
                {"name": "q",    "width": "N", "note": "parallel output (SIPO/PIPO modes)"},
            ],
        },
        "typical_params": ["width (data width)", "srMode (PISO|SISO|SIPO|PIPO)", "shiftDir (left|right)"],
        "usage": "Use to serialize parallel data (PISO) or deserialize serial data (SIPO) — e.g. UART/SPI TX shift register.",
        "triggers": [
            "shift register", "serialize", "deserialize", "serial in parallel out",
            "parallel in serial out", "shift", "sipo", "piso"
        ],
        "common_exports": ["sout (PISO/SISO)", "q (SIPO/PIPO)"],
        "common_imports": ["din (from FIFO or external)", "en (from FSM, often gated by baud_tc)", "load (from FSM)"],
    },

    "fsm": {
        "description": "Moore finite state machine — you define states, outputs, and transitions",
        "ports": {
            "inputs":  [
                {"name": "<condition signals>", "width": "1", "note": "1-bit condition wires that drive state transitions"},
            ],
            "outputs": [
                {"name": "<fsm_output signals>", "width": "1", "note": "registered Moore outputs — one value per state"},
            ],
        },
        "typical_params": ["fsm_states (list of state names)", "fsm_outputs (list of 1-bit output signal names)"],
        "usage": "Use whenever you need sequenced control — start/data/stop phases, handshake protocols, multi-step operations.",
        "triggers": [
            "state machine", "fsm", "sequence", "protocol", "handshake", "phase",
            "multi-step", "control flow", "frame state", "arbitration", "schedule"
        ],
        "common_exports": ["control signals: load, shift_en, rd_en, wr_en, done, valid, cs_n, etc."],
        "common_imports": ["tc (from counter)", "empty/full (from FIFO)", "external handshake signals"],
    },

    "comb": {
        "description": "Combinational logic node — single operation on 1 or 2 inputs",
        "ports": {
            "inputs":  [
                {"name": "in0", "width": "N", "note": "first operand (all ops)"},
                {"name": "in1", "width": "N", "note": "second operand (binary ops only)"},
            ],
            "outputs": [
                {"name": "out", "width": "N", "note": "result"},
            ],
        },
        "typical_params": ["op (not|buf|and|or|xor|add|sub|eq|lt|gt)", "width"],
        "usage": "Use for signal inversion (not), gating (and), comparison (eq/lt/gt), or arithmetic (add/sub). One node per operation.",
        "triggers": [
            "compare", "detect", "check if", "equals", "match", "delimiter detection",
            "threshold", "greater than", "less than", "invert", "gate", "and gate",
            "or gate", "xor", "add", "subtract", "comparator", "equality"
        ],
        "common_exports": ["out"],
        "common_imports": ["in0, in1 from counters, FIFOs, FSMs, or external ports"],
    },

    "reg": {
        "description": "D flip-flop register — clk/rst implicit",
        "ports": {
            "inputs":  [{"name": "d", "width": "N", "note": "data input"}],
            "outputs": [{"name": "q", "width": "N", "note": "registered output"}],
        },
        "typical_params": ["width"],
        "usage": "Use to pipeline a signal by one clock cycle, or to register a combinational result.",
        "triggers": [
            "register", "flip flop", "latch", "pipeline stage", "delay one cycle",
            "store value", "sample"
        ],
        "common_exports": ["q"],
        "common_imports": ["d (from comb node or external)"],
    },

    "macro_sync": {
        "description": "2-FF CDC synchronizer for single-bit signals crossing clock domains",
        "ports": {
            "inputs":  [{"name": "d", "width": "1", "note": "async input signal"}],
            "outputs": [{"name": "q", "width": "1", "note": "synchronized output"}],
        },
        "typical_params": [],
        "usage": "Use whenever a 1-bit signal crosses from one clock domain to another — prevents metastability.",
        "triggers": [
            "cdc", "clock domain crossing", "synchronizer", "metastability",
            "async input", "cross domain"
        ],
        "common_exports": ["q"],
        "common_imports": ["d (from external async signal)"],
    },

    "macro_penc": {
        "description": "Priority encoder — finds the index of the highest (or lowest) set bit",
        "ports": {
            "inputs":  [{"name": "data_in", "width": "N", "note": "input vector"}],
            "outputs": [
                {"name": "index", "width": "N", "note": "binary index of priority bit"},
                {"name": "valid", "width": "1", "note": "1 if any input bit is set"},
            ],
        },
        "typical_params": ["width", "lsbPriority (0=MSB first, 1=LSB first)"],
        "usage": "Use to find which requester has highest priority in an arbiter, or first set bit in a mask.",
        "triggers": [
            "priority encoder", "first set bit", "highest priority", "leading one",
            "arbitration priority"
        ],
        "common_exports": ["index", "valid"],
        "common_imports": ["data_in (request vector from external)"],
    },

    "macro_dpram": {
        "description": "Dual-port RAM — independent read/write on two ports",
        "ports": {
            "inputs":  [
                {"name": "we_a",   "width": "1", "note": "port A write enable"},
                {"name": "addr_a", "width": "N", "note": "port A address"},
                {"name": "din_a",  "width": "N", "note": "port A write data"},
                {"name": "we_b",   "width": "1", "note": "port B write enable"},
                {"name": "addr_b", "width": "N", "note": "port B address"},
                {"name": "din_b",  "width": "N", "note": "port B write data"},
            ],
            "outputs": [
                {"name": "dout_a", "width": "N", "note": "port A read data"},
                {"name": "dout_b", "width": "N", "note": "port B read data"},
            ],
        },
        "typical_params": ["width (data width)", "addrWidth (address bits → depth = 2^addrWidth)"],
        "usage": "Use for register files, lookup tables, or ping-pong buffers where two agents need simultaneous access.",
        "triggers": [
            "dual port ram", "dpram", "register file", "lookup table",
            "two port memory", "simultaneous read write"
        ],
        "common_exports": ["dout_a", "dout_b"],
        "common_imports": ["addr, din, we from FSM or external"],
    },

    "mux": {
        "description": "N-to-1 multiplexer",
        "ports": {
            "inputs":  [
                {"name": "in0..inN", "width": "N", "note": "data inputs"},
                {"name": "sel0..selM", "width": "1", "note": "select bits — ceil(log2(N)) bits total"},
            ],
            "outputs": [{"name": "out", "width": "N", "note": "selected output"}],
        },
        "typical_params": ["muxSize (number of inputs)", "width"],
        "usage": "Use to select between multiple data sources based on a control signal — e.g. ALU input selection.",
        "triggers": [
            "mux", "multiplexer", "select", "choose between", "data selector"
        ],
        "common_exports": ["out"],
        "common_imports": ["in0..inN from data sources, sel from FSM or external"],
    },
}


_FSM_TRANSITION_TABLES: dict[str, dict] = {


    "tx_fsm": {
        "states":      ["idle", "read_fifo", "start_bit", "data_bits", "stop_bit"],
        "reset_state": "idle",
        "fsm_outputs": ["shift_en", "load", "rd_en", "tx_bit",
                        "baud_en", "bit_counter_load", "baud_counter_load"],
        "outputs_per_state": {
            "idle":      {
                "shift_en": "0", "load": "0", "rd_en": "0", "tx_bit": "1",
                "baud_en": "0", "bit_counter_load": "0", "baud_counter_load": "0",
            },

            "read_fifo": {
                "shift_en": "0", "load": "0", "rd_en": "1", "tx_bit": "1",
                "baud_en": "0", "bit_counter_load": "0", "baud_counter_load": "1",
            },
 
            "start_bit": {
                "shift_en": "0", "load": "1", "rd_en": "0", "tx_bit": "0",
                "baud_en": "1", "bit_counter_load": "1", "baud_counter_load": "0",
            },
            "data_bits": {
                "shift_en": "1", "load": "0", "rd_en": "0", "tx_bit": "0",
                "baud_en": "1", "bit_counter_load": "0", "baud_counter_load": "0",
            },
            "stop_bit":  {
                "shift_en": "0", "load": "0", "rd_en": "0", "tx_bit": "1",
                "baud_en": "1", "bit_counter_load": "0", "baud_counter_load": "0",
            },
        },
        "transitions": [
            {"from": "idle",      "to": "read_fifo", "condition": "not_empty"},
            {"from": "read_fifo", "to": "start_bit", "condition": "1"},
            {"from": "start_bit", "to": "data_bits", "condition": "baud_counter_tc"},
            {"from": "data_bits", "to": "stop_bit",  "condition": "bit_counter_tc",
             "priority": 0},
            {"from": "data_bits", "to": "data_bits", "condition": "not_bit_tc",
             "priority": 1},
            {"from": "stop_bit",  "to": "idle",      "condition": "baud_counter_tc"},
        ],
    },


    "rx_fsm": {
        "states":      ["idle", "start_detect", "data_bits", "stop_bit", "done"],
        "reset_state": "idle",
        "fsm_outputs": ["shift_en", "wr_en", "rx_ready"],
        "outputs_per_state": {
            "idle":         {"shift_en": "0", "wr_en": "0", "rx_ready": "0"},
            "start_detect": {"shift_en": "0", "wr_en": "0", "rx_ready": "0"},
            "data_bits":    {"shift_en": "1", "wr_en": "0", "rx_ready": "0"},
            "stop_bit":     {"shift_en": "0", "wr_en": "0", "rx_ready": "0"},
            "done":         {"shift_en": "0", "wr_en": "1", "rx_ready": "1"},
        },
        "transitions": [
            {"from": "idle",         "to": "start_detect", "condition": "not_rx_in"},
            {"from": "start_detect", "to": "data_bits",    "condition": "tc"},
            {"from": "data_bits",    "to": "stop_bit",     "condition": "bit_tc",     "priority": 0},
            {"from": "data_bits",    "to": "data_bits",    "condition": "not_bit_tc", "priority": 1},
            {"from": "stop_bit",     "to": "done",         "condition": "tc"},
            {"from": "done",         "to": "idle",         "condition": "1"},
        ],
    },


    "spi_fsm": {
        "states":      ["idle", "cs_assert", "transfer", "cs_deassert"],
        "reset_state": "idle",
        "fsm_outputs": ["cs_n", "sclk", "shift_en", "load", "done"],
        "outputs_per_state": {
            "idle":        {"cs_n": "1", "sclk": "0", "shift_en": "0", "load": "0", "done": "0"},
            "cs_assert":   {"cs_n": "0", "sclk": "0", "shift_en": "0", "load": "1", "done": "0"},
            "transfer":    {"cs_n": "0", "sclk": "1", "shift_en": "1", "load": "0", "done": "0"},
            "cs_deassert": {"cs_n": "1", "sclk": "0", "shift_en": "0", "load": "0", "done": "1"},
        },
        "transitions": [
            {"from": "idle",        "to": "cs_assert",   "condition": "start"},
            {"from": "cs_assert",   "to": "transfer",    "condition": "tc"},
            {"from": "transfer",    "to": "cs_deassert", "condition": "bit_tc",     "priority": 0},
            {"from": "transfer",    "to": "transfer",    "condition": "not_bit_tc", "priority": 1},
            {"from": "cs_deassert", "to": "idle",        "condition": "tc"},
        ],
    },


    "spi_slave_fsm": {
        "states":      ["idle", "receiving", "done"],
        "reset_state": "idle",
        "fsm_outputs": ["shift_en", "wr_en", "rx_ready"],
        "outputs_per_state": {
            "idle":      {"shift_en": "0", "wr_en": "0", "rx_ready": "0"},
            "receiving": {"shift_en": "1", "wr_en": "0", "rx_ready": "0"},
            "done":      {"shift_en": "0", "wr_en": "1", "rx_ready": "1"},
        },
        "transitions": [
            {"from": "idle",      "to": "receiving", "condition": "not_cs_n"},
            {"from": "receiving", "to": "done",      "condition": "bit_tc",     "priority": 0},
            {"from": "receiving", "to": "receiving", "condition": "not_bit_tc", "priority": 1},
            {"from": "done",      "to": "idle",      "condition": "cs_n"},
        ],
    },


    "i2c_fsm": {
        "states":      ["idle", "start", "addr", "ack1", "data", "ack2", "stop"],
        "reset_state": "idle",
        "fsm_outputs": ["scl_en", "sda_out", "shift_en", "load", "done", "error"],
        "outputs_per_state": {
            "idle":  {"scl_en": "0", "sda_out": "1", "shift_en": "0", "load": "0", "done": "0", "error": "0"},
            "start": {"scl_en": "0", "sda_out": "0", "shift_en": "0", "load": "1", "done": "0", "error": "0"},
            "addr":  {"scl_en": "1", "sda_out": "0", "shift_en": "1", "load": "0", "done": "0", "error": "0"},
            "ack1":  {"scl_en": "1", "sda_out": "1", "shift_en": "0", "load": "0", "done": "0", "error": "0"},
            "data":  {"scl_en": "1", "sda_out": "0", "shift_en": "1", "load": "0", "done": "0", "error": "0"},
            "ack2":  {"scl_en": "1", "sda_out": "1", "shift_en": "0", "load": "0", "done": "0", "error": "0"},
            "stop":  {"scl_en": "0", "sda_out": "1", "shift_en": "0", "load": "0", "done": "1", "error": "0"},
        },
        "transitions": [
            {"from": "idle",  "to": "start", "condition": "start_req"},
            {"from": "start", "to": "addr",  "condition": "tc"},
            {"from": "addr",  "to": "ack1",  "condition": "bit_tc"},
            {"from": "ack1",  "to": "data",  "condition": "not_sda_in", "priority": 0},
            {"from": "ack1",  "to": "idle",  "condition": "sda_in",     "priority": 1},
            {"from": "data",  "to": "ack2",  "condition": "bit_tc"},
            {"from": "ack2",  "to": "stop",  "condition": "not_sda_in", "priority": 0},
            {"from": "ack2",  "to": "idle",  "condition": "sda_in",     "priority": 1},
            {"from": "stop",  "to": "idle",  "condition": "1"},
        ],
    },


    "debounce_fsm": {
        "states":      ["idle", "counting", "stable"],
        "reset_state": "idle",
        "fsm_outputs": ["btn_out", "cnt_en"],
        "outputs_per_state": {
            "idle":     {"btn_out": "0", "cnt_en": "0"},
            "counting": {"btn_out": "0", "cnt_en": "1"},
            "stable":   {"btn_out": "1", "cnt_en": "0"},
        },
        "transitions": [
            {"from": "idle",     "to": "counting", "condition": "btn_raw"},
            {"from": "counting", "to": "stable",   "condition": "tc",         "priority": 0},
            {"from": "counting", "to": "idle",     "condition": "not_btn_raw","priority": 1},
            {"from": "stable",   "to": "idle",     "condition": "not_btn_raw"},
        ],
    },


    "pwm_fsm": {
        "states":      ["high", "low"],
        "reset_state": "high",
        "fsm_outputs": ["pwm_out"],
        "outputs_per_state": {
            "high": {"pwm_out": "1"},
            "low":  {"pwm_out": "0"},
        },
        "transitions": [
            {"from": "high", "to": "low",  "condition": "duty_tc"},
            {"from": "low",  "to": "high", "condition": "period_tc"},
        ],
    },

    "dma_fsm": {
        "states":      ["idle", "req", "burst", "done"],
        "reset_state": "idle",
        "fsm_outputs": ["bus_req", "rd_en", "wr_en", "dma_done"],
        "outputs_per_state": {
            "idle":  {"bus_req": "0", "rd_en": "0", "wr_en": "0", "dma_done": "0"},
            "req":   {"bus_req": "1", "rd_en": "0", "wr_en": "0", "dma_done": "0"},
            "burst": {"bus_req": "1", "rd_en": "1", "wr_en": "1", "dma_done": "0"},
            "done":  {"bus_req": "0", "rd_en": "0", "wr_en": "0", "dma_done": "1"},
        },
        "transitions": [
            {"from": "idle",  "to": "req",   "condition": "dma_req"},
            {"from": "req",   "to": "burst", "condition": "bus_grant"},
            {"from": "burst", "to": "done",  "condition": "tc",     "priority": 0},
            {"from": "burst", "to": "burst", "condition": "not_tc", "priority": 1},
            {"from": "done",  "to": "idle",  "condition": "1"},
        ],
    },

    "axi_lite_fsm": {
        "states":      ["idle", "read_addr", "read_data", "write_addr",
                        "write_data", "write_resp"],
        "reset_state": "idle",
        "fsm_outputs": ["arready", "rvalid", "awready", "wready", "bvalid"],
        "outputs_per_state": {
            "idle":       {"arready": "1", "rvalid": "0", "awready": "1", "wready": "0", "bvalid": "0"},
            "read_addr":  {"arready": "0", "rvalid": "0", "awready": "0", "wready": "0", "bvalid": "0"},
            "read_data":  {"arready": "0", "rvalid": "1", "awready": "0", "wready": "0", "bvalid": "0"},
            "write_addr": {"arready": "0", "rvalid": "0", "awready": "0", "wready": "1", "bvalid": "0"},
            "write_data": {"arready": "0", "rvalid": "0", "awready": "0", "wready": "0", "bvalid": "0"},
            "write_resp": {"arready": "0", "rvalid": "0", "awready": "0", "wready": "0", "bvalid": "1"},
        },
        "transitions": [
            {"from": "idle",       "to": "read_addr",  "condition": "arvalid", "priority": 0},
            {"from": "idle",       "to": "write_addr", "condition": "awvalid", "priority": 1},
            {"from": "read_addr",  "to": "read_data",  "condition": "1"},
            {"from": "read_data",  "to": "idle",       "condition": "rready"},
            {"from": "write_addr", "to": "write_data", "condition": "wvalid"},
            {"from": "write_data", "to": "write_resp", "condition": "1"},
            {"from": "write_resp", "to": "idle",       "condition": "bready"},
        ],
    },

    "rr_fsm": {
        "states":      ["grant0", "grant1", "grant2", "grant3"],
        "reset_state": "grant0",
        "fsm_outputs": ["gnt0", "gnt1", "gnt2", "gnt3"],
        "outputs_per_state": {
            "grant0": {"gnt0": "1", "gnt1": "0", "gnt2": "0", "gnt3": "0"},
            "grant1": {"gnt0": "0", "gnt1": "1", "gnt2": "0", "gnt3": "0"},
            "grant2": {"gnt0": "0", "gnt1": "0", "gnt2": "1", "gnt3": "0"},
            "grant3": {"gnt0": "0", "gnt1": "0", "gnt2": "0", "gnt3": "1"},
        },
        "transitions": [
            {"from": "grant0", "to": "grant1", "condition": "req1"},
            {"from": "grant0", "to": "grant2", "condition": "req2"},
            {"from": "grant0", "to": "grant3", "condition": "req3"},
            {"from": "grant1", "to": "grant2", "condition": "req2"},
            {"from": "grant1", "to": "grant3", "condition": "req3"},
            {"from": "grant1", "to": "grant0", "condition": "req0"},
            {"from": "grant2", "to": "grant3", "condition": "req3"},
            {"from": "grant2", "to": "grant0", "condition": "req0"},
            {"from": "grant2", "to": "grant1", "condition": "req1"},
            {"from": "grant3", "to": "grant0", "condition": "req0"},
            {"from": "grant3", "to": "grant1", "condition": "req1"},
            {"from": "grant3", "to": "grant2", "condition": "req2"},
        ],
    },

    "crc_fsm": {
        "states":      ["idle", "processing", "done"],
        "reset_state": "idle",
        "fsm_outputs": ["shift_en", "load", "crc_valid"],
        "outputs_per_state": {
            "idle":       {"shift_en": "0", "load": "1", "crc_valid": "0"},
            "processing": {"shift_en": "1", "load": "0", "crc_valid": "0"},
            "done":       {"shift_en": "0", "load": "0", "crc_valid": "1"},
        },
        "transitions": [
            {"from": "idle",       "to": "processing", "condition": "start"},
            {"from": "processing", "to": "done",       "condition": "tc",     "priority": 0},
            {"from": "processing", "to": "processing", "condition": "not_tc", "priority": 1},
            {"from": "done",       "to": "idle",       "condition": "1"},
        ],
    },

    "cordic_fsm": {
        "states":      ["idle", "iterating", "done"],
        "reset_state": "idle",
        "fsm_outputs": ["shift_en", "valid_out"],
        "outputs_per_state": {
            "idle":      {"shift_en": "0", "valid_out": "0"},
            "iterating": {"shift_en": "1", "valid_out": "0"},
            "done":      {"shift_en": "0", "valid_out": "1"},
        },
        "transitions": [
            {"from": "idle",      "to": "iterating", "condition": "start"},
            {"from": "iterating", "to": "done",      "condition": "tc",     "priority": 0},
            {"from": "iterating", "to": "iterating", "condition": "not_tc", "priority": 1},
            {"from": "done",      "to": "idle",      "condition": "1"},
        ],
    },

    "mac_fsm": {
        "states":      ["idle", "multiply", "accumulate", "done"],
        "reset_state": "idle",
        "fsm_outputs": ["mul_en", "load", "valid_out"],
        "outputs_per_state": {
            "idle":       {"mul_en": "0", "load": "1", "valid_out": "0"},
            "multiply":   {"mul_en": "1", "load": "0", "valid_out": "0"},
            "accumulate": {"mul_en": "0", "load": "0", "valid_out": "0"},
            "done":       {"mul_en": "0", "load": "0", "valid_out": "1"},
        },
        "transitions": [
            {"from": "idle",       "to": "multiply",   "condition": "start"},
            {"from": "multiply",   "to": "accumulate", "condition": "tc"},
            {"from": "accumulate", "to": "done",       "condition": "tc",     "priority": 0},
            {"from": "accumulate", "to": "multiply",   "condition": "not_tc", "priority": 1},
            {"from": "done",       "to": "idle",       "condition": "1"},
        ],
    },
}


def _counter_sc(sc_id: str, name: str, width: str, role: str,
                x: int, y: int, exports=None, imports=None,
                terminal_value: str = None) -> dict:
    """Helper: create a macro_cfgcounter sub-circuit entry."""
    data = {"width": width, "countDir": 1}
    if terminal_value:
        data["terminalValue"] = terminal_value
    return {
        "id": sc_id, "name": name, "pattern": "macro_cfgcounter",
        "role": role,
        "data": data,
        "exports": exports or [{"signal": "tc", "handle": "tc", "width": "1"}],
        "imports": imports or [
            {"signal": "en",       "handle": "en",       "width": "1", "from": "external"},
            {"signal": "load",     "handle": "load",     "width": "1", "from": "external"},
            {"signal": "load_val", "handle": "load_val", "width": width, "from": "external"},
        ],
        "position": {"x": x, "y": y},
    }


def _fifo_sc(sc_id: str, name: str, width: str, depth: str, role: str,
             x: int, y: int) -> dict:
    """Helper: create a macro_fifo sub-circuit entry."""
    return {
        "id": sc_id, "name": name, "pattern": "macro_fifo",
        "role": role,
        "data": {"width": width, "fifoDepth": depth, "aeThresh": "4"},
        "exports": [
            {"signal": "dout",  "handle": "dout",  "width": width},
            {"signal": "empty", "handle": "empty", "width": "1"},
            {"signal": "full",  "handle": "full",  "width": "1"},
        ],
        "imports": [
            {"signal": "wr_en", "handle": "wr_en", "width": "1",   "from": "external"},
            {"signal": "din",   "handle": "din",   "width": width, "from": "external"},
            {"signal": "rd_en", "handle": "rd_en", "width": "1",   "from": "external"},
        ],
        "position": {"x": x, "y": y},
    }


def _shiftreg_sc(sc_id: str, name: str, width: str, mode: str,
                 direction: str, role: str, x: int, y: int,
                 imports=None, exports=None) -> dict:
    """Helper: create a macro_shiftreg sub-circuit entry."""
    serial_out = mode in ("PISO", "SISO")
    return {
        "id": sc_id, "name": name, "pattern": "macro_shiftreg",
        "role": role,
        "data": {"width": width, "srMode": mode, "shiftDir": direction},
        "exports": exports or ([
            {"signal": "sout", "handle": "sout", "width": "1"}
        ] if serial_out else [
            {"signal": "out", "handle": "out", "width": width}
        ]),
        "imports": imports or [
            {"signal": "din",  "handle": "din",  "width": width, "from": "external"},
            {"signal": "en",   "handle": "en",   "width": "1",   "from": "external"},
            {"signal": "load", "handle": "load", "width": "1",   "from": "external"},
        ],
        "position": {"x": x, "y": y},
    }


_KNOWN_HIERARCHIES: dict[str, dict] = {
    "uart_tx": {
        "description": "UART Transmitter",

        "sub_circuits": [
            _counter_sc("baud_counter", "baud_counter", "16",
                        "Generates baud rate timing — pulses tc every BAUD_DIV clocks",
                        100, 100,
                        exports=[{"signal": "baud_counter_tc", "handle": "tc", "width": "1"}],
                        imports=[
                            {"signal": "en",       "handle": "en",       "width": "1",
                             "from": "tx_fsm", "src_signal": "baud_en"},
                            {"signal": "load",     "handle": "load",     "width": "1",
                             "from": "tx_fsm", "src_signal": "baud_counter_load"},
                            {"signal": "load_val", "handle": "load_val", "width": "16",
                             "from": "external"},
                        ],
                        terminal_value="BAUD_DIV"),
            _fifo_sc("data_fifo", "data_fifo", "8", "16",
                     "Buffers data bytes waiting to be transmitted",
                     100, 350),
            {
                "id": "tx_fsm", "name": "tx_fsm", "pattern": "fsm",
                "role": "Controls UART TX protocol — sequences start, data, stop bits",
                "fsm_states":  ["idle", "start_bit", "data_bits", "stop_bit"],
                "fsm_outputs": ["shift_en", "load", "rd_en", "tx_bit",
                                "baud_en", "bit_counter_load", "baud_counter_load"],
                "imports": [
                    {"signal": "baud_counter_tc", "handle": "baud_counter_tc",
                     "width": "1", "from": "baud_counter", "src_handle": "tc"},
                    {"signal": "empty", "handle": "empty",
                     "width": "1", "from": "data_fifo", "src_handle": "empty"},
                ],
                "exports": [
                    {"signal": "shift_en",           "width": "1"},
                    {"signal": "load",                "width": "1"},
                    {"signal": "rd_en",               "width": "1"},
                    {"signal": "tx_bit",              "width": "1"},
                    {"signal": "baud_en",             "width": "1"},
                    {"signal": "bit_counter_load",    "width": "1"},
                    {"signal": "baud_counter_load",   "width": "1"},
                ],
                "position": {"x": 600, "y": 200},
            },

            _counter_sc("bit_counter", "bit_counter", "4",
                        "Counts DATA_WIDTH baud ticks per byte — resets each byte",
                        600, 500,
                        exports=[{"signal": "bit_counter_tc", "handle": "tc", "width": "1"}],
                        imports=[
                            {"signal": "en",   "handle": "en",   "width": "1",
                             "from": "tx_fsm", "src_signal": "shift_en"},
                            {"signal": "load", "handle": "load", "width": "1",
                             "from": "tx_fsm", "src_signal": "bit_counter_load"},
                            {"signal": "load_val", "handle": "load_val", "width": "4",
                             "from": "external"},
                        ],
                        terminal_value="DATA_WIDTH-1"),
            _shiftreg_sc("shift_reg", "shift_reg", "8", "PISO", "right",
                         "Serializes 8-bit data byte, shifts out LSB first",
                         1100, 200,
                         imports=[
                             {"signal": "din",  "handle": "din",  "width": "8",
                              "from": "data_fifo", "src_handle": "dout"},
                             {"signal": "en",   "handle": "en",   "width": "1",
                              "from": "tx_fsm", "src_signal": "shift_en"},
                             {"signal": "load", "handle": "load", "width": "1",
                              "from": "tx_fsm", "src_signal": "load"},
                         ]),
        ],

        "parameters": {
            "DATA_WIDTH": "8",
            "BAUD_DIV":   "868",
        },

        "top_level_inputs": [
            {"name": "wr_en", "width": "1",          "to": "data_fifo", "dst_handle": "wr_en"},
            {"name": "din",   "width": "DATA_WIDTH",  "to": "data_fifo", "dst_handle": "din"},
        ],
        "top_level_outputs": [

            {"name": "tx_out", "width": "1", "from": "_output_mux", "src_handle": "out"},
        ],

        "signal_list": [

            {
                "name": "baud_counter_tc", "width": "1",
                "driver": "baud_counter",  "driver_handle": "tc",
                "consumers": ["tx_fsm"],
                "reset_value": "0",        "domain": "control",
            },

            {
                "name": "data_fifo_empty", "width": "1",
                "driver": "data_fifo",     "driver_handle": "empty",
                "consumers": ["not_empty_comb"],
                "reset_value": "1",        "domain": "control",
            },
            {
                "name": "data_fifo_dout",  "width": "8",
                "driver": "data_fifo",     "driver_handle": "dout",
                "consumers": ["shift_reg"],
                "reset_value": "0",        "domain": "data",
            },
            {
                "name": "not_empty",       "width": "1",
                "driver": "not_empty_comb", "driver_handle": "out",
                "consumers": ["tx_fsm"],
                "reset_value": "0",        "domain": "control",
                "comb_op": "not",          "comb_input": "data_fifo_empty",
            },
            {

                "name": "shift_en",        "width": "1",
                "driver": "tx_fsm",        "driver_handle": "shift_en",
                "gated_by": "baud_counter_tc",
                "consumers": ["bit_counter", "shift_reg"],
                "reset_value": "0",        "domain": "control",
            },
            {
                "name": "bit_counter_tc",  "width": "1",
                "driver": "bit_counter",   "driver_handle": "tc",
                "consumers": ["not_bit_tc_comb", "tx_fsm"],
                "reset_value": "0",        "domain": "control",
            },
            {
                "name": "not_bit_tc",      "width": "1",
                "driver": "not_bit_tc_comb", "driver_handle": "out",
                "consumers": ["tx_fsm"],
                "reset_value": "1",        "domain": "control",
                "comb_op": "not",          "comb_input": "bit_counter_tc",
            },
    
            {
                "name": "load",            "width": "1",
                "driver": "tx_fsm",        "driver_handle": "load",
                "consumers": ["shift_reg"],
                "reset_value": "0",        "domain": "control",
            },
            {
                "name": "rd_en",           "width": "1",
                "driver": "tx_fsm",        "driver_handle": "rd_en",
                "consumers": ["data_fifo"],
                "reset_value": "0",        "domain": "control",
            },
            {
                "name": "tx_bit",          "width": "1",
                "driver": "tx_fsm",        "driver_handle": "tx_bit",
                "consumers": ["_output_mux"],   # routed through output mux
                "reset_value": "1",        "domain": "control",
            },
            {
                "name": "baud_en",         "width": "1",
                "driver": "tx_fsm",        "driver_handle": "baud_en",
                "consumers": ["baud_counter"],
                "reset_value": "0",        "domain": "control",
            },
            {
                "name": "bit_counter_load", "width": "1",
                "driver": "tx_fsm",         "driver_handle": "bit_counter_load",
                "consumers": ["bit_counter"],
                "reset_value": "0",         "domain": "control",
            },
            {
                "name": "baud_counter_load", "width": "1",
                "driver": "tx_fsm",          "driver_handle": "baud_counter_load",
                "consumers": ["baud_counter"],
                "reset_value": "0",          "domain": "control",
            },

            {
                "name": "shift_reg_sout",  "width": "1",
                "driver": "shift_reg",     "driver_handle": "sout",
                "consumers": ["_output_mux"],
                "reset_value": "1",        "domain": "data",
            },
        ],


        "output_logic": [
            {
                "output":   "tx_out",
                "type":     "state_mux",       
                "fsm":      "tx_fsm",
                "default":  "shift_reg_sout",  
                "overrides": {
                    "idle":      "1'b1",        
                    "read_fifo": "1'b1",        
                    "start_bit": "1'b0",        
                    "stop_bit":  "1'b1",        
                },
            },
        ],


        "reset": {
            "signal":   "rst",
            "polarity": "active_high",  
            "type":     "synchronous",  
        },

        "timing": {
            "clock": "clk",
            "bit_period_ref": "baud_counter",   
            "byte_period_ref": "bit_counter",   
            "state_actions": {
                "idle": {
                    "while": [
                        {"action": "disable", "target": "baud_counter",
                         "via_signal": "baud_en"},
                    ],
                },
                "start_bit": {
                    "entry": [
                        {"action": "load",  "target": "bit_counter",
                         "value": "0", "via_signal": "bit_counter_load"},
                        {"action": "enable", "target": "baud_counter",
                         "via_signal": "baud_en"},
                    ],
                },
                "data_bits": {
                    "while": [
                        {"action": "enable", "target": "baud_counter",
                         "via_signal": "baud_en"},
                        {"action": "enable", "target": "bit_counter",
                         "via_signal": "shift_en"},
                    ],

                    "transition_priority": ["bit_counter_tc", "not_bit_tc"],
                },
                "stop_bit": {
                    "while": [
                        {"action": "enable", "target": "baud_counter",
                         "via_signal": "baud_en"},
                    ],
                },
            },
            "invariants": [
                "bit_counter must be loaded (bit_counter_load=1) on every entry to start_bit",
                "baud_counter must be disabled (baud_en=0) in idle state",
                "tx_out must be 1'b1 in idle and stop_bit states",
                "tx_out must be 1'b0 in start_bit state",
                "tx_out must follow shift_reg_sout in data_bits state",
            ],
        },
    },


    "uart_rx": {
        "description": "UART Receiver",
        "parameters": {"DATA_WIDTH": "8"},
        "sub_circuits": [
            _counter_sc("baud_counter", "baud_counter", "8",
                        "Samples at center of each bit period", 100, 100),
            {
                "id": "rx_fsm", "name": "rx_fsm", "pattern": "fsm",
                "role": "Controls UART RX — detects start, samples data bits",
                "fsm_states":  ["idle", "start_detect", "data_bits", "stop_bit", "done"],
                "fsm_outputs": ["shift_en", "wr_en", "rx_ready"],
                "imports": [
                    {"signal": "tc",        "handle": "tc",        "width": "1",
                     "from": "baud_counter", "src_handle": "tc"},
                    {"signal": "bit_tc",    "handle": "bit_tc",    "width": "1",
                     "from": "bit_counter", "src_handle": "tc"},
                    {"signal": "not_rx_in", "handle": "not_rx_in", "width": "1",
                     "from": "external"},
                ],
                "exports": [
                    {"signal": "shift_en", "width": "1"},
                    {"signal": "wr_en",    "width": "1"},
                    {"signal": "rx_ready", "width": "1"},
                ],
                "position": {"x": 600, "y": 200},
            },
            _counter_sc("bit_counter", "bit_counter", "3",
                        "Counts 8 received bits",
                        600, 500,
                        exports=[{"signal": "bit_tc", "handle": "tc", "width": "1"}],
                        imports=[
                            {"signal": "en",       "handle": "en",       "width": "1",
                             "from": "rx_fsm",   "src_signal": "shift_en"},
                            {"signal": "load",     "handle": "load",     "width": "1",
                             "from": "external"},
                            {"signal": "load_val", "handle": "load_val", "width": "3",
                             "from": "external"},
                        ]),
            _shiftreg_sc("shift_reg", "shift_reg", "8", "SIPO", "right",
                         "Captures incoming serial bits, outputs parallel byte",
                         1100, 200,
                         imports=[
                             {"signal": "sin", "handle": "sin", "width": "1",
                              "from": "external"},
                             {"signal": "en",  "handle": "en",  "width": "1",
                              "from": "rx_fsm", "src_signal": "shift_en"},
                         ],
                         exports=[{"signal": "out", "handle": "out", "width": "8"}]),
            _fifo_sc("rx_fifo", "rx_fifo", "8", "16",
                     "Buffers received bytes for host read",
                     1400, 200),
        ],
        "signal_list": [
            {"name": "rx_in",      "width": "1",
             "driver": "port_in_rx_in", "driver_handle": "out",
             "consumers": ["rx_fsm"], "domain": "control"},
            {"name": "tc",         "width": "1",
             "driver": "baud_counter", "driver_handle": "tc",
             "consumers": ["rx_fsm"], "domain": "control"},
            {"name": "not_rx_in",  "width": "1",
             "driver": "rx_fsm__not_rx_in_comb", "driver_handle": "out",
             "consumers": ["rx_fsm"], "domain": "control",
             "comb_op": "not", "comb_input": "rx_in"},
            {"name": "bit_tc",     "width": "1",
             "driver": "bit_counter", "driver_handle": "tc",
             "consumers": ["rx_fsm"], "domain": "control"},
            {"name": "not_bit_tc", "width": "1",
             "driver": "rx_fsm__not_bit_tc_comb", "driver_handle": "out",
             "consumers": ["rx_fsm"], "domain": "control",
             "comb_op": "not", "comb_input": "bit_tc"},
        ],
        "top_level_inputs": [
            {"name": "rx_in",  "width": "1", "to": None},
            {"name": "rd_en",  "width": "1", "to": "rx_fifo", "dst_handle": "rd_en"},
        ],
        "top_level_outputs": [
            {"name": "dout",     "width": "DATA_WIDTH", "from": "rx_fifo",  "src_handle": "dout"},
            {"name": "rx_ready", "width": "1", "from": "rx_fsm",   "src_signal": "rx_ready"},
        ],
        "reset": {"signal": "rst", "polarity": "active_high", "type": "synchronous"},
    },

    "spi_master": {
        "description": "SPI Master Controller",
        "parameters": {"DATA_WIDTH": "8"},
        "sub_circuits": [
            _counter_sc("spi_clk_div", "spi_clk_div", "8",
                        "Divides system clock to generate SPI clock", 100, 100),
            {
                "id": "spi_fsm", "name": "spi_fsm", "pattern": "fsm",
                "role": "Controls SPI transaction — CS, SCLK, MOSI sequencing",
                "fsm_states":  ["idle", "cs_assert", "transfer", "cs_deassert"],
                "fsm_outputs": ["cs_n", "sclk", "shift_en", "load", "done"],
                "imports": [
                    {"signal": "tc",     "handle": "tc",     "width": "1",
                     "from": "spi_clk_div", "src_handle": "tc"},
                    {"signal": "bit_tc", "handle": "bit_tc", "width": "1",
                     "from": "bit_counter", "src_handle": "tc"},
                    {"signal": "start",  "handle": "start",  "width": "1",
                     "from": "external"},
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
            _counter_sc("bit_counter", "bit_counter", "3",
                        "Counts 8 SPI bits per transfer",
                        600, 500,
                        exports=[{"signal": "bit_tc", "handle": "tc", "width": "1"}],
                        imports=[
                            {"signal": "en",       "handle": "en",       "width": "1",
                             "from": "spi_fsm",  "src_signal": "shift_en"},
                            {"signal": "load",     "handle": "load",     "width": "1",
                             "from": "external"},
                            {"signal": "load_val", "handle": "load_val", "width": "3",
                             "from": "external"},
                        ]),
            _shiftreg_sc("tx_sreg", "tx_sreg", "8", "PISO", "right",
                         "Holds and shifts out MOSI data",
                         1100, 200,
                         imports=[
                             {"signal": "din",  "handle": "din",  "width": "8",
                              "from": "external"},
                             {"signal": "en",   "handle": "en",   "width": "1",
                              "from": "spi_fsm", "src_signal": "shift_en"},
                             {"signal": "load", "handle": "load", "width": "1",
                              "from": "spi_fsm", "src_signal": "load"},
                         ]),
            _shiftreg_sc("rx_sreg", "rx_sreg", "8", "SIPO", "right",
                         "Captures incoming MISO data",
                         1100, 450,
                         imports=[
                             {"signal": "sin", "handle": "sin", "width": "1",
                              "from": "external"},
                             {"signal": "en",  "handle": "en",  "width": "1",
                              "from": "spi_fsm", "src_signal": "shift_en"},
                         ],
                         exports=[{"signal": "out", "handle": "out", "width": "8"}]),
        ],
        "signal_list": [
            {"name": "tc",         "width": "1",
             "driver": "spi_clk_div", "driver_handle": "tc",
             "consumers": ["spi_fsm"], "domain": "control"},
            {"name": "bit_tc",     "width": "1",
             "driver": "bit_counter", "driver_handle": "tc",
             "consumers": ["spi_fsm"], "domain": "control"},
            {"name": "not_bit_tc", "width": "1",
             "driver": "spi_fsm__not_bit_tc_comb", "driver_handle": "out",
             "consumers": ["spi_fsm"], "domain": "control",
             "comb_op": "not", "comb_input": "bit_tc"},
        ],
        "top_level_inputs": [
            {"name": "din",   "width": "DATA_WIDTH", "to": "tx_sreg",  "dst_handle": "din"},
            {"name": "start", "width": "1", "to": "spi_fsm",  "dst_handle": "start"},
            {"name": "miso",  "width": "1", "to": "rx_sreg",  "dst_handle": "sin"},
        ],
        "top_level_outputs": [
            {"name": "mosi",  "width": "1", "from": "tx_sreg",  "src_handle": "sout"},
            {"name": "cs_n",  "width": "1", "from": "spi_fsm",  "src_signal": "cs_n"},
            {"name": "sclk",  "width": "1", "from": "spi_fsm",  "src_signal": "sclk"},
            {"name": "dout",  "width": "DATA_WIDTH", "from": "rx_sreg",  "src_handle": "out"},
            {"name": "done",  "width": "1", "from": "spi_fsm",  "src_signal": "done"},
        ],
        "reset": {"signal": "rst", "polarity": "active_high", "type": "synchronous"},
    },


    "pwm": {
        "description": "PWM Generator",
        "sub_circuits": [
            _counter_sc("period_counter", "period_counter", "8",
                        "Counts the full PWM period", 100, 100,
                        exports=[{"signal": "count",     "handle": "count", "width": "8"},
                                 {"signal": "period_tc", "handle": "tc",    "width": "1"}],
                        imports=[
                            {"signal": "en",       "handle": "en",       "width": "1",
                             "from": "external"},
                            {"signal": "load",     "handle": "load",     "width": "1",
                             "from": "external"},
                            {"signal": "load_val", "handle": "load_val", "width": "8",
                             "from": "external"},
                        ]),
            {
                "id": "duty_cmp", "name": "duty_cmp", "pattern": "comb",
                "role": "Compares counter to duty cycle threshold",
                "data": {"op": "lt", "width": "1"},
                "imports": [
                    {"signal": "in0", "handle": "in0", "width": "8",
                     "from": "period_counter", "src_handle": "count"},
                    {"signal": "in1", "handle": "in1", "width": "8",
                     "from": "external"},
                ],
                "exports": [{"signal": "out", "handle": "out", "width": "1"}],
                "position": {"x": 500, "y": 100},
            },
        ],
        "top_level_inputs": [
            {"name": "duty",   "width": "8", "to": "duty_cmp",      "dst_handle": "in1"},
            {"name": "period", "width": "8", "to": "period_counter", "dst_handle": "load_val"},
        ],
        "top_level_outputs": [
            {"name": "pwm_out", "width": "1", "from": "duty_cmp", "src_handle": "out"},
        ],
        "reset": {"signal": "rst", "polarity": "active_high", "type": "synchronous"},
    },

    "debouncer": {
        "description": "Button Debouncer",
        "sub_circuits": [
            _counter_sc("sample_counter", "sample_counter", "16",
                        "Counts stable samples before accepting button state",
                        100, 100,
                        imports=[
                            {"signal": "en", "handle": "en", "width": "1",
                             "from": "debounce_fsm", "src_signal": "cnt_en"},
                        ]),
            {
                "id": "debounce_fsm", "name": "debounce_fsm", "pattern": "fsm",
                "role": "Waits for stable input before registering button press",
                "fsm_states":  ["idle", "counting", "stable"],
                "fsm_outputs": ["btn_out", "cnt_en"],
                "imports": [
                    {"signal": "tc",      "handle": "tc",      "width": "1",
                     "from": "sample_counter", "src_handle": "tc"},
                    {"signal": "btn_raw", "handle": "btn_raw", "width": "1",
                     "from": "external"},
                ],
                "exports": [
                    {"signal": "btn_out", "width": "1"},
                    {"signal": "cnt_en",  "width": "1"},
                ],
                "position": {"x": 500, "y": 100},
            },
        ],
        "signal_list": [
            {"name": "btn_raw",     "width": "1",
             "driver": "port_in_btn_raw", "driver_handle": "out",
             "consumers": ["debounce_fsm"], "domain": "control"},
            {"name": "tc",          "width": "1",
             "driver": "sample_counter", "driver_handle": "tc",
             "consumers": ["debounce_fsm"], "domain": "control"},
            {"name": "not_btn_raw", "width": "1",
             "driver": "debounce_fsm__not_btn_raw_comb", "driver_handle": "out",
             "consumers": ["debounce_fsm"], "domain": "control",
             "comb_op": "not", "comb_input": "btn_raw"},
        ],
        "top_level_inputs": [
            {"name": "btn_raw", "width": "1", "to": "debounce_fsm", "dst_handle": "btn_raw"},
        ],
        "top_level_outputs": [
            {"name": "btn_out", "width": "1", "from": "debounce_fsm", "src_signal": "btn_out"},
        ],
        "reset": {"signal": "rst", "polarity": "active_high", "type": "synchronous"},
    },

    "clk_divider": {
        "description": "Clock Divider",
        "sub_circuits": [
            _counter_sc("div_counter", "div_counter", "8",
                        "Counts to divide input clock frequency",
                        100, 100),
            {
                "id": "toggle_reg", "name": "toggle_reg", "pattern": "reg",
                "role": "Toggles output on every terminal count to generate divided clock",
                "data": {"width": "1"},
                "imports": [
                    {"signal": "d", "handle": "d", "width": "1", "from": "external"},
                ],
                "exports": [{"signal": "q", "handle": "q", "width": "1"}],
                "position": {"x": 500, "y": 100},
            },
        ],
        "top_level_inputs": [
            {"name": "div_val", "width": "8", "to": "div_counter", "dst_handle": "load_val"},
        ],
        "top_level_outputs": [
            {"name": "clk_out", "width": "1", "from": "div_counter", "src_handle": "tc"},
        ],
        "reset": {"signal": "rst", "polarity": "active_high", "type": "synchronous"},
    },

    "cdc_sync": {
        "description": "2-Flop CDC Synchronizer",
        "sub_circuits": [
            {
                "id": "ff1", "name": "ff1", "pattern": "macro_sync",
                "role": "First synchronization flop — captures metastable signal",
                "data": {"width": "1"},
                "imports": [{"signal": "d", "handle": "d", "width": "1", "from": "external"}],
                "exports": [{"signal": "q", "handle": "q", "width": "1"}],
                "position": {"x": 200, "y": 200},
            },
            {
                "id": "ff2", "name": "ff2", "pattern": "macro_sync",
                "role": "Second synchronization flop — resolved stable output",
                "data": {"width": "1"},
                "imports": [{"signal": "d", "handle": "d", "width": "1",
                             "from": "ff1", "src_handle": "q"}],
                "exports": [{"signal": "q", "handle": "q", "width": "1"}],
                "position": {"x": 500, "y": 200},
            },
        ],
        "top_level_inputs": [
            {"name": "async_in", "width": "1", "to": "ff1", "dst_handle": "d"},
        ],
        "top_level_outputs": [
            {"name": "sync_out", "width": "1", "from": "ff2", "src_handle": "q"},
        ],
        "reset": {"signal": "rst", "polarity": "active_high", "type": "synchronous"},
    },

    "crc_gen": {
        "description": "CRC Generator (CRC-8)",
        "parameters": {"DATA_WIDTH": "8"},
        "sub_circuits": [
            _counter_sc("bit_counter", "bit_counter", "4",
                        "Counts bits being processed", 100, 100,
                        exports=[{"signal": "bit_tc", "handle": "tc", "width": "1"}],
                        imports=[
                            {"signal": "en",       "handle": "en",       "width": "1",
                             "from": "external"},
                            {"signal": "load",     "handle": "load",     "width": "1",
                             "from": "external"},
                            {"signal": "load_val", "handle": "load_val", "width": "4",
                             "from": "external"},
                        ]),
            {
                "id": "crc_fsm", "name": "crc_fsm", "pattern": "fsm",
                "role": "Controls CRC computation — load, process, output",
                "fsm_states":  ["idle", "processing", "done"],
                "fsm_outputs": ["shift_en", "load", "crc_valid"],
                "imports": [
                    {"signal": "start",  "handle": "start",  "width": "1",
                     "from": "external"},
                    {"signal": "tc",     "handle": "tc",     "width": "1",
                     "from": "bit_counter", "src_handle": "tc"},
                ],
                "exports": [
                    {"signal": "shift_en",  "width": "1"},
                    {"signal": "load",      "width": "1"},
                    {"signal": "crc_valid", "width": "1"},
                ],
                "position": {"x": 500, "y": 200},
            },
            _shiftreg_sc("data_reg", "data_reg", "8", "PISO", "right",
                         "Holds input data for CRC computation",
                         900, 200,
                         imports=[
                             {"signal": "din",  "handle": "din",  "width": "8",
                              "from": "external"},
                             {"signal": "en",   "handle": "en",   "width": "1",
                              "from": "crc_fsm", "src_signal": "shift_en"},
                             {"signal": "load", "handle": "load", "width": "1",
                              "from": "crc_fsm", "src_signal": "load"},
                         ]),
        ],
        "signal_list": [
            {"name": "bit_counter_tc", "width": "1",
             "driver": "bit_counter", "driver_handle": "tc",
             "consumers": ["crc_fsm"], "domain": "control"},
            {"name": "tc",     "width": "1",
             "driver": "bit_counter", "driver_handle": "tc",
             "consumers": ["crc_fsm"], "domain": "control"},
            {"name": "not_tc", "width": "1",
             "driver": "crc_fsm__not_tc_comb", "driver_handle": "out",
             "consumers": ["crc_fsm"], "domain": "control",
             "comb_op": "not", "comb_input": "tc"},
        ],
        "top_level_inputs": [
            {"name": "data_in", "width": "DATA_WIDTH", "to": "data_reg", "dst_handle": "din"},
            {"name": "start",   "width": "1", "to": "crc_fsm",  "dst_handle": "start"},
        ],
        "top_level_outputs": [
            {"name": "crc_valid", "width": "1", "from": "crc_fsm", "src_signal": "crc_valid"},
        ],
        "reset": {"signal": "rst", "polarity": "active_high", "type": "synchronous"},
    },

    "mac_unit": {
        "description": "Multiply-Accumulate Unit (MAC)",
        "sub_circuits": [
            _counter_sc("op_counter", "op_counter", "8",
                        "Counts MAC operations for batch processing",
                        100, 100,
                        imports=[
                            {"signal": "en", "handle": "en", "width": "1",
                             "from": "mac_fsm", "src_signal": "mul_en"},
                        ]),
            {
                "id": "mac_fsm", "name": "mac_fsm", "pattern": "fsm",
                "role": "Controls MAC pipeline — multiply then accumulate",
                "fsm_states":  ["idle", "multiply", "accumulate", "done"],
                "fsm_outputs": ["mul_en", "load", "valid_out"],
                "imports": [
                    {"signal": "start", "handle": "start", "width": "1",
                     "from": "external"},
                    {"signal": "tc",    "handle": "tc",    "width": "1",
                     "from": "op_counter", "src_handle": "tc"},
                ],
                "exports": [
                    {"signal": "mul_en",    "width": "1"},
                    {"signal": "load",      "width": "1"},
                    {"signal": "valid_out", "width": "1"},
                ],
                "position": {"x": 500, "y": 200},
            },
        ],
        "signal_list": [
            {"name": "tc",     "width": "1",
             "driver": "op_counter", "driver_handle": "tc",
             "consumers": ["mac_fsm"], "domain": "control"},
            {"name": "not_tc", "width": "1",
             "driver": "mac_fsm__not_tc_comb", "driver_handle": "out",
             "consumers": ["mac_fsm"], "domain": "control",
             "comb_op": "not", "comb_input": "tc"},
        ],
        "top_level_inputs": [
            {"name": "a",     "width": "8", "to": None},
            {"name": "b",     "width": "8", "to": None},
            {"name": "start", "width": "1", "to": "mac_fsm", "dst_handle": "start"},
        ],
        "top_level_outputs": [
            {"name": "result",    "width": "16", "from": None},
            {"name": "valid_out", "width": "1",  "from": "mac_fsm", "src_signal": "valid_out"},
        ],
        "reset": {"signal": "rst", "polarity": "active_high", "type": "synchronous"},
    },

    "axi_lite_slave": {
        "description": "AXI-Lite Slave Interface",
        "sub_circuits": [
            {
                "id": "axi_lite_fsm", "name": "axi_lite_fsm", "pattern": "fsm",
                "role": "Handles AXI-Lite read and write transactions",
                "fsm_states":  ["idle", "read_addr", "read_data",
                                "write_addr", "write_data", "write_resp"],
                "fsm_outputs": ["arready", "rvalid", "awready", "wready", "bvalid"],
                "imports": [
                    {"signal": "arvalid", "handle": "arvalid", "width": "1", "from": "external"},
                    {"signal": "awvalid", "handle": "awvalid", "width": "1", "from": "external"},
                    {"signal": "wvalid",  "handle": "wvalid",  "width": "1", "from": "external"},
                    {"signal": "rready",  "handle": "rready",  "width": "1", "from": "external"},
                    {"signal": "bready",  "handle": "bready",  "width": "1", "from": "external"},
                ],
                "exports": [
                    {"signal": "arready", "width": "1"},
                    {"signal": "rvalid",  "width": "1"},
                    {"signal": "awready", "width": "1"},
                    {"signal": "wready",  "width": "1"},
                    {"signal": "bvalid",  "width": "1"},
                ],
                "position": {"x": 400, "y": 200},
            },
            _fifo_sc("reg_file", "reg_file", "32", "16",
                     "Holds AXI-Lite register map values",
                     800, 200),
        ],
        "top_level_inputs": [
            {"name": "arvalid", "width": "1",  "to": "axi_lite_fsm", "dst_handle": "arvalid"},
            {"name": "araddr",  "width": "32", "to": None},
            {"name": "awvalid", "width": "1",  "to": "axi_lite_fsm", "dst_handle": "awvalid"},
            {"name": "awaddr",  "width": "32", "to": None},
            {"name": "wvalid",  "width": "1",  "to": "axi_lite_fsm", "dst_handle": "wvalid"},
            {"name": "wdata",   "width": "32", "to": None},
            {"name": "rready",  "width": "1",  "to": "axi_lite_fsm", "dst_handle": "rready"},
            {"name": "bready",  "width": "1",  "to": "axi_lite_fsm", "dst_handle": "bready"},
        ],
        "top_level_outputs": [
            {"name": "arready", "width": "1",  "from": "axi_lite_fsm", "src_signal": "arready"},
            {"name": "rvalid",  "width": "1",  "from": "axi_lite_fsm", "src_signal": "rvalid"},
            {"name": "rdata",   "width": "32", "from": "reg_file",      "src_handle": "dout"},
            {"name": "awready", "width": "1",  "from": "axi_lite_fsm", "src_signal": "awready"},
            {"name": "wready",  "width": "1",  "from": "axi_lite_fsm", "src_signal": "wready"},
            {"name": "bvalid",  "width": "1",  "from": "axi_lite_fsm", "src_signal": "bvalid"},
        ],
        "reset": {"signal": "rst", "polarity": "active_high", "type": "synchronous"},
    },

    "rr_arbiter": {
        "description": "4-Port Round-Robin Arbiter",
        "sub_circuits": [
            {
                "id": "rr_fsm", "name": "rr_fsm", "pattern": "fsm",
                "role": "Cycles through 4 request ports in round-robin order",
                "fsm_states":  ["grant0", "grant1", "grant2", "grant3"],
                "fsm_outputs": ["gnt0", "gnt1", "gnt2", "gnt3"],
                "imports": [
                    {"signal": "req0", "handle": "req0", "width": "1", "from": "external"},
                    {"signal": "req1", "handle": "req1", "width": "1", "from": "external"},
                    {"signal": "req2", "handle": "req2", "width": "1", "from": "external"},
                    {"signal": "req3", "handle": "req3", "width": "1", "from": "external"},
                ],
                "exports": [
                    {"signal": "gnt0", "width": "1"},
                    {"signal": "gnt1", "width": "1"},
                    {"signal": "gnt2", "width": "1"},
                    {"signal": "gnt3", "width": "1"},
                ],
                "position": {"x": 400, "y": 200},
            },
        ],
        "top_level_inputs": [
            {"name": "req0", "width": "1", "to": "rr_fsm", "dst_handle": "req0"},
            {"name": "req1", "width": "1", "to": "rr_fsm", "dst_handle": "req1"},
            {"name": "req2", "width": "1", "to": "rr_fsm", "dst_handle": "req2"},
            {"name": "req3", "width": "1", "to": "rr_fsm", "dst_handle": "req3"},
        ],
        "top_level_outputs": [
            {"name": "gnt0", "width": "1", "from": "rr_fsm", "src_signal": "gnt0"},
            {"name": "gnt1", "width": "1", "from": "rr_fsm", "src_signal": "gnt1"},
            {"name": "gnt2", "width": "1", "from": "rr_fsm", "src_signal": "gnt2"},
            {"name": "gnt3", "width": "1", "from": "rr_fsm", "src_signal": "gnt3"},
        ],
        "reset": {"signal": "rst", "polarity": "active_high", "type": "synchronous"},
    },

    "cordic": {
        "description": "CORDIC Sin/Cos Compute Engine",
        "sub_circuits": [
            _counter_sc("iter_counter", "iter_counter", "4",
                        "Counts CORDIC iterations (typically 16)",
                        100, 100,
                        imports=[
                            {"signal": "en", "handle": "en", "width": "1",
                             "from": "cordic_fsm", "src_signal": "shift_en"},
                        ]),
            {
                "id": "cordic_fsm", "name": "cordic_fsm", "pattern": "fsm",
                "role": "Controls CORDIC iteration pipeline",
                "fsm_states":  ["idle", "iterating", "done"],
                "fsm_outputs": ["shift_en", "valid_out"],
                "imports": [
                    {"signal": "start", "handle": "start", "width": "1",
                     "from": "external"},
                    {"signal": "tc",    "handle": "tc",    "width": "1",
                     "from": "iter_counter", "src_handle": "tc"},
                ],
                "exports": [
                    {"signal": "shift_en",  "width": "1"},
                    {"signal": "valid_out", "width": "1"},
                ],
                "position": {"x": 500, "y": 200},
            },
        ],
        "signal_list": [
            {"name": "tc",     "width": "1",
             "driver": "iter_counter", "driver_handle": "tc",
             "consumers": ["cordic_fsm"], "domain": "control"},
            {"name": "not_tc", "width": "1",
             "driver": "cordic_fsm__not_tc_comb", "driver_handle": "out",
             "consumers": ["cordic_fsm"], "domain": "control",
             "comb_op": "not", "comb_input": "tc"},
        ],
        "top_level_inputs": [
            {"name": "angle", "width": "16", "to": None},
            {"name": "start", "width": "1",  "to": "cordic_fsm", "dst_handle": "start"},
        ],
        "top_level_outputs": [
            {"name": "sin_out",   "width": "16", "from": None},
            {"name": "cos_out",   "width": "16", "from": None},
            {"name": "valid_out", "width": "1",  "from": "cordic_fsm", "src_signal": "valid_out"},
        ],
        "reset": {"signal": "rst", "polarity": "active_high", "type": "synchronous"},
    },

    "dma_ctrl": {
        "description": "Single-Channel DMA Controller",
        "sub_circuits": [
            _counter_sc("burst_counter", "burst_counter", "8",
                        "Counts burst length for DMA transfer",
                        100, 100),
            {
                "id": "dma_fsm", "name": "dma_fsm", "pattern": "fsm",
                "role": "Controls DMA bus request, data burst, completion",
                "fsm_states":  ["idle", "req", "burst", "done"],
                "fsm_outputs": ["bus_req", "rd_en", "wr_en", "dma_done"],
                "imports": [
                    {"signal": "dma_req",   "handle": "dma_req",   "width": "1",
                     "from": "external"},
                    {"signal": "bus_grant", "handle": "bus_grant", "width": "1",
                     "from": "external"},
                    {"signal": "tc",        "handle": "tc",        "width": "1",
                     "from": "burst_counter", "src_handle": "tc"},
                ],
                "exports": [
                    {"signal": "bus_req",  "width": "1"},
                    {"signal": "rd_en",    "width": "1"},
                    {"signal": "wr_en",    "width": "1"},
                    {"signal": "dma_done", "width": "1"},
                ],
                "position": {"x": 500, "y": 200},
            },
            _fifo_sc("dma_fifo", "dma_fifo", "32", "16",
                     "Buffers data during DMA burst transfer",
                     900, 200),
        ],
        "top_level_inputs": [
            {"name": "dma_req",   "width": "1",  "to": "dma_fsm",       "dst_handle": "dma_req"},
            {"name": "bus_grant", "width": "1",  "to": "dma_fsm",       "dst_handle": "bus_grant"},
            {"name": "src_data",  "width": "32", "to": "dma_fifo",      "dst_handle": "din"},
            {"name": "burst_len", "width": "8",  "to": "burst_counter", "dst_handle": "load_val"},
        ],
        "top_level_outputs": [
            {"name": "bus_req",  "width": "1",  "from": "dma_fsm",  "src_signal": "bus_req"},
            {"name": "dma_done", "width": "1",  "from": "dma_fsm",  "src_signal": "dma_done"},
            {"name": "dst_data", "width": "32", "from": "dma_fifo", "src_handle": "dout"},
        ],
        "reset": {"signal": "rst", "polarity": "active_high", "type": "synchronous"},
    },
}


def get_circuit_key(prompt: str):
    """
    Classify a prompt against known circuit keywords.
    Returns (circuit_key, hierarchy_dict) or (None, None).
    """
    p = prompt.lower().strip()
    for key, keywords in _CIRCUIT_KEYWORDS.items():
        if any(kw in p for kw in keywords):
            if key in _KNOWN_HIERARCHIES:
                return key, _KNOWN_HIERARCHIES[key]
    return None, None