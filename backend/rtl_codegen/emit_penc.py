"""
emit_penc.py
Generates a standalone parameterized priority encoder Verilog module.
"""
import math


def emit_penc(inst_name: str, width: int, lsb_priority: int = 0) -> tuple[str, str]:
    """
    Returns (module_name, verilog_source).

    lsb_priority: 0 = MSB has highest priority, 1 = LSB has highest priority
    """
    width       = max(2, int(width))
    idx_bits    = max(1, math.ceil(math.log2(max(width, 2))))
    module_name = f"penc_{inst_name}"
    pri_str     = "LSB" if lsb_priority else "MSB"

    lines = []
    lines.append(f"// Auto-generated: Priority Encoder — width={width}, {pri_str} priority")
    lines.append(f"module {module_name} #(")
    lines.append(f"    parameter WIDTH        = {width},")
    lines.append(f"    parameter LSB_PRIORITY = {lsb_priority}")
    lines.append(f") (")
    lines.append(f"    input  [WIDTH-1:0]    data_in,")
    lines.append(f"    output reg [{idx_bits}-1:0] index,")
    lines.append(f"    output reg            valid")
    lines.append(f");\n")
    lines.append(f"    integer i;")
    lines.append(f"    always @(*) begin")
    lines.append(f"        index = {idx_bits}'b0;")
    lines.append(f"        valid = 1'b0;")
    lines.append(f"        if (LSB_PRIORITY) begin")
    lines.append(f"            for (i = 0; i < WIDTH; i = i + 1)")
    lines.append(f"                if (!valid && data_in[i]) begin")
    lines.append(f"                    index = i[{idx_bits}-1:0];")
    lines.append(f"                    valid = 1'b1;")
    lines.append(f"                end")
    lines.append(f"        end else begin")
    lines.append(f"            for (i = WIDTH-1; i >= 0; i = i - 1)")
    lines.append(f"                if (!valid && data_in[i]) begin")
    lines.append(f"                    index = i[{idx_bits}-1:0];")
    lines.append(f"                    valid = 1'b1;")
    lines.append(f"                end")
    lines.append(f"        end")
    lines.append(f"    end")
    lines.append(f"\nendmodule")
    return module_name, "\n".join(lines)


def penc_instantiation(inst_name: str, width: int, lsb_priority: int,
                        data_in_src: str,
                        index_wire: str, valid_wire: str) -> str:
    module_name = f"penc_{inst_name}"
    lines = []
    lines.append(f"    {module_name} #(.WIDTH({width}), .LSB_PRIORITY({lsb_priority})) {inst_name}_inst (")
    lines.append(f"        .data_in({data_in_src}),")
    lines.append(f"        .index({index_wire}),")
    lines.append(f"        .valid({valid_wire})")
    lines.append(f"    );")
    return "\n".join(lines)