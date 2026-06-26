"""
emit_testbench.py - RTL Copilot testbench generator

stimulus dict fields (all optional, safe defaults shown):
  steps            : list of {time, values, expected, label}
  reset_type       : "sync" | "async" | "none"    (default: "sync")
  reset_active     : "high" | "low"               (default: auto-detected from IR)
  use_corner_cases : bool                          (default: False)
  use_random       : bool                          (default: False)
  num_random_steps : int                           (default: 8)
  random_seed      : int | null                    (default: null)
  sim_duration_ns  : int                           (default: 2000)
"""

import json
import random
import sys



def _port_width(p):
    try:
        return max(1, int(float(p.get("width", 1))))
    except Exception:
        return 1


def _port_width_resolved(p, params):
    """
    Like _port_width but resolves parameter names (e.g. "DATA_WIDTH") to their
    numeric value using the IR parameters dict before converting.
    Falls back to 8 if the name is not found, which is a safe default for data buses.
    """
    raw = str(p.get("width", "1")).strip()

    try:
        return max(1, int(float(raw)))
    except ValueError:
        pass

    if raw in params:
        try:
            return max(1, int(float(params[raw])))
        except (ValueError, TypeError):
            pass

    return 8


def get_width_prefix(w):
    try:
        val = int(float(w))
        return f"[{val-1}:0] " if val > 1 else ""
    except Exception:
        return f"[{w}-1:0] "


def _needs_seq(ir):
    nodes      = ir.get("nodes", [])
    port_names = [p["name"] for p in ir.get("ports", [])]
    seq_types  = {
        "reg", "fsm_state", "math",
        "macro_counter", "macro_shiftreg", "macro_sync",
        "macro_fifo", "macro_penc",
        "macro_edgedet", "macro_dpram", "macro_cfgcounter",
    }


    def _custom_block_is_seq(n):
        if n.get("type") != "custom_block":
            return False

        pattern = n.get("customSchema", {}).get("pattern", "")
        if pattern in ("counter_based", "register_based", "shift_based"):
            return True

        cb_port_names = [p.get("name", "") for p in n.get("customPorts", [])]
        return "clk" in cb_port_names or "rst" in cb_port_names

    return (
        any(n["type"] in seq_types for n in nodes)
        or any(_custom_block_is_seq(n) for n in nodes)
        or "clk" in port_names
        or "rst" in port_names
    )


def _detect_reset_active(ir):
    """
    Auto-detect reset polarity from IR node types.
    macro_fifo / macro_dpram / macro_cfgcounter / macro_shiftreg
    all use active-low reset (!rst internally).
    Custom blocks (counter/register/shift) also use active-low.
    Everything else uses active-high.
    Returns "low" or "high".
    """
    active_low_types = {
        "macro_fifo", "macro_dpram",
        "macro_cfgcounter", "macro_shiftreg",
    }
    for n in ir.get("nodes", []):
        if n.get("type") in active_low_types:
            return "low"
        if n.get("type") == "custom_block":
            pattern = n.get("customSchema", {}).get("pattern", "")
            if pattern in ("counter_based", "register_based", "shift_based"):
                return "low"
    return "high"


def _build_corner_steps(input_ports, start_idx, params):
    """
    Corner-case stimulus: 0, all-ones, LSB-only, MSB-only per port.
    1-bit ports get only 0 and 1.
    """
    steps = []
    idx   = start_idx
    for p in input_ports:
        if p["name"] in ("clk", "rst"):
            continue
        w    = _port_width_resolved(p, params)
        name = p["name"]
        if w == 1:
            cases = [("0", "zero"), ("1", "one")]
        else:
            all_ones = (1 << w) - 1
            msb_only = 1 << (w - 1)
            cases = [
                ("0",           "zero"),
                (str(all_ones), "all_ones"),
                ("1",           "lsb_only"),
                (str(msb_only), "msb_only"),
            ]
        for val_str, suffix in cases:
            steps.append({
                "label":    f"corner_{name}_{suffix}",
                "time":     idx * 100,
                "values":   {name: val_str},
                "expected": {},
                "_auto":    True,
            })
            idx += 1
    return steps


def _build_random_steps(input_ports, count, seed, start_idx, params):
    """
    Random stimulus across all input ports simultaneously.
    Isolated RNG so global state is unaffected.
    """
    rng        = random.Random(seed)
    data_ports = [p for p in input_ports if p["name"] not in ("clk", "rst")]
    steps      = []
    for i in range(count):
        values = {
            p["name"]: str(rng.randint(0, (1 << _port_width_resolved(p, params)) - 1))
            for p in data_ports
        }
        steps.append({
            "label":    f"random_{i}",
            "time":     (start_idx + i) * 100,
            "values":   values,
            "expected": {},
            "_auto":    True,
        })
    return steps


