"""
emit_sync.py
Generates a standalone 2-FF CDC synchronizer Verilog module.
"""


def emit_sync(inst_name: str, width: int = 1) -> tuple[str, str]:
    """
    Returns (module_name, verilog_source).
    """
    width       = max(1, int(width))
    module_name = f"sync2ff_{inst_name}"

    lines = []
    lines.append(f"// Auto-generated: 2-FF CDC Synchronizer — {width}-bit")
    lines.append(f"module {module_name} #(")
    lines.append(f"    parameter WIDTH = {width}")
    lines.append(f") (")
    lines.append(f"    input              clk,")
    lines.append(f"    input  [WIDTH-1:0] d,")
    lines.append(f"    output [WIDTH-1:0] q")
    lines.append(f");\n")
    lines.append(f"    (* ASYNC_REG = \"TRUE\" *) reg [WIDTH-1:0] stage1, stage2;")
    lines.append(f"")
    lines.append(f"    always @(posedge clk) begin")
    lines.append(f"        stage1 <= d;")
    lines.append(f"        stage2 <= stage1;")
    lines.append(f"    end")
    lines.append(f"")
    lines.append(f"    assign q = stage2;")
    lines.append(f"\nendmodule")
    return module_name, "\n".join(lines)


def sync_instantiation(inst_name: str, width: int,
                        d_src: str, q_wire: str) -> str:
    module_name = f"sync2ff_{inst_name}"
    lines = []
    lines.append(f"    {module_name} #(.WIDTH({width})) {inst_name}_inst (")
    lines.append(f"        .clk(clk),")
    lines.append(f"        .d({d_src}),")
    lines.append(f"        .q({q_wire})")
    lines.append(f"    );")
    return "\n".join(lines)