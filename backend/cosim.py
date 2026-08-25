from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# Reset/clock ports are driven by the harness, not randomised.
_HARNESS_PORTS = {"clk", "clock", "rst", "reset", "rst_n", "resetn"}

DEFAULT_CYCLES = int(os.environ.get("COSIM_CYCLES", "24"))
_IVERILOG_TIMEOUT = float(os.environ.get("COSIM_TIMEOUT", "45"))


def ports_from_verilog(src: str) -> tuple[list, list, bool, str | None]:
    """Read the port list straight from the emitted top module.

    Taking ports from the generated source rather than from a result dict is
    what makes this robust: the reference model is built against exactly what
    the design exposes, and a change in the result schema cannot silently
    disable the check — which is how it came to report "no comparable ports"
    for a design that had five.

    Returns (inputs, outputs, has_clk, reset_name).
    """
    m = re.search(r"module\s+\w+\s*(?:#\s*\([^)]*\)\s*)?\((.*?)\)\s*;",
                  src, re.S)
    if not m:
        return [], [], False, None

    ins, outs, has_clk, rst = [], [], False, None
    for raw in m.group(1).split(","):
        decl = raw.strip()
        if not decl:
            continue
        d = re.match(r"(input|output)\s+(?:wire\s+|reg\s+)?(\[[^\]]+\])?\s*(\w+)",
                     decl)
        if not d:
            continue
        direction, rng, name = d.group(1), d.group(2), d.group(3)

        width = 1
        if rng:
            # "[12-1:0]" or "[11:0]" are sizeable; "[WIDTH-1:0]" is not, and a
            # parameterised port is left at 1 bit for stimulus purposes.
            hi = rng.strip("[]").split(":")[0]
            try:
                width = eval(hi, {"__builtins__": {}}) + 1   # noqa: S307
            except Exception:
                width = 1

        low = name.lower()
        if low in ("clk", "clock"):
            has_clk = True
        elif (rst is None and direction == "input"
              and low in ("rst", "reset", "rst_n", "resetn")):
            # First match only. A design can have both the harness reset `rst`
            # and a user-facing `reset` port (a peak detector's clear input);
            # overwriting meant the real reset was driven as data and the
            # clear input was never exercised.
            rst = name
        elif direction == "input":
            ins.append({"name": name, "width": max(1, int(width))})
        else:
            outs.append({"name": name, "width": max(1, int(width))})
    return ins, outs, has_clk, rst


def iverilog_available() -> bool:
    return shutil.which("iverilog") is not None and shutil.which("vvp") is not None


# ── stimulus ────────────────────────────────────────────────────────────────

def _lcg(seed: int):
    """Small deterministic PRNG. Reproducibility matters more than quality:
    the same design must produce the same verdict on every run."""
    state = seed & 0xFFFFFFFF
    while True:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        yield state


def build_stimulus(input_ports: list[dict], cycles: int = DEFAULT_CYCLES,
                   seed: int = 12345) -> list[dict]:
    """Corner values first, then pseudo-random.

    Corners catch the boundary bugs (0, 1, all-ones, half-scale); random
    catches ordering bugs like a peak detector that only fails on a
    descending sequence.
    """
    rng = _lcg(seed)
    rows: list[dict] = []

    def corners(w: int) -> list[int]:
        m = (1 << w) - 1
        return [0, 1, m, m >> 1, (m >> 1) + 1] if w > 1 else [0, 1]

    n_corner = max(len(corners(int(p.get("width", 1) or 1)))
                   for p in input_ports) if input_ports else 0
    for i in range(n_corner):
        row = {}
        for p in input_ports:
            w = max(1, int(p.get("width", 1) or 1))
            c = corners(w)
            row[p["name"]] = c[i % len(c)]
        rows.append(row)

    while len(rows) < cycles:
        row = {}
        for p in input_ports:
            w = max(1, int(p.get("width", 1) or 1))
            row[p["name"]] = next(rng) & ((1 << w) - 1)
        rows.append(row)
    return rows[:cycles]