def _emit_step(L, step, step_idx, needs_clk, current_sim_time, output_ports):
    """Emit one stimulus step. Returns updated current_sim_time."""
    target_time = int(step.get("time", 0))
    values      = step.get("values", {})
    expected    = step.get("expected", {})
    label       = step.get("label", f"step_{step_idx}")
    is_auto     = step.get("_auto", False)

    comment_tag = "AUTO" if is_auto else f"t={target_time} ns"
    L.append(f"    // -- {label}  ({comment_tag}) ----------------")

    if needs_clk:
        L.append("    @(posedge clk); #1;")
    else:
        delay = max(0, target_time - current_sim_time)
        if delay > 0:
            L.append(f"    #{delay};")
        current_sim_time = target_time

    # Drive inputs
    has_inputs   = any(str(v).strip() for v in values.values())
    has_expected = any(str(v).strip() for v in expected.values())

    for port_name, val in values.items():
        if str(val).strip():
            L.append(f"    {port_name} = {val};")

    if not needs_clk:
        L.append("    #1;")

    if needs_clk and has_inputs and has_expected:
        L.append("    @(posedge clk); #1;  // settle: let sequential logic respond")

    inp_names   = [pn for pn in list(values.keys())[:4] if str(values.get(pn, "")).strip()]
    out_names   = [p["name"] for p in output_ports[:3]]
    all_display = inp_names + out_names
    if all_display:
        fmt     = "  ".join([f"{n}=%0d" for n in all_display])
        sig_str = ", ".join(all_display)
        L.append(f'    $display("{label}: {fmt}", {sig_str});')

    for out_name, exp_val in expected.items():
        if str(exp_val).strip():
            L.append(f"    if ({out_name} === {exp_val}) begin")
            L.append(f'      $display("  [PASS] {out_name} == {exp_val}");')
            L.append(f"      pass_count = pass_count + 1;")
            L.append(f"    end else begin")
            L.append(f'      $display("  [FAIL] {out_name}: expected {exp_val}, got %0d", {out_name});')
            L.append(f"      fail_count = fail_count + 1;")
            L.append(f"    end")

    L.append("")
    return current_sim_time



