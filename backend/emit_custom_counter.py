"""
emit_custom_counter.py
Deterministic Verilog generator for counter-based custom blocks.

Schema config fields:
  count_dir        : "up" | "down"
  count_width      : int — width of internal counter (from internal signals)
  reset_condition  : "input_port" | "fixed_value" | "free_running"
  reset_port       : str — port name (when reset_condition == "input_port")
  reset_value      : int — fixed value (when reset_condition == "fixed_value")
  outputs          : list of output config dicts:
    {
      "port"      : str  — output port name
      "mode"      : "lt" | "lte" | "gt" | "gte" | "eq" | "terminal" | "passthrough"
      "operand"   : str  — port name or integer literal to compare against
    }
"""


def emit_custom_counter(schema: dict) -> str:
    """
    Takes a validated custom block schema dict.
    Returns a Verilog string for the complete module.
    """
    name        = schema["name"]
    ports       = schema["ports"]
    config      = schema.get("config", {})
    description = schema.get("description", "")
    internal    = schema.get("internal_signals", [])

    count_width = int(config.get("count_width", 8))
    for sig in internal:
        if "counter" in sig["name"].lower() or "cnt" in sig["name"].lower() or "count" in sig["name"].lower():
            try:
                count_width = int(sig["width"])
            except Exception:
                pass
            break

    count_dir       = config.get("count_dir", "up")
    reset_condition = config.get("reset_condition", "free_running")
    reset_port      = config.get("reset_port", "")
    reset_value     = config.get("reset_value", 0)
    output_configs  = config.get("outputs", [])


    input_ports  = [p for p in ports if p["dir"] == "input"  and p["name"] not in ("clk", "rst")]
    output_ports = [p for p in ports if p["dir"] == "output"]

    L = []

    L.append(f"// Auto-generated custom block: {name}")
    if description:
        L.append(f"// {description}")
    L.append(f"module {name} (")

    port_lines = []
    port_lines.append(f"    input  wire        clk")
    port_lines.append(f"    ,input  wire        rst")
    for p in input_ports:
        w     = p["width"]
        decl  = f"[{w}-1:0] " if str(w) != "1" else ""
        port_lines.append(f"    ,input  wire {decl}{p['name']}")
    for p in output_ports:
        w     = p["width"]
        decl  = f"[{w}-1:0] " if str(w) != "1" else ""
        port_lines.append(f"    ,output reg  {decl}{p['name']}")
    L.append("\n".join(port_lines))
    L.append(");")
    L.append("")


    L.append(f"    // Internal counter")
    L.append(f"    reg [{count_width}-1:0] _counter;")
    L.append("")


    if reset_condition == "input_port" and reset_port:
        terminal_expr = f"_counter >= {reset_port} - 1"
        reset_expr    = reset_port
    elif reset_condition == "fixed_value":
        terminal_expr = f"_counter >= {reset_value} - 1"
        reset_expr    = str(reset_value)
    else:
        terminal_expr = "1'b0"  
        reset_expr    = None


    L.append(f"    // Counter logic")
    L.append(f"    always @(posedge clk or posedge rst) begin")
    L.append(f"        if (!rst) begin")
    L.append(f"            _counter <= 0;")
    L.append(f"        end else begin")

    if reset_condition != "free_running" and reset_expr:
        L.append(f"            if ({terminal_expr})")
        L.append(f"                _counter <= 0;")
        L.append(f"            else")
        if count_dir == "down":
            L.append(f"                _counter <= _counter - 1;")
        else:
            L.append(f"                _counter <= _counter + 1;")
    else:
        if count_dir == "down":
            L.append(f"            _counter <= _counter - 1;")
        else:
            L.append(f"            _counter <= _counter + 1;")

    L.append(f"        end")
    L.append(f"    end")
    L.append("")

    L.append(f"    // Output logic")
    L.append(f"    always @(*) begin")

    for p in output_ports:
        L.append(f"        {p['name']} = 0;")

    op_map = {
        "lt":  "<",
        "lte": "<=",
        "gt":  ">",
        "gte": ">=",
        "eq":  "==",
    }

    for out_cfg in output_configs:
        port_name = out_cfg.get("port", "")
        mode      = out_cfg.get("mode", "passthrough")
        operand   = out_cfg.get("operand", "0")

        if not port_name:
            continue

        if mode == "terminal":
            L.append(f"        if ({terminal_expr})")
            L.append(f"            {port_name} = 1'b1;")
        elif mode == "passthrough":
            L.append(f"        {port_name} = _counter;")
        elif mode in op_map:
            op = op_map[mode]
            L.append(f"        if (_counter {op} {operand})")
            L.append(f"            {port_name} = 1'b1;")

    L.append(f"    end")
    L.append("")
    L.append("endmodule")

    return "\n".join(L)