"""
emit_custom_register.py
Deterministic Verilog generator for register-based custom blocks.

Covers: accumulators, pipeline registers, sample-and-hold,
peak detectors, running min/max, enable-gated registers.

Schema config fields:
  reg_width      : int    — bit width of the internal register
  has_enable     : bool   — only update when enable input is high
  enable_port    : str    — name of the 1-bit enable input (if has_enable)
  reset_value    : str    — value on rst, e.g. "0" or "255"
  feedback_mode  : "none" | "add" | "sub" | "max" | "min"
  feedback_port  : str    — input port used in feedback expression
  outputs        : list of output config dicts:
    {
      "port"    : str  — output port name
      "mode"    : "passthrough" | "eq" | "gt" | "lt" | "gte" | "lte"
      "operand" : str  — port name or integer to compare against
    }
"""


def emit_custom_register(schema: dict) -> str:
    """
    Takes a validated custom block schema dict.
    Returns a Verilog string for the complete register-based module.
    """
    name        = schema["name"]
    ports       = schema["ports"]
    config      = schema.get("config", {})
    description = schema.get("description", "")
    internal    = schema.get("internal_signals", [])


    reg_width = int(config.get("reg_width", 8))
    for sig in internal:
        n = sig["name"].lower()
        if any(kw in n for kw in ("reg", "acc", "store", "val", "data", "sample", "peak")):
            try:
                reg_width = int(sig["width"])
            except Exception:
                pass
            break

    has_enable    = bool(config.get("has_enable", False))
    enable_port   = config.get("enable_port", "").strip()
    reset_value   = config.get("reset_value", "0")
    feedback_mode = config.get("feedback_mode", "none")
    feedback_port = config.get("feedback_port", "").strip()
    output_configs = config.get("outputs", [])

    input_ports  = [p for p in ports if p["dir"] == "input"  and p["name"] not in ("clk", "rst")]
    output_ports = [p for p in ports if p["dir"] == "output"]

    data_inputs = [p for p in input_ports if p["name"] != enable_port]
    primary_input = data_inputs[0]["name"] if data_inputs else "0"

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

    L.append(f"    // Internal register")
    L.append(f"    reg [{reg_width}-1:0] _reg;")
    L.append("")

    if feedback_mode == "add":
        fp = feedback_port or primary_input
        next_val = f"_reg + {fp}"
    elif feedback_mode == "sub":
        fp = feedback_port or primary_input
        next_val = f"_reg - {fp}"
    elif feedback_mode == "max":
        fp = feedback_port or primary_input
        next_val = f"(_reg > {fp}) ? _reg : {fp}"
    elif feedback_mode == "min":
        fp = feedback_port or primary_input
        next_val = f"(_reg < {fp}) ? _reg : {fp}"
    else:
        next_val = primary_input

    L.append(f"    // Register logic")
    L.append(f"    always @(posedge clk or posedge rst) begin")
    L.append(f"        if (!rst) begin")
    L.append(f"            _reg <= {reset_value};")
    L.append(f"        end else begin")

    if has_enable and enable_port:
        L.append(f"            if ({enable_port}) begin")
        L.append(f"                _reg <= {next_val};")
        L.append(f"            end")
    else:
        L.append(f"            _reg <= {next_val};")

    L.append(f"        end")
    L.append(f"    end")
    L.append("")

    op_map = {
        "eq":  "==", "gt": ">",  "lt": "<",
        "gte": ">=", "lte": "<=",
    }

    L.append(f"    // Output logic")
    L.append(f"    always @(*) begin")
    for p in output_ports:
        L.append(f"        {p['name']} = 0;")

    for out_cfg in output_configs:
        port_name = out_cfg.get("port", "").strip()
        mode      = out_cfg.get("mode", "passthrough")
        operand   = out_cfg.get("operand", "").strip()

        if not port_name:
            continue

        if mode == "passthrough":
            L.append(f"        {port_name} = _reg;")
        elif mode in op_map:
            op  = op_map[mode]
            cmp = operand if operand else "0"
            L.append(f"        {port_name} = (_reg {op} {cmp});")

    L.append(f"    end")
    L.append("")
    L.append("endmodule")

    return "\n".join(L)