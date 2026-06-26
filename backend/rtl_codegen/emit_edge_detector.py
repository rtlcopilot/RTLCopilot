"""
emit_edge_detector.py
Generates a standalone edge detector Verilog module.
EDGE_TYPE: 0 = rising, 1 = falling, 2 = both
"""


def emit_edge_detector(inst_name: str, edge_type: int) -> tuple[str, str]:
    """
    Returns (module_name, verilog_source).
    edge_type: 0=rising, 1=falling, 2=both
    """
    edge_type   = int(edge_type) if int(edge_type) in (0, 1, 2) else 0
    module_name = f"edgedet_{inst_name}"
    et_str      = ["RISING", "FALLING", "BOTH"][edge_type]

    lines = []
    lines.append(f"// Auto-generated: Edge Detector ({et_str})")
    lines.append(f"module {module_name} #(")
    lines.append(f"    parameter EDGE_TYPE = {edge_type}  // 0=rising 1=falling 2=both")
    lines.append(f") (")
    lines.append(f"    input  wire clk,")
    lines.append(f"    input  wire rst,")
    lines.append(f"    input  wire signal_in,")
    lines.append(f"    output reg  pulse_out")
    lines.append(f");\n")
    lines.append(f"    reg [2:0] sync_reg;")
    lines.append(f"")
    lines.append(f"    always @(posedge clk or posedge rst) begin")
    lines.append(f"        if (rst) begin")
    lines.append(f"            sync_reg  <= 3'b000;")
    lines.append(f"            pulse_out <= 1'b0;")
    lines.append(f"        end else begin")
    lines.append(f"            sync_reg <= {{sync_reg[1:0], signal_in}};")
    lines.append(f"            case (EDGE_TYPE)")
    lines.append(f"                0: pulse_out <=  sync_reg[1] & ~sync_reg[2]; // Rising")
    lines.append(f"                1: pulse_out <= ~sync_reg[1] &  sync_reg[2]; // Falling")
    lines.append(f"                2: pulse_out <=  sync_reg[1] ^  sync_reg[2]; // Both")
    lines.append(f"                default: pulse_out <= 1'b0;")
    lines.append(f"            endcase")
    lines.append(f"        end")
    lines.append(f"    end")
    lines.append(f"\nendmodule")
    return module_name, "\n".join(lines)


def edge_detector_instantiation(inst_name: str, edge_type: int,
                                 signal_in_src: str,
                                 pulse_out_wire: str) -> str:
    module_name = f"edgedet_{inst_name}"
    lines = []
    lines.append(f"    {module_name} #(.EDGE_TYPE({edge_type})) {inst_name}_inst (")
    lines.append(f"        .clk(clk),")
    lines.append(f"        .rst(rst),")
    lines.append(f"        .signal_in({signal_in_src}),")
    lines.append(f"        .pulse_out({pulse_out_wire})")
    lines.append(f"    );")
    return "\n".join(lines)