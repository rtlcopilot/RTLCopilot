"""
emit_mux.py
Generates a standalone parameterized N:1 multiplexer Verilog module.
Called by emit_verilog.py (the orchestrator).
"""
import math


def emit_mux(inst_name: str, num_inputs: int, width: int) -> tuple[str, str]:
    """
    Returns (module_name, verilog_source).

    module_name  — unique name used both as Verilog module name and filename stem.
    verilog_source — complete synthesisable Verilog.

    Parameters
    ----------
    inst_name  : canvas node name (used as module suffix for uniqueness)
    num_inputs : number of data inputs  (≥ 2)
    width      : data bus width in bits
    """
    num_inputs  = max(2, int(num_inputs))
    width       = max(1, int(width))
    sel_bits    = max(1, math.ceil(math.log2(num_inputs)))
    module_name = f"mux_{inst_name}"

    lines = []
    lines.append(f"// Auto-generated: {num_inputs}:{1} Multiplexer — {width}-bit data")
    lines.append(f"module {module_name} #(")
    lines.append(f"    parameter WIDTH = {width},")
    lines.append(f"    parameter N     = {num_inputs}")
    lines.append(f") (")

    # Data inputs
    for i in range(num_inputs):
        lines.append(f"    input  [WIDTH-1:0] in{i},")

    lines.append(f"    input  [{sel_bits}-1:0] sel,")
    lines.append(f"    output [WIDTH-1:0] out")
    lines.append(f");\n")

    if num_inputs == 2:
        lines.append(f"    assign out = sel ? in1 : in0;")
    else:
        lines.append(f"    reg [WIDTH-1:0] out_r;")
        lines.append(f"    always @(*) begin")
        lines.append(f"        case (sel)")
        for i in range(num_inputs):
            lines.append(f"            {sel_bits}'d{i}: out_r = in{i};")
        lines.append(f"            default:  out_r = {width}'b0;")
        lines.append(f"        endcase")
        lines.append(f"    end")
        lines.append(f"    assign out = out_r;")

    lines.append(f"\nendmodule")
    return module_name, "\n".join(lines)


def mux_instantiation(inst_name: str, num_inputs: int, width: int,
                       sel_bits: int, data_srcs: list[str],
                       sel_src: str, out_wire: str) -> str:
    """
    Returns the Verilog instantiation snippet for top.v.

    data_srcs : list of width-N signal names (in0 … inN-1)
    sel_src   : combined select signal (1-bit or multi-bit)
    out_wire  : wire name that receives the output
    """
    module_name = f"mux_{inst_name}"
    lines = []
    lines.append(f"    {module_name} #(.WIDTH({width}), .N({num_inputs})) {inst_name}_inst (")
    for i, src in enumerate(data_srcs):
        lines.append(f"        .in{i}({src}),")
    lines.append(f"        .sel({sel_src}),")
    lines.append(f"        .out({out_wire})")
    lines.append(f"    );")
    return "\n".join(lines)