# ── testbench generation ────────────────────────────────────────────────────

def _tb_source(module: str, input_ports: list[dict], output_ports: list[dict],
               stimulus: list[dict], has_clk: bool, reset_name: str | None,
               reset_active_high: bool = True) -> str:
    """A self-checking-free testbench: it only PRINTS outputs.

    Comparison happens in Python on the two printed traces, so the same
    testbench drives both modules and neither can influence the verdict.
    """
    lines = ["`timescale 1ns/1ps", "module cosim_tb;"]

    for p in input_ports:
        w = max(1, int(p.get("width", 1) or 1))
        decl = f"[{w-1}:0] " if w > 1 else ""
        lines.append(f"  reg {decl}{p['name']};")
    for p in output_ports:
        w = max(1, int(p.get("width", 1) or 1))
        decl = f"[{w-1}:0] " if w > 1 else ""
        lines.append(f"  wire {decl}{p['name']};")
    if has_clk:
        lines.append("  reg clk;")
    if reset_name:
        lines.append(f"  reg {reset_name};")

    conns = []
    if has_clk:
        conns.append(".clk(clk)")
    if reset_name:
        conns.append(f".{reset_name}({reset_name})")
    conns += [f".{p['name']}({p['name']})" for p in input_ports + output_ports]
    lines.append(f"  {module} dut({', '.join(conns)});")

    if has_clk:
        lines += ["  initial clk = 0;", "  always #5 clk = ~clk;"]

    lines.append("  initial begin")
    if reset_name:
        lines.append(f"    {reset_name} = 1'b{1 if reset_active_high else 0};")
    for p in input_ports:
        lines.append(f"    {p['name']} = 0;")
    if has_clk:
        lines += ["    @(posedge clk); @(posedge clk);"]
    if reset_name:
        lines.append(f"    {reset_name} = 1'b{0 if reset_active_high else 1};")
    if has_clk:
        lines.append("    @(negedge clk);")

    for i, row in enumerate(stimulus):
        for p in input_ports:
            lines.append(f"    {p['name']} = {row.get(p['name'], 0)};")
        lines.append("    @(posedge clk); #1;" if has_clk else "    #10;")
        fmt = " ".join(f"{p['name']}=%0d" for p in output_ports)
        args = ", ".join(p["name"] for p in output_ports)
        lines.append(f'    $display("STEP {i} {fmt}", {args});')

    lines += ["    $finish;", "  end", "endmodule"]
    return "\n".join(lines)


# ── running ─────────────────────────────────────────────────────────────────

def _run(sources: dict[str, str], tb: str) -> tuple[bool, list[str], str]:
    """Compile and run one design. Returns (ok, STEP lines, error text)."""
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        for name, text in sources.items():
            (dp / name).write_text(text, encoding="utf-8")
        (dp / "cosim_tb.v").write_text(tb, encoding="utf-8")
        vfiles = [str(dp / n) for n in sources] + [str(dp / "cosim_tb.v")]
        try:
            c = subprocess.run(["iverilog", "-o", str(dp / "a.out")] + vfiles,
                               capture_output=True, text=True,
                               timeout=_IVERILOG_TIMEOUT)
            if c.returncode != 0:
                return False, [], c.stderr or c.stdout
            r = subprocess.run(["vvp", str(dp / "a.out")],
                               capture_output=True, text=True,
                               timeout=_IVERILOG_TIMEOUT)
            steps = [l.strip() for l in r.stdout.splitlines()
                     if l.strip().startswith("STEP ")]
            return True, steps, ""
        except subprocess.TimeoutExpired:
            return False, [], "simulation timed out"
        except Exception as e:                       # pragma: no cover
            return False, [], f"{type(e).__name__}: {e}"