def emit_testbench(ir, stimulus):
    module_name  = ir.get("module", "top")
    ports        = ir.get("ports", [])
    port_names   = [p["name"] for p in ports]
    input_ports  = [p for p in ports if p["dir"] == "input"]
    output_ports = [p for p in ports if p["dir"] == "output"]
    ir_params    = ir.get("parameters", {})

    has_seq      = _needs_seq(ir)
    has_clk_port = "clk" in port_names
    has_rst_port = "rst" in port_names
    needs_clk    = has_seq or has_clk_port or has_rst_port

    reset_type      = stimulus.get("reset_type", "sync")
    sim_duration_ns = max(500, int(stimulus.get("sim_duration_ns", 2000) or 2000))


    user_reset_active = stimulus.get("reset_active", None)
    if user_reset_active in ("high", "low"):
        reset_active = user_reset_active
    else:
        reset_active = _detect_reset_active(ir)

    use_corner_cases = bool(stimulus.get("use_corner_cases", False))
    use_random       = bool(stimulus.get("use_random",       False))
    num_random_steps = max(1, int(stimulus.get("num_random_steps", 8) or 8))
    raw_seed         = stimulus.get("random_seed", None)
    random_seed      = int(raw_seed) if raw_seed is not None else None

    rst_assert   = "1'b1" if reset_active == "high" else "1'b0"
    rst_deassert = "1'b0" if reset_active == "high" else "1'b1"

    user_steps = stimulus.get("steps", [])
    try:
        user_steps = sorted(user_steps, key=lambda x: int(x.get("time", 0)))
    except Exception:
        pass


    next_idx = len(user_steps)

    corner_steps = []
    if use_corner_cases:
        corner_steps = _build_corner_steps(input_ports, start_idx=next_idx, params=ir_params)
        next_idx += len(corner_steps)

    random_steps = []
    if use_random:
        random_steps = _build_random_steps(
            input_ports, num_random_steps, random_seed,
            start_idx=next_idx, params=ir_params
        )

    auto_step_count = len(corner_steps) + len(random_steps)
    timeout_ns      = max(sim_duration_ns + 200, auto_step_count * 20 + 500, 2200)


    L = []
    L.append("`timescale 1ns / 1ps")
    L.append(f"// Testbench for {module_name} - RTL Copilot")
    L.append(
        f"// Config: reset={reset_type} active_{reset_active}"
        f"  duration={sim_duration_ns}ns"
        f"  corner={'on' if use_corner_cases else 'off'}"
        f"  random={'on' if use_random else 'off'}"
        + (f"  seed={random_seed}" if use_random and random_seed is not None else "")
    )
    L.append(f"module {module_name}_tb;")
    L.append("")


    if ir_params:
        L.append("  // Parameters (mirrored from DUT)")
        for pname, pval in ir_params.items():
            L.append(f"  localparam {pname} = {pval};")
        L.append("")


    L.append("  // Signals")
    declared = set()

    if needs_clk:
        if not has_clk_port:
            L.append("  reg clk;")
            declared.add("clk")
        if not has_rst_port:
            L.append("  reg rst;")
            declared.add("rst")

    for p in ports:
        name = p["name"]
        if name in declared:
            continue
        declared.add(name)
        prefix = get_width_prefix(p.get("width", 1))
        dtype  = "reg" if p["dir"] == "input" else "wire"
        L.append(f"  {dtype} {prefix}{name};")

    L.append("")
    L.append("  integer pass_count = 0;")
    L.append("  integer fail_count = 0;")

    L.append("")
    L.append(f"  {module_name} uut (")
    inst_ports = []
    inst_seen  = set()

    for p in ports:
        if p["name"] not in inst_seen:
            inst_ports.append(f"    .{p['name']}({p['name']})")
            inst_seen.add(p["name"])

    if needs_clk:
        if "clk" not in inst_seen:
            inst_ports.append("    .clk(clk)")
        if "rst" not in inst_seen:
            inst_ports.append("    .rst(rst)")

    L.append(",\n".join(inst_ports))
    L.append("  );")


    if needs_clk:
        L.append("")
        L.append("  // Clock: 10 ns period (100 MHz)")
        L.append("  initial clk = 1'b0;")
        L.append("  always #5 clk = ~clk;")

    L.append("")
    L.append(f"  // Watchdog: abort if sim exceeds {timeout_ns} ns")
    L.append(f"  initial begin")
    L.append(f"    #{timeout_ns};")
    L.append(f'    $display("TIMEOUT: simulation exceeded {timeout_ns} ns");')
    L.append(f"    $finish;")
    L.append(f"  end")


    L.append("")
    L.append("  initial begin")
    L.append('    $dumpfile("simulation.vcd");')
    L.append(f'    $dumpvars(0, {module_name}_tb.uut);  // dump UUT signals only (excludes testbench counters)')
    L.append("  end")

    L.append("")
    L.append("  initial begin")
    L.append(f'    $display("\\n=== {module_name} testbench start ===");')
    if use_random and random_seed is not None:
        L.append(f'    $display("  seed={random_seed} (deterministic)");')
    elif use_random:
        L.append(f'    $display("  seed=none (new sequence each run)");')
    L.append("")

    if needs_clk and reset_type != "none":
        polarity_note = "active-high" if reset_active == "high" else "active-low"
        L.append(f"    // Reset prologue ({reset_type}, {polarity_note})")
        L.append(f"    rst = {rst_assert};")
        for p in input_ports:
            if p["name"] not in ("clk", "rst"):
                L.append(f"    {p['name']} = 0;")

        L.append("    @(posedge clk); #1;")
        L.append("    @(posedge clk); #1;")
        L.append("    @(posedge clk); #1;")
        L.append("    @(posedge clk); #1;")
        L.append(f"    rst = {rst_deassert};")
        L.append("    @(posedge clk); #1;")
        L.append("")
        current_sim_time = 41
    elif not needs_clk:
        for p in input_ports:
            L.append(f"    {p['name']} = 0;")
        L.append("    #10;")
        L.append("")
        current_sim_time = 10
    else:

        for p in input_ports:
            if p["name"] not in ("clk", "rst"):
                L.append(f"    {p['name']} = 0;")
        L.append("    @(posedge clk); #1;")
        L.append("")
        current_sim_time = 11

    # User steps
    if user_steps:
        L.append('    $display("-- User stimulus --");')
        L.append("")
    for step_idx, step in enumerate(user_steps):
        current_sim_time = _emit_step(
            L, step, step_idx, needs_clk, current_sim_time, output_ports
        )

    # Corner-case steps
    if corner_steps:
        L.append('    $display("-- Corner cases --");')
        L.append("")
        for step_idx, step in enumerate(corner_steps):
            current_sim_time = _emit_step(
                L, step, step_idx, needs_clk, current_sim_time, output_ports
            )

    # Random steps
    if random_steps:
        seed_note = f"seed={random_seed}" if random_seed is not None else "unseeded"
        L.append(f'    $display("-- Random stimulus ({seed_note}) --");')
        L.append("")
        for step_idx, step in enumerate(random_steps):
            current_sim_time = _emit_step(
                L, step, step_idx, needs_clk, current_sim_time, output_ports
            )

    # Trailing hold to guarantee sim_duration_ns is reached
    L.append(f"    // Guarantee minimum simulation window of {sim_duration_ns} ns")
    L.append(f"    if ($time < {sim_duration_ns}) #({sim_duration_ns} - $time);")
    L.append("")

    # Final report
    L.append("    // Final report")
    L.append('    $display("\\n=== RESULTS: %0d PASS  %0d FAIL ===", pass_count, fail_count);')
    L.append("    if (fail_count == 0)")
    L.append('      $display("  ALL TESTS PASSED");')
    L.append("    else")
    L.append('      $display("  FAILURES DETECTED - review above");')
    L.append("    #50;")
    L.append("    $finish;")
    L.append("  end")
    L.append("")
    L.append("endmodule")

    return "\n".join(L)

if __name__ == "__main__":
    try:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            data = json.load(f)
        output = emit_testbench(data.get("ir", {}), data.get("stimulus", {}))
        sys.stdout.buffer.write(output.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
    except Exception:
        import traceback
        sys.stderr.buffer.write(
            f"// Python Error:\n{traceback.format_exc()}".encode("utf-8")
        )
        sys.exit(1)