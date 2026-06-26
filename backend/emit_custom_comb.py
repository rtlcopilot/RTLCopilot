"""
emit_custom_comb.py
Deterministic Verilog generator for combinational custom blocks.

No clock, no reset, no internal state. All outputs are pure functions
of current inputs — emitted as assign statements or a combinational
always @(*) block.

Schema config fields:
  outputs : list of output config dicts:
    {
      "port"      : str  — output port name
      "mode"      : "add"         — out = a + b
                  | "sub"         — out = a - b
                  | "mul"         — out = a * b
                  | "and"         — out = a & b
                  | "or"          — out = a | b
                  | "xor"         — out = a ^ b
                  | "not"         — out = ~a
                  | "eq"          — out = (a == b)
                  | "neq"         — out = (a != b)
                  | "lt"          — out = (a < b)
                  | "lte"         — out = (a <= b)
                  | "gt"          — out = (a > b)
                  | "gte"         — out = (a >= b)
                  | "mux"         — out = sel ? b : a
                  | "shl"         — out = a << b
                  | "shr"         — out = a >> b
                  | "concat"      — out = {a, b}
                  | "passthrough" — out = a
                  | "sat_add"     — saturating add: out = (a+b overflows) ? MAX : a+b
                  | "sat_sub"     — saturating sub: out = (a<b) ? 0 : a-b
      "operand_a" : str  — first input port name or integer literal
      "operand_b" : str  — second input port name or integer literal (if needed)
    }
"""


def _width_decl(w):
    """Returns '[W-1:0] ' for multi-bit or '' for 1-bit."""
    try:
        return f"[{int(w)}-1:0] " if int(w) > 1 else ""
    except (ValueError, TypeError):
        return f"[{w}-1:0] "


def emit_custom_comb(schema: dict) -> str:
    """
    Takes a validated custom block schema dict.
    Returns a Verilog string for the complete combinational module.
    """
    name           = schema["name"]
    ports          = schema["ports"]
    config         = schema.get("config", {})
    description    = schema.get("description", "")
    output_configs = config.get("outputs", [])

    input_ports  = [p for p in ports if p["dir"] == "input"  and p["name"] not in ("clk", "rst")]
    output_ports = [p for p in ports if p["dir"] == "output"]

    L = []


    L.append(f"// Auto-generated custom block: {name}")
    if description:
        L.append(f"// {description}")
    L.append(f"module {name} (")

    port_lines = []
    for i, p in enumerate(input_ports):
        prefix = "    " if i == 0 else "    ,"
        w      = p["width"]
        decl   = _width_decl(w)
        port_lines.append(f"{prefix}input  wire {decl}{p['name']}")
    for p in output_ports:
        w    = p["width"]
        decl = _width_decl(w)
        port_lines.append(f"    ,output wire {decl}{p['name']}")

    L.append("\n".join(port_lines))
    L.append(");")
    L.append("")

    out_width_map = {p["name"]: p["width"] for p in output_ports}

    L.append("    // Combinational output logic")

    for out_cfg in output_configs:
        port_name = out_cfg.get("port", "").strip()
        mode      = out_cfg.get("mode", "passthrough").strip()
        a         = out_cfg.get("operand_a", "0").strip()
        b         = out_cfg.get("operand_b", "0").strip()

        if not port_name:
            continue

        ow = out_width_map.get(port_name, "1")

        if mode == "passthrough":
            L.append(f"    assign {port_name} = {a};")

        elif mode == "not":
            L.append(f"    assign {port_name} = ~{a};")

        elif mode in ("add", "sub", "mul", "and", "or", "xor", "shl", "shr"):
            op_map = {
                "add": "+", "sub": "-", "mul": "*",
                "and": "&", "or":  "|", "xor": "^",
                "shl": "<<","shr": ">>",
            }
            op = op_map[mode]
            L.append(f"    assign {port_name} = {a} {op} {b};")

        elif mode in ("eq", "neq", "lt", "lte", "gt", "gte"):
            op_map = {
                "eq": "==", "neq": "!=",
                "lt": "<",  "lte": "<=",
                "gt": ">",  "gte": ">=",
            }
            op = op_map[mode]
            L.append(f"    assign {port_name} = ({a} {op} {b});")

        elif mode == "mux":

            sel = next((p["name"] for p in input_ports if str(p.get("width","1")) == "1"
                        and p["name"] not in (a, b)), b)
            L.append(f"    assign {port_name} = {sel} ? {b} : {a};")

        elif mode == "concat":
            L.append(f"    assign {port_name} = {{{a}, {b}}};")

        elif mode == "sat_add":
            try:
                w_int = int(ow)
                L.append(f"    wire [{w_int}:0] _sat_add_{port_name} = {{1'b0,{a}}} + {{1'b0,{b}}};")
                L.append(f"    assign {port_name} = _sat_add_{port_name}[{w_int}] ? {{{w_int}{{1'b1}}}} : _sat_add_{port_name}[{w_int-1}:0];")
            except (ValueError, TypeError):
                L.append(f"    assign {port_name} = {a} + {b};")

        elif mode == "sat_sub":
            L.append(f"    assign {port_name} = ({a} >= {b}) ? ({a} - {b}) : 0;")

        else:

            L.append(f"    assign {port_name} = {a};  // fallback: unknown mode '{mode}'")

    L.append("")
    L.append("endmodule")

    return "\n".join(L)