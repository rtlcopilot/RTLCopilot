"""
emit_fifo.py
Generates a standalone synchronous FIFO Verilog module.
"""
import math


def emit_fifo(inst_name: str, depth: int, width: int, ae_thresh: int) -> tuple[str, str]:
    """
    Returns (module_name, verilog_source).
    """
    depth      = max(4,  int(depth))
    width      = max(1,  int(width))
    ae_thresh  = max(1,  int(ae_thresh))
    ptr_bits   = max(1, math.ceil(math.log2(max(depth, 2))))
    cnt_bits   = ptr_bits + 1
    module_name = f"fifo_{inst_name}"

    lines = []
    lines.append(f"// Auto-generated: Synchronous FIFO — depth={depth}, width={width}, ae_thresh={ae_thresh}")
    lines.append(f"module {module_name} #(")
    lines.append(f"    parameter WIDTH     = {width},")
    lines.append(f"    parameter DEPTH     = {depth},")
    lines.append(f"    parameter AE_THRESH = {ae_thresh}")
    lines.append(f") (")
    lines.append(f"    input              clk,")
    lines.append(f"    input              rst,")
    lines.append(f"    input              wr_en,")
    lines.append(f"    input  [WIDTH-1:0] din,")
    lines.append(f"    input              rd_en,")
    lines.append(f"    output reg [WIDTH-1:0] dout,")
    lines.append(f"    output             full,")
    lines.append(f"    output             empty,")
    lines.append(f"    output             almost_empty")
    lines.append(f");\n")

    lines.append(f"    reg [WIDTH-1:0]    mem [0:DEPTH-1];")
    lines.append(f"    reg [{ptr_bits}-1:0] wr_ptr, rd_ptr;")
    lines.append(f"    reg [{cnt_bits}-1:0] count;")
    lines.append(f"    integer i;")
    lines.append(f"")
    lines.append(f"    assign full         = (count == DEPTH);")
    lines.append(f"    assign empty        = (count == 0);")
    lines.append(f"    assign almost_empty = (count <= AE_THRESH);")
    lines.append(f"")
    lines.append(f"    always @(posedge clk) begin")
    lines.append(f"        if (rst) begin")
    lines.append(f"            wr_ptr <= 0; rd_ptr <= 0; count <= 0; dout <= 0;")
    lines.append(f"            for (i = 0; i < DEPTH; i = i + 1) mem[i] <= 0;")
    lines.append(f"        end else begin")
    lines.append(f"            if (wr_en && !full) begin")
    lines.append(f"                mem[wr_ptr] <= din;")
    lines.append(f"                wr_ptr <= wr_ptr + 1;")
    lines.append(f"            end")
    lines.append(f"            if (rd_en && !empty) begin")
    lines.append(f"                dout   <= mem[rd_ptr];")
    lines.append(f"                rd_ptr <= rd_ptr + 1;")
    lines.append(f"            end")
    lines.append(f"            case ({{(wr_en && !full), (rd_en && !empty)}})")
    lines.append(f"                2'b10: count <= count + 1;")
    lines.append(f"                2'b01: count <= count - 1;")
    lines.append(f"                default: count <= count;")
    lines.append(f"            endcase")
    lines.append(f"        end")
    lines.append(f"    end")
    lines.append(f"\nendmodule")
    return module_name, "\n".join(lines)


def fifo_instantiation(inst_name: str, depth: int, width: int, ae_thresh: int,
                        wr_en_src: str, din_src: str, rd_en_src: str,
                        dout_wire: str, full_wire: str,
                        empty_wire: str, ae_wire: str) -> str:
    module_name = f"fifo_{inst_name}"
    lines = []
    lines.append(f"    {module_name} #(.WIDTH({width}), .DEPTH({depth}), .AE_THRESH({ae_thresh})) {inst_name}_inst (")
    lines.append(f"        .clk(clk),")
    lines.append(f"        .rst(rst),")
    lines.append(f"        .wr_en({wr_en_src}),")
    lines.append(f"        .din({din_src}),")
    lines.append(f"        .rd_en({rd_en_src}),")
    lines.append(f"        .dout({dout_wire}),")
    lines.append(f"        .full({full_wire}),")
    lines.append(f"        .empty({empty_wire}),")
    lines.append(f"        .almost_empty({ae_wire})")
    lines.append(f"    );")
    return "\n".join(lines)