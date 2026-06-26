"""
emit_counter.py
Generates a standalone synchronous up-counter Verilog module.
"""


def emit_counter(inst_name: str, width: int) -> tuple[str, str]:
    """
    Returns (module_name, verilog_source).
    """
    width       = max(1, int(width))
    module_name = f"counter_{inst_name}"

    lines = []
    lines.append(f"// Auto-generated: Synchronous Up-Counter — {width}-bit")
    lines.append(f"module {module_name} #(")
    lines.append(f"    parameter WIDTH = {width}")
    lines.append(f") (")
    lines.append(f"    input              clk,")
    lines.append(f"    input              rst,")
    lines.append(f"    input              en,")
    lines.append(f"    input              res,")
    lines.append(f"    output reg [WIDTH-1:0] out")
    lines.append(f");\n")
    lines.append(f"    always @(posedge clk) begin")
    lines.append(f"        if (rst || res)")
    lines.append(f"            out <= {{WIDTH{{1'b0}}}};")
    lines.append(f"        else if (en)")
    lines.append(f"            out <= out + 1'b1;")
    lines.append(f"    end")
    lines.append(f"\nendmodule")
    return module_name, "\n".join(lines)


def counter_instantiation(inst_name: str, width: int,
                           en_src: str, res_src: str,
                           out_wire: str) -> str:
    module_name = f"counter_{inst_name}"
    en_tied  = en_src  if en_src  != "0" else "1'b1"
    res_tied = res_src if res_src != "0" else "1'b0"
    lines = []
    lines.append(f"    {module_name} #(.WIDTH({width})) {inst_name}_inst (")
    lines.append(f"        .clk(clk),")
    lines.append(f"        .rst(rst),")
    lines.append(f"        .en({en_tied}),")
    lines.append(f"        .res({res_tied}),")
    lines.append(f"        .out({out_wire})")
    lines.append(f"    );")
    return "\n".join(lines)