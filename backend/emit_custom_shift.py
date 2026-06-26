"""
emit_custom_shift.py
Deterministic Verilog generator for shift-based custom blocks.

Covers: delay lines, LFSRs, serial-to-parallel converters,
data scramblers, CRC generator steps.

Schema config fields:
  shift_width    : int    — bit width of each stage (1 for serial, N for parallel)
  depth          : int    — number of stages
  shift_dir      : "left" | "right"
  has_enable     : bool   — shift only when enable is high
  enable_port    : str    — name of the 1-bit enable input
  feedback_mode  : "none" | "xor"
  feedback_taps  : list[int] — bit positions XORed back to input (LFSR)
  has_load       : bool   — parallel load supported
  load_port      : str    — name of the parallel load data input
  load_en_port   : str    — name of the 1-bit load enable input
  outputs        : list of output config dicts:
    {
      "port"  : str  — output port name
      "mode"  : "last_stage"   — output the final shift stage
              | "full_reg"     — output the entire shift register
              | "stage"        — output a specific stage index
              | "xor_all"      — XOR all stages together (parity)
      "stage_index" : int      — which stage (for mode "stage")
    }
"""
import math


def emit_custom_shift(schema: dict) -> str:
    """
    Takes a validated custom block schema dict.
    Returns a Verilog string for the complete shift-based module.
    """
    name        = schema["name"]
    ports       = schema["ports"]
    config      = schema.get("config", {})
    description = schema.get("description", "")
    internal    = schema.get("internal_signals", [])

    shift_width = int(config.get("shift_width", 1))
    depth       = int(config.get("depth", 8))

    if "shift_width" not in config and "depth" not in config:
        for sig in internal:
            n = sig["name"].lower()
            if any(kw in n for kw in ("shift", "sreg", "sr", "lfsr", "delay", "pipe")):
                try:
                    w = int(sig["width"])
                    depth       = w
                    shift_width = 1
                except Exception:
                    pass
                break

    shift_dir     = config.get("shift_dir", "left")
    has_enable    = bool(config.get("has_enable", False))
    enable_port   = config.get("enable_port", "").strip()
    feedback_mode = config.get("feedback_mode", "none")
    feedback_taps = config.get("feedback_taps", [])
    has_load      = bool(config.get("has_load", False))
    load_port     = config.get("load_port", "").strip()
    load_en_port  = config.get("load_en_port", "").strip()
    output_configs = config.get("outputs", [])

    input_ports  = [p for p in ports if p["dir"] == "input"  and p["name"] not in ("clk", "rst")]
    output_ports = [p for p in ports if p["dir"] == "output"]

    control_ports = {enable_port, load_port, load_en_port} - {""}
    data_inputs   = [p for p in input_ports if p["name"] not in control_ports]
    serial_in     = data_inputs[0]["name"] if data_inputs else "1'b0"

    total_width = depth * shift_width

    L = []

    L.append(f"// Auto-generated custom block: {name}")
    if description:
        L.append(f"// {description}")
    L.append(f"module {name} (")

    port_lines = []
    port_lines.append(f"    input  wire        clk")
    port_lines.append(f"    ,input  wire        rst")
    for p in input_ports:
        w    = p["width"]
        decl = f"[{w}-1:0] " if str(w) != "1" else ""
        port_lines.append(f"    ,input  wire {decl}{p['name']}")
    for p in output_ports:
        w    = p["width"]
        decl = f"[{w}-1:0] " if str(w) != "1" else ""
        port_lines.append(f"    ,output reg  {decl}{p['name']}")
    L.append("\n".join(port_lines))
    L.append(");")
    L.append("")

    L.append(f"    // Internal shift register: {depth} stages x {shift_width}-bit")
    L.append(f"    reg [{total_width}-1:0] _sreg;")
    L.append("")

    feedback_expr = serial_in
    if feedback_mode == "xor" and feedback_taps:
        tap_bits = " ^ ".join([f"_sreg[{t}]" for t in feedback_taps if t < total_width])
        if tap_bits:
            feedback_expr = f"({serial_in} ^ {tap_bits})"


    L.append(f"    // Shift logic")
    L.append(f"    always @(posedge clk or posedge rst) begin")
    L.append(f"        if (!rst) begin")
    L.append(f"            _sreg <= 0;")
    L.append(f"        end else begin")

    if has_load and load_port and load_en_port:
        L.append(f"            if ({load_en_port}) begin")
        L.append(f"                _sreg <= {load_port};")
        L.append(f"            end else", )

    shift_body_indent = "            " if not (has_load and load_port and load_en_port) else "            else "

    if has_enable and enable_port:
        if has_load and load_port and load_en_port:
            L.append(f"            if ({enable_port}) begin")
        else:
            L.append(f"            if ({enable_port}) begin")

        if shift_dir == "right":
            L.append(f"                _sreg <= {{{feedback_expr}, _sreg[{total_width}-1:{shift_width}]}};")
        else:
            L.append(f"                _sreg <= {{_sreg[{total_width}-{shift_width}-1:0], {feedback_expr}}};")
        L.append(f"            end")
    else:
        if has_load and load_port and load_en_port:
            L.append(f"            begin")

        if shift_dir == "right":
            L.append(f"                _sreg <= {{{feedback_expr}, _sreg[{total_width}-1:{shift_width}]}};")
        else:
            L.append(f"                _sreg <= {{_sreg[{total_width}-{shift_width}-1:0], {feedback_expr}}};")

        if has_load and load_port and load_en_port:
            L.append(f"            end")

    L.append(f"        end")
    L.append(f"    end")
    L.append("")

    L.append(f"    // Output logic")
    L.append(f"    always @(*) begin")
    for p in output_ports:
        L.append(f"        {p['name']} = 0;")

    for out_cfg in output_configs:
        port_name   = out_cfg.get("port", "").strip()
        mode        = out_cfg.get("mode", "last_stage")
        stage_index = int(out_cfg.get("stage_index", depth - 1))

        if not port_name:
            continue

        if mode == "full_reg":
            L.append(f"        {port_name} = _sreg;")

        elif mode == "last_stage":
            if shift_dir == "right":

                hi = shift_width - 1
                lo = 0
            else:

                hi = total_width - 1
                lo = total_width - shift_width
            if shift_width == 1:
                L.append(f"        {port_name} = _sreg[{hi}];")
            else:
                L.append(f"        {port_name} = _sreg[{hi}:{lo}];")

        elif mode == "stage":
            idx = min(stage_index, depth - 1)
            if shift_dir == "right":
                hi = total_width - 1 - idx * shift_width
                lo = hi - shift_width + 1
            else:
                lo = idx * shift_width
                hi = lo + shift_width - 1
            if shift_width == 1:
                L.append(f"        {port_name} = _sreg[{hi}];")
            else:
                L.append(f"        {port_name} = _sreg[{hi}:{lo}];")

        elif mode == "xor_all":

            L.append(f"        {port_name} = ^_sreg;")

    L.append(f"    end")
    L.append("")
    L.append("endmodule")

    return "\n".join(L)