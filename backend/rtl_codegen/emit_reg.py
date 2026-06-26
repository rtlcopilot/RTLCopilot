"""
emit_reg.py
Generates a standalone synchronous D flip-flop / register Verilog module.
"""


def emit_reg(inst_name: str, width: int) -> tuple[str, str]:
    """
    Returns (module_name, verilog_source).
    """
    width       = max(1, int(width))
    module_name = f"reg_{inst_name}"

    lines = []
    lines.append(f"// Auto-generated: D Flip-Flop / Register — {width}-bit")
    lines.append(f"module {module_name} #(")
    lines.append(f"    parameter WIDTH = {width}")
    lines.append(f") (")
    lines.append(f"    input              clk,")
    lines.append(f"    input              rst,")
    lines.append(f"    input  [WIDTH-1:0] d,")
    lines.append(f"    output reg [WIDTH-1:0] q")
    lines.append(f");\n")
    lines.append(f"    always @(posedge clk) begin")
    lines.append(f"        if (rst)")
    lines.append(f"            q <= {{WIDTH{{1'b0}}}};")
    lines.append(f"        else")
    lines.append(f"            q <= d;")
    lines.append(f"    end")
    lines.append(f"\nendmodule")
    return module_name, "\n".join(lines)


def reg_instantiation(inst_name: str, width: int,
                       d_src: str, q_wire: str) -> str:
    module_name = f"reg_{inst_name}"
    d_tied = d_src if d_src != "0" else f"{width}'b0"
    lines = []
    lines.append(f"    {module_name} #(.WIDTH({width})) {inst_name}_inst (")
    lines.append(f"        .clk(clk),")
    lines.append(f"        .rst(rst),")
    lines.append(f"        .d({d_tied}),")
    lines.append(f"        .q({q_wire})")
    lines.append(f"    );")
    return "\n".join(lines)