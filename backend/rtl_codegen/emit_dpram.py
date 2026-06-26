"""
emit_dpram.py
Generates a standalone dual-port RAM Verilog module.
"""


def emit_dpram(inst_name: str, data_width: int, addr_width: int) -> tuple[str, str]:
    """
    Returns (module_name, verilog_source).
    depth = 2**addr_width
    """
    data_width  = max(1,  int(data_width))
    addr_width  = max(1,  int(addr_width))
    module_name = f"dpram_{inst_name}"

    lines = []
    lines.append(f"// Auto-generated: Dual-Port RAM — data={data_width}b addr={addr_width}b depth={2**addr_width}")
    lines.append(f"module {module_name} #(")
    lines.append(f"    parameter DATA_WIDTH = {data_width},")
    lines.append(f"    parameter ADDR_WIDTH = {addr_width}")
    lines.append(f") (")
    lines.append(f"    input  wire                      clk,")
    lines.append(f"    // Port A")
    lines.append(f"    input  wire                      we_a,")
    lines.append(f"    input  wire [ADDR_WIDTH-1:0]     addr_a,")
    lines.append(f"    input  wire [DATA_WIDTH-1:0]     din_a,")
    lines.append(f"    output reg  [DATA_WIDTH-1:0]     dout_a,")
    lines.append(f"    // Port B")
    lines.append(f"    input  wire                      we_b,")
    lines.append(f"    input  wire [ADDR_WIDTH-1:0]     addr_b,")
    lines.append(f"    input  wire [DATA_WIDTH-1:0]     din_b,")
    lines.append(f"    output reg  [DATA_WIDTH-1:0]     dout_b")
    lines.append(f");\n")
    lines.append(f"    localparam DEPTH = (1 << ADDR_WIDTH);")
    lines.append(f"    reg [DATA_WIDTH-1:0] mem [0:DEPTH-1];")
    lines.append(f"")
    lines.append(f"    // Port A: Read-First")
    lines.append(f"    always @(posedge clk) begin")
    lines.append(f"        dout_a <= mem[addr_a];")
    lines.append(f"        if (we_a)")
    lines.append(f"            mem[addr_a] <= din_a;")
    lines.append(f"    end")
    lines.append(f"")
    lines.append(f"    // Port B: Read-First")
    lines.append(f"    always @(posedge clk) begin")
    lines.append(f"        dout_b <= mem[addr_b];")
    lines.append(f"        if (we_b)")
    lines.append(f"            mem[addr_b] <= din_b;")
    lines.append(f"    end")
    lines.append(f"\nendmodule")
    return module_name, "\n".join(lines)


def dpram_instantiation(inst_name: str, data_width: int, addr_width: int,
                         we_a_src: str,   addr_a_src: str, din_a_src: str,
                         we_b_src: str,   addr_b_src: str, din_b_src: str,
                         dout_a_wire: str, dout_b_wire: str) -> str:
    module_name = f"dpram_{inst_name}"
    lines = []
    lines.append(f"    {module_name} #(.DATA_WIDTH({data_width}), .ADDR_WIDTH({addr_width})) {inst_name}_inst (")
    lines.append(f"        .clk(clk),")
    lines.append(f"        .we_a({we_a_src}),")
    lines.append(f"        .addr_a({addr_a_src}),")
    lines.append(f"        .din_a({din_a_src}),")
    lines.append(f"        .dout_a({dout_a_wire}),")
    lines.append(f"        .we_b({we_b_src}),")
    lines.append(f"        .addr_b({addr_b_src}),")
    lines.append(f"        .din_b({din_b_src}),")
    lines.append(f"        .dout_b({dout_b_wire})")
    lines.append(f"    );")
    return "\n".join(lines)