def _parse_step(line: str) -> tuple[int, dict[str, int]]:
    m = re.match(r"STEP (\d+) (.*)", line)
    if not m:
        return -1, {}
    vals = {}
    for kv in m.group(2).split():
        if "=" in kv:
            k, v = kv.split("=", 1)
            try:
                vals[k] = int(v)
            except ValueError:
                pass
    return int(m.group(1)), vals


def compare(structural_files: dict[str, str], behavioural_src: str,
            input_ports: list[dict], output_ports: list[dict],
            has_clk: bool = True, reset_name: str | None = "rst",
            reset_active_high: bool = True,
            cycles: int = DEFAULT_CYCLES) -> dict:
    """Co-simulate both designs on identical stimulus and diff the traces.

    Returns a verdict dict:
        status : "match" | "mismatch" | "skipped" | "error"
        divergences : first few differing steps, with the stimulus that
                      produced them, so the report names concrete values
    """
    if not iverilog_available():
        return {"status": "skipped", "reason": "iverilog not on PATH"}
    if not input_ports or not output_ports:
        return {"status": "skipped", "reason": "no ports to compare"}

    stim = build_stimulus(input_ports, cycles)
    tb_struct = _tb_source("top", input_ports, output_ports, stim,
                           has_clk, reset_name, reset_active_high)
    tb_behav = _tb_source("ref_model", input_ports, output_ports, stim,
                          has_clk, reset_name, reset_active_high)

    ok_s, steps_s, err_s = _run(structural_files, tb_struct)
    if not ok_s:
        return {"status": "error", "reason": f"structural design: {err_s[:300]}"}

    ok_b, steps_b, err_b = _run({"ref_model.v": behavioural_src}, tb_behav)
    if not ok_b:
        # The reference failing to compile is not evidence about the design.
        return {"status": "skipped",
                "reason": f"reference model did not compile: {err_b[:300]}"}

    divergences = []
    for ls, lb in zip(steps_s, steps_b):
        i_s, vs = _parse_step(ls)
        i_b, vb = _parse_step(lb)
        if i_s != i_b:
            continue
        diff = {k: (vs.get(k), vb.get(k)) for k in vs if vs.get(k) != vb.get(k)}
        if diff:
            divergences.append({
                "step": i_s,
                "inputs": stim[i_s] if i_s < len(stim) else {},
                "outputs": {k: {"design": a, "reference": b}
                            for k, (a, b) in diff.items()},
            })
        if len(divergences) >= 5:
            break

    if divergences:
        return {"status": "mismatch", "divergences": divergences,
                "compared_steps": min(len(steps_s), len(steps_b))}
    return {"status": "match", "compared_steps": min(len(steps_s), len(steps_b))}


def describe(verdict: dict) -> str:
    """Plain-language summary for the chat window."""
    st = verdict.get("status")
    if st == "match":
        return (f"Behaviour checked against an independent reference over "
                f"{verdict.get('compared_steps', 0)} cycles — they agree.")
    if st == "skipped":
        return f"Behaviour not verified ({verdict.get('reason', 'skipped')})."
    if st == "error":
        return f"Behaviour could not be checked ({verdict.get('reason', '')})."

    lines = ["**I'm not sure this circuit does what you asked.**", "",
             "I built a second, independent version straight from your "
             "description and simulated both. They disagree:"]
    for d in verdict.get("divergences", [])[:3]:
        ins = ", ".join(f"{k}={v}" for k, v in d["inputs"].items())
        for port, vals in d["outputs"].items():
            lines.append(f"  - cycle {d['step']} ({ins}): `{port}` is "
                         f"{vals['design']} here, but {vals['reference']} in "
                         f"the reference")
    lines += ["", "One of the two is wrong — most often the operator on a "
                  "comparator, or the branches of a multiplexer being the "
                  "wrong way round. The blocks are on your canvas so you can "
                  "check."]
    return "\n".join(lines)


__all__ = [_n for _n in dir() if not _n.startswith("__")]