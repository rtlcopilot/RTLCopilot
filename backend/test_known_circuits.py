"""
test_known_circuits.py
======================
Automated regression suite for RTLCopilot known circuits.

Runs every circuit in _KNOWN_HIERARCHIES through the full v2 pipeline
(same path as a real AI build, but without a server or HTTP request),
validates the Verilog output at multiple levels, and reports pass/fail.

Usage:
    cd D:\\RTLCopilot\\backend
    python test_known_circuits.py

    # Test specific circuits only:
    python test_known_circuits.py uart_tx spi_master

    # Verbose mode (print full Verilog on failure):
    python test_known_circuits.py --verbose

Exit code: 0 = all passed, 1 = any failed
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
CODEGEN_DIR = BACKEND_DIR / "rtl_codegen"
EMIT_SCRIPT = CODEGEN_DIR / "emit_verilog.py"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(CODEGEN_DIR))

os.environ.setdefault("TESTING", "1")

try:
    from known_circuits import _KNOWN_HIERARCHIES, _CIRCUIT_KEYWORDS
    from api import (
        _run_hierarchical_v2,
        _v2_classify,
    )
except ImportError as e:
    print(f"[ERROR] Could not import from api.py: {e}")
    print("        Make sure you run this from D:\\RTLCopilot\\backend")
    sys.exit(1)

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):  return f"{GREEN}✅ {msg}{RESET}"
def fail(msg): return f"{RED}❌ {msg}{RESET}"
def warn(msg): return f"{YELLOW}⚠️  {msg}{RESET}"
def info(msg): return f"{CYAN}   {msg}{RESET}"


def check_iverilog(verilog_files: dict) -> list[str]:
    """Run iverilog on all generated files. Returns list of error strings."""
    errors = []
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            for fname, code in verilog_files.items():
                (p / fname).write_text(code, encoding="utf-8")
            files = [str(p / f) for f in verilog_files]
            result = subprocess.run(
                ["iverilog", "-tnull", "-s", "top"] + files,
                capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0:
                for line in result.stderr.strip().splitlines():
                    # Skip the false-positive "-s top" error
                    if "Unable to find the root module" in line:
                        continue
                    if line.strip():
                        errors.append(f"iverilog: {line.strip()}")
    except FileNotFoundError:
        pass  
    except Exception as e:
        errors.append(f"iverilog check crashed: {e}")
    return errors


def check_no_duplicate_declarations(top_v: str) -> list[str]:
    """Detect signals declared as both wire and reg."""
    errors = []
    wires = set(re.findall(r'\bwire\s+(?:\[[\w\-:]+\]\s+)?(\w+)\s*;', top_v))
    regs  = set(re.findall(r'\breg\s+(?:\[[\w\-:]+\]\s+)?(\w+)\s*;', top_v))
    dupes = wires & regs
    for d in sorted(dupes):
        errors.append(f"Duplicate declaration: '{d}' is both wire and reg")
    return errors


def check_no_orphan_wires(top_v: str) -> list[str]:
    """Detect wire declarations that are never driven (no assign, no port connection)."""
    errors = []
    declared = re.findall(r'\bwire\s+(?:\[[\w\-:]+\]\s+)?(\w+)\s*;', top_v)
    for w in declared:
        driven_by_assign = bool(re.search(rf'\bassign\s+{w}\s*=', top_v))
        driven_by_port   = bool(re.search(rf'\.[\w]+\s*\(\s*{w}\s*\)', top_v))
        driven_by_output = bool(re.search(rf'\boutput\b.*\b{w}\b', top_v))
        if not (driven_by_assign or driven_by_port or driven_by_output):
            errors.append(f"Orphan wire: '{w}' declared but never driven")
    return errors


def check_localparam_prefixes(top_v: str) -> list[str]:
    """Detect unprefixed localparams that could collide across FSMs."""
    errors = []
    dangerous = ["idle", "start_bit", "stop_bit", "data_bits", "active",
                 "done", "wait", "init", "reset", "counting", "stable",
                 "transfer", "read", "write", "send", "receive"]
    localparams = re.findall(r'\blocalparam\s+(\w+)\s*=', top_v)
    for lp in localparams:
        if lp.lower() in dangerous:
            errors.append(
                f"Unprefixed localparam '{lp}' — will collide if second FSM added. "
                f"Expected e.g. 'TXFSM_{lp.upper()}'"
            )
    return errors


def check_terminal_values(top_v: str) -> list[str]:
    """Detect cfgcnt instantiations missing TERMINAL_VALUE when they should have it."""
    errors = []
    insts = re.findall(
        r'cfgcnt_(\w+)\s*#\(([^)]+)\)\s*\w+_inst',
        top_v
    )
    for name, params in insts:
        if "baud" in name and "TERMINAL_VALUE" not in params:
            errors.append(
                f"cfgcnt_{name} missing .TERMINAL_VALUE — baud counter will use "
                f"default all-ones which may be wrong"
            )
        if "bit" in name and "TERMINAL_VALUE" not in params:
            errors.append(
                f"cfgcnt_{name} missing .TERMINAL_VALUE — bit counter terminal "
                f"count is accidental (defaults to all-ones)"
            )
    return errors


def check_data_width_parameterized(top_v: str) -> list[str]:
    """Check that data ports use DATA_WIDTH parameter, not hardcoded width."""
    errors = []
    hardcoded = re.findall(
        r'\b(input|output)\s+\[(?:7:0|8-1:0)\]\s+(\w*din\w*|\w*data\w*|\w*dout\w*)',
        top_v
    )
    for direction, sig in hardcoded:
        errors.append(
            f"Port '{sig}' has hardcoded width [7:0] — should use [DATA_WIDTH-1:0]"
        )
    return errors


def check_output_logic_state_names(top_v: str) -> list[str]:
    """Check assign tx_out ternary references valid localparam names."""
    errors = []
    localparams = set(re.findall(r'\blocalparam\s+(\w+)\s*=', top_v))
    comparisons = re.findall(r'current_state\s*==\s*(\w+)', top_v)
    for state in comparisons:
        if state not in localparams:
            errors.append(
                f"output_logic assign references '{state}' but no localparam found — "
                f"prefix mismatch"
            )
    return errors


def check_no_dead_fsm_regs(top_v: str, circuit_key: str) -> list[str]:
    """Check for regs declared in FSM but never read (dead registers)."""
    errors = []
    regs = re.findall(r'\breg\s+(?:\[[\w\-:]+\]\s+)?(\w+)\s*;', top_v)

    skip = {"current_state", "next_state"}
    for r in regs:
        if r in skip:
            continue

        assign_pattern = rf'\b{r}\s*='
        use_pattern    = rf'\.[\w]+\s*\(\s*{r}\s*\)'
        all_uses = re.findall(rf'\b{r}\b', top_v)

        decl_count   = len(re.findall(rf'\breg\s+(?:\[[\w\-:]+\]\s+)?{r}\s*;', top_v))
        assign_count = len(re.findall(assign_pattern, top_v))
        port_count   = len(re.findall(use_pattern, top_v))
        wire_use     = len(re.findall(rf'\bwire\b.*\b{r}\b|\bassign\b.*\b{r}\b', top_v))
        total_uses   = len(all_uses)

        if port_count == 0 and wire_use == 0 and total_uses == (decl_count + assign_count):
            errors.append(f"Dead FSM reg '{r}' — declared and assigned but never consumed")
    return errors


def check_shift_register_sout_connected(top_v: str) -> list[str]:
    """Check that shift register outputs are wired to something meaningful.
    PISO/SISO mode → serial output _sout must exist and be used.
    SIPO/PIPO mode → parallel output _q or connected via .out() port — no _sout expected.
    """
    errors = []

    insts = re.findall(
        r'shiftreg_(\w+)\s*#\([^)]*\)\s*\w+_inst', top_v
    )
    for inst_name in insts:
        has_parallel = bool(re.search(rf'\.out\s*\(\s*{inst_name}', top_v))
        has_sout_port = bool(re.search(rf'\.sout\s*\(', top_v))
        if has_parallel:

            pass
        elif has_sout_port or f"{inst_name}_sout" in top_v:

            sout_wire = f"{inst_name}_sout"
            if sout_wire not in top_v:
                errors.append(f"Shift register '{inst_name}' (PISO/SISO) missing _sout wire")
        else:

            errors.append(f"Shift register '{inst_name}' has no output connected")
    return errors


PROTOCOL_CHECKS = {
    "uart_tx": lambda v: _check_uart_tx(v),
}

def _check_uart_tx(top_v: str) -> list[str]:
    errors = []

    if "read_fifo" not in top_v:
        errors.append("UART TX: missing read_fifo state (FIFO read timing bug)")

    if "TXFSM_idle" in top_v:
        if not re.search(r'TXFSM_idle\s*\)\s*\?\s*1\'b1', top_v):
            errors.append("UART TX: tx_out not 1'b1 in idle state")
   
    if "TXFSM_start_bit" in top_v:
        if not re.search(r'TXFSM_start_bit\s*\)\s*\?\s*1\'b0', top_v):
            errors.append("UART TX: tx_out not 1'b0 in start_bit state")
    
    if "cfgcnt_baud_counter" in top_v:
        if "TERMINAL_VALUE(BAUD_DIV)" not in top_v:
            errors.append("UART TX: baud_counter missing TERMINAL_VALUE(BAUD_DIV)")
    
    if "cfgcnt_bit_counter" in top_v:
        if "TERMINAL_VALUE(DATA_WIDTH-1)" not in top_v:
            errors.append("UART TX: bit_counter missing TERMINAL_VALUE(DATA_WIDTH-1)")
    
    if "shift_en_raw" not in top_v:
        errors.append("UART TX: missing shift_en_raw (shift_en gating not applied)")
    if "shift_en_raw & baud_counter_tc" not in top_v:
        errors.append("UART TX: assign shift_en = shift_en_raw & baud_counter_tc missing")
    return errors




async def run_circuit(circuit_key: str, hierarchy: dict, verbose: bool = False) -> dict:
    """
    Build circuit_key through the v2 pipeline directly.
    Returns { passed, errors, warnings, top_v, time_s }
    """
    t0 = time.time()
    errors   = []
    warnings = []
    top_v    = ""
    verilog_files = {}

    try:

        keywords = _CIRCUIT_KEYWORDS.get(circuit_key, [circuit_key.replace("_", " ")])
        prompt = keywords[0] if keywords else circuit_key.replace("_", " ")

        # Run the v2 pipeline (same as ai_assist → known route)
        result = await _run_hierarchical_v2(prompt, current_user="test_runner")

        if result.get("fallback"):
            errors.append(f"Circuit not found by _v2_classify with prompt '{prompt}'")
            return {"passed": False, "errors": errors, "warnings": warnings,
                    "top_v": "", "time_s": time.time() - t0}

        verilog_files = result.get("verilog_files", {})
        top_v         = verilog_files.get("top.v", "")

        if not top_v:
            errors.append("emit_verilog.py returned empty top.v")
            return {"passed": False, "errors": errors, "warnings": warnings,
                    "top_v": top_v, "time_s": time.time() - t0}

        # ── Level 1: iverilog ─────────────────────────────────────────────────
        errors   += check_iverilog(verilog_files)

        # ── Level 2: Structural ───────────────────────────────────────────────
        errors   += check_no_duplicate_declarations(top_v)
        warnings += check_no_orphan_wires(top_v)
        errors   += check_localparam_prefixes(top_v)
        errors   += check_terminal_values(top_v)
        errors   += check_data_width_parameterized(top_v)
        errors   += check_output_logic_state_names(top_v)
        errors   += check_no_dead_fsm_regs(top_v, circuit_key)
        errors   += check_shift_register_sout_connected(top_v)

        # ── Level 3: Protocol-specific ────────────────────────────────────────
        if circuit_key in PROTOCOL_CHECKS:
            errors += PROTOCOL_CHECKS[circuit_key](top_v)

    except Exception as e:
        import traceback
        errors.append(f"Pipeline crashed: {e}")
        if verbose:
            traceback.print_exc()

    return {
        "passed":   len(errors) == 0,
        "errors":   errors,
        "warnings": warnings,
        "top_v":    top_v,
        "time_s":   time.time() - t0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    args    = [a for a in sys.argv[1:] if not a.startswith("--")]
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    # Determine which circuits to test
    all_keys = list(_KNOWN_HIERARCHIES.keys())
    if args:
        keys = [k for k in args if k in all_keys]
        unknown = [k for k in args if k not in all_keys]
        if unknown:
            print(warn(f"Unknown circuit keys: {unknown}"))
    else:
        keys = all_keys

    print(f"\n{BOLD}RTLCopilot — Known Circuit Regression Suite{RESET}")
    print(f"Testing {len(keys)} circuit(s): {keys}\n")
    print("─" * 70)

    results = {}
    for key in keys:
        hierarchy = _KNOWN_HIERARCHIES[key]
        print(f"\n{CYAN}[{key}]{RESET} {hierarchy.get('description', '')}")

        result = await run_circuit(key, hierarchy, verbose=verbose)
        results[key] = result

        t = f"{result['time_s']:.1f}s"
        if result["passed"]:
            print(f"  {ok('PASSED')} ({t})")
        else:
            print(f"  {fail('FAILED')} ({t})")
            for e in result["errors"]:
                print(f"    {fail(e)}")

        for w in result["warnings"]:
            print(f"    {warn(w)}")

        if verbose and result["top_v"]:
            print(f"\n  --- top.v ---")
            print(result["top_v"])
            print(f"  --- end ---\n")

    print("\n" + "─" * 70)
    passed = [k for k, r in results.items() if r["passed"]]
    failed = [k for k, r in results.items() if not r["passed"]]
    total_time = sum(r["time_s"] for r in results.values())

    print(f"\n{BOLD}SUMMARY{RESET}  ({total_time:.1f}s total)")
    print(f"  {ok(f'Passed: {len(passed)}/{len(keys)}')}")
    if passed:
        print(f"     {', '.join(passed)}")

    if failed:
        print(f"  {fail(f'Failed: {len(failed)}/{len(keys)}')}")
        for k in failed:
            print(f"     {k}:")
            for e in results[k]["errors"]:
                print(f"       • {e}")

    print()
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    asyncio.run(main())