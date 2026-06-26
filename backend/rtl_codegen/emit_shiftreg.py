"""
emit_shiftreg.py
Generates a standalone synchronous shift-register Verilog module.

Supports all 4 canonical modes:
  SISO — Serial In, Serial Out
  PISO — Parallel In, Serial Out  (UART TX, SPI TX)
  SIPO — Serial In, Parallel Out  (UART RX, SPI RX)
  PIPO — Parallel In, Parallel Out (pipeline register)

And two shift directions for SISO/PISO/SIPO:
  right — shifts toward LSB (bit[0] exits first)
  left  — shifts toward MSB (bit[N-1] exits first)
"""


def emit_shiftreg(inst_name: str, width: int,
                  mode: str = "PISO",
                  direction: str = "right") -> tuple[str, str]:
    """
    Returns (module_name, verilog_source).

    mode      : "SISO" | "PISO" | "SIPO" | "PIPO"
    direction : "right" | "left"  (ignored for PIPO)
    """
    width       = max(1, int(width))
    mode        = mode.upper().strip()
    direction   = direction.lower().strip()
    module_name = f"shiftreg_{inst_name}"

    # Validate
    if mode not in ("SISO", "PISO", "SIPO", "PIPO"):
        mode = "PISO"
    if direction not in ("right", "left"):
        direction = "right"

    has_parallel_in  = mode in ("PISO", "PIPO")
    has_parallel_out = mode in ("SIPO", "PIPO")
    has_serial_in    = mode in ("SISO", "SIPO")
    has_serial_out   = mode in ("SISO", "PISO")
    has_load         = mode in ("PISO", "PIPO")

    L = []
    L.append(f"// Auto-generated: {width}-bit Shift Register ({mode}, shift-{direction})")
    L.append(f"module {module_name} #(")
    L.append(f"    parameter WIDTH = {width}")
    L.append(f") (")
    L.append(f"    input              clk,")
    L.append(f"    input              rst,")

    # Input ports
    if has_parallel_in:
        L.append(f"    input  [WIDTH-1:0] din,")
    if has_serial_in:
        L.append(f"    input              sin,")
    if has_load:
        L.append(f"    input              load,")
    L.append(f"    input              en,")

    # Output ports
    if has_parallel_out:
        L.append(f"    output wire [WIDTH-1:0] out" + ("," if has_serial_out else ""))
    if has_serial_out:
        L.append(f"    output wire        sout")

    L.append(f");\n")

    # Internal register
    L.append(f"    reg [WIDTH-1:0] _sreg;")
    L.append(f"")

    # Serial output assignment
    if has_serial_out:
        if direction == "right":
            L.append(f"    assign sout = _sreg[0];  // LSB exits first (right-shift)")
        else:
            L.append(f"    assign sout = _sreg[WIDTH-1];  // MSB exits first (left-shift)")
        L.append(f"")

    # Parallel output assignment for SIPO
    if mode == "SIPO":
        L.append(f"    assign out = _sreg;")
        L.append(f"")

    # Sequential logic
    L.append(f"    always @(posedge clk) begin")
    L.append(f"        if (rst)")
    L.append(f"            _sreg <= {{WIDTH{{1'b0}}}};")
    L.append(f"        else begin")

    if has_load:
        L.append(f"            if (load)")
        L.append(f"                _sreg <= din;")
        L.append(f"            else if (en) begin")
    else:
        L.append(f"            if (en) begin")

    # Shift logic
    if mode == "SISO":
        if direction == "right":
            L.append(f"                _sreg <= {{sin, _sreg[WIDTH-1:1]}};  // right: sin enters MSB")
        else:
            L.append(f"                _sreg <= {{_sreg[WIDTH-2:0], sin}};  // left: sin enters LSB")
    elif mode == "PISO":
        if direction == "right":
            L.append(f"                _sreg <= {{1'b0, _sreg[WIDTH-1:1]}};  // right: shift out LSB")
        else:
            L.append(f"                _sreg <= {{_sreg[WIDTH-2:0], 1'b0}};  // left: shift out MSB")
    elif mode == "SIPO":
        if direction == "right":
            L.append(f"                _sreg <= {{sin, _sreg[WIDTH-1:1]}};  // right: sin enters MSB")
        else:
            L.append(f"                _sreg <= {{_sreg[WIDTH-2:0], sin}};  // left: sin enters LSB")
    elif mode == "PIPO":
        L.append(f"                _sreg <= din;  // PIPO: load is the only operation")

    L.append(f"            end")
    L.append(f"        end")
    L.append(f"    end")

    # PIPO parallel output driven from register
    if mode == "PIPO":
        L.append(f"")
        L.append(f"    assign out = _sreg;")

    L.append(f"\nendmodule")
    return module_name, "\n".join(L)


def shiftreg_instantiation(inst_name: str, width: int,
                            mode: str = "PISO", direction: str = "right",
                            din_src: str = "0", sin_src: str = "0",
                            load_src: str = "0", en_src: str = "0",
                            out_wire: str = "", sout_wire: str = "") -> str:
    """
    Returns the Verilog instantiation string for a shift register.
    Wire names must be pre-declared by the caller (emit_verilog.py).
    """
    mode      = mode.upper().strip()
    module_name = f"shiftreg_{inst_name}"

    has_parallel_in  = mode in ("PISO", "PIPO")
    has_serial_in    = mode in ("SISO", "SIPO")
    has_parallel_out = mode in ("SIPO", "PIPO")
    has_serial_out   = mode in ("SISO", "PISO")
    has_load         = mode in ("PISO", "PIPO")

    # Safe defaults
    en_tied   = en_src   if en_src   not in ("0", "") else "1'b0"
    din_tied  = din_src  if din_src  not in ("0", "") else f"{width}'b0"
    sin_tied  = sin_src  if sin_src  not in ("0", "") else "1'b0"
    load_tied = load_src if load_src not in ("0", "") else "1'b0"

    L = []
    L.append(f"    {module_name} #(.WIDTH({width})) {inst_name}_inst (")
    L.append(f"        .clk(clk),")
    L.append(f"        .rst(rst),")
    if has_parallel_in:
        L.append(f"        .din({din_tied}),")
    if has_serial_in:
        L.append(f"        .sin({sin_tied}),")
    if has_load:
        L.append(f"        .load({load_tied}),")
    L.append(f"        .en({en_tied}),")
    if has_parallel_out:
        out_w = out_wire if out_wire else f"{inst_name}_out"
        L.append(f"        .out({out_w})" + ("," if has_serial_out else ""))
    if has_serial_out:
        sout_w = sout_wire if sout_wire else f"{inst_name}_sout"
        L.append(f"        .sout({sout_w})")
    L.append(f"    );")
    return "\n".join(L)