"""
emit_cfg_counter.py
Generates a standalone configurable counter Verilog module.
Supports: up/down direction, synchronous load, terminal count output.
"""


def emit_cfg_counter(inst_name: str, width: int, count_dir: int,
                      terminal_value: str = None) -> tuple[str, str]:
    """
    Returns (module_name, verilog_source).
    count_dir: 1 = up (default), 0 = down
    terminal_value: optional override for TERMINAL_VALUE parameter.
      Pass a Verilog expression string (e.g. "BAUD_DIV", "8'hFF").
      Defaults to {WIDTH{1'b1}} (all ones) when None.
    """
    width       = max(1, int(width))
    count_dir   = 1 if int(count_dir) else 0
    module_name = f"cfgcnt_{inst_name}"
    dir_str     = "UP" if count_dir else "DOWN"


    lines = []
    lines.append(f"// Auto-generated: Configurable Counter ({dir_str}, {width}-bit)")
    lines.append(f"module {module_name} #(")
    lines.append(f"    parameter WIDTH         = {width},")
    lines.append(f"    parameter COUNT_DIR     = {count_dir},  // 1=up 0=down")
    lines.append(f"    parameter [WIDTH-1:0] TERMINAL_VALUE = {{WIDTH{{1'b1}}}}")
    lines.append(f") (")
    lines.append(f"    input  wire              clk,")
    lines.append(f"    input  wire              rst,")
    lines.append(f"    input  wire              en,")
    lines.append(f"    input  wire              load,")
    lines.append(f"    input  wire [WIDTH-1:0]  load_value,")
    lines.append(f"    output reg  [WIDTH-1:0]  count,")
    lines.append(f"    output reg               terminal_count")
    lines.append(f");\n")
    lines.append(f"    wire [WIDTH-1:0] next_count =")
    lines.append(f"        (load)   ? load_value :")
    lines.append(f"        (en)   ? (COUNT_DIR ? count + 1'b1 : count - 1'b1) :")
    lines.append(f"                   count;")
    lines.append(f"")
    lines.append(f"    always @(posedge clk or posedge rst) begin")
    lines.append(f"        if (rst) begin")
    lines.append(f"            count          <= (COUNT_DIR) ? {{WIDTH{{1'b0}}}} : TERMINAL_VALUE;")
    lines.append(f"            terminal_count <= 1'b0;")
    lines.append(f"        end else begin")
    lines.append(f"            count          <= next_count;")
    lines.append(f"            terminal_count <= (next_count == TERMINAL_VALUE);")
    lines.append(f"        end")
    lines.append(f"    end")
    lines.append(f"\nendmodule")
    return module_name, "\n".join(lines)


def cfg_counter_instantiation(inst_name: str, width: int, count_dir: int,
                                enable_src: str, load_src: str,
                                load_value_src: str,
                                count_wire: str, tc_wire: str,
                                terminal_value: str = None) -> str:

    module_name = f"cfgcnt_{inst_name}"

    load_tied  = load_src       if load_src       != "0" else "1'b0"
    lv_tied    = load_value_src if load_value_src != "0" else f"{width}'b0"
    en_tied    = enable_src     if enable_src     != "0" else "1'b1"
    lines = []

    tv_param = f", .TERMINAL_VALUE({terminal_value})" if terminal_value else ""
    lines.append(f"    {module_name} #(.WIDTH({width}), .COUNT_DIR({count_dir}){tv_param}) {inst_name}_inst (")
    lines.append(f"        .clk(clk),")
    lines.append(f"        .rst(rst),")
    lines.append(f"        .en({en_tied}),")
    lines.append(f"        .load({load_tied}),")
    lines.append(f"        .load_value({lv_tied}),")
    if count_wire:
        lines.append(f"        .count({count_wire}),")
    lines.append(f"        .terminal_count({tc_wire})")
    lines.append(f"    );")
    return "\n".join(lines)