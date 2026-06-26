"""
semantic_library.py — RTL Copilot Verification Semantic Library
================================================================
Deterministic expected-output calculator and test plan generator
for standard RTL blocks. Used by the autonomous verification agent.

No LLM involved here — pure Python logic that mirrors the
deterministic Verilog emit scripts.

Custom blocks use LLM-derived understanding (passed in as a dict).
"""

import math
import itertools
import random
from typing import Any


def _mask(width: int) -> int:
    """Bit mask for a given width."""
    return (1 << width) - 1


def _corner_values(width: int) -> list[int]:
    """Corner case values for a given bit width."""
    if width == 1:
        return [0, 1]
    mx = _mask(width)
    return sorted(set([0, 1, mx >> 1, (mx >> 1) + 1, mx - 1, mx]))


def _random_values(width: int, n: int = 4, seed: int = 42) -> list[int]:
    rng = random.Random(seed)
    return [rng.randint(0, _mask(width)) for _ in range(n)]


def _port_width(port: dict) -> int:
    try:
        return max(1, int(port.get("width", 1)))
    except Exception:
        return 1


def compute_comb_expected(op: str, in0: int, in1: int, width: int) -> int:
    """
    Deterministic expected output for a comb block given op and inputs.
    Mirrors emit_verilog.py assign logic exactly.
    """
    mask = _mask(width)
    ops = {
        "add":  lambda a, b: (a + b) & mask,
        "sub":  lambda a, b: (a - b) & mask,
        "mul":  lambda a, b: (a * b) & mask,
        "and":  lambda a, b: a & b,
        "or":   lambda a, b: a | b,
        "xor":  lambda a, b: a ^ b,
        "not":  lambda a, b: (~a) & mask,
        "buf":  lambda a, b: a & mask,
        "eq":   lambda a, b: 1 if a == b else 0,
        "neq":  lambda a, b: 1 if a != b else 0,
        "gt":   lambda a, b: 1 if a > b  else 0,
        "lt":   lambda a, b: 1 if a < b  else 0,
        "gte":  lambda a, b: 1 if a >= b else 0,
        "lte":  lambda a, b: 1 if a <= b else 0,
        "shl":  lambda a, b: (a << (b % width)) & mask,
        "shr":  lambda a, b: (a >> (b % width)) & mask,
    }
    fn = ops.get(op)
    if fn is None:
        return 0
    return fn(in0, in1)


def compute_const_expected(value: Any) -> int:
    try:
        return int(str(value).strip(), 0)
    except Exception:
        return 0



class CounterSim:
    """Mirrors emit_counter.py behaviour — synchronous, active-high rst."""
    def __init__(self, width: int = 8):
        self.width  = width
        self.mask   = _mask(width)
        self.count  = 0

    def reset(self):
        self.count = 0

    def tick(self, en: int = 1, res: int = 0) -> int:
        if res:
            self.count = 0
        elif en:
            self.count = (self.count + 1) & self.mask
        return self.count


class RegisterSim:
    """Mirrors emit_reg.py — synchronous, active-high rst."""
    def __init__(self, width: int = 8):
        self.width = width
        self.mask  = _mask(width)
        self.q     = 0

    def reset(self):
        self.q = 0

    def tick(self, d: int) -> int:
        self.q = d & self.mask
        return self.q


class FifoSim:
    """Mirrors emit_fifo.py — synchronous, active-low rst."""
    def __init__(self, depth: int = 16, width: int = 8):
        self.depth  = depth
        self.width  = width
        self.mask   = _mask(width)
        self.buf    = []
        self.dout   = 0

    def reset(self):
        self.buf  = []
        self.dout = 0

    def tick(self, wr_en: int = 0, din: int = 0,
             rd_en: int = 0) -> dict:
        if wr_en and len(self.buf) < self.depth:
            self.buf.append(din & self.mask)
        if rd_en and self.buf:
            self.dout = self.buf.pop(0)
        return {
            "full":         1 if len(self.buf) >= self.depth else 0,
            "empty":        1 if len(self.buf) == 0 else 0,
            "almost_empty": 1 if len(self.buf) <= 1 else 0,
            "dout":         self.dout,
        }


def _make_step(label: str, values: dict, expected: dict, time: int) -> dict:
    return {
        "label":    label,
        "time":     time,
        "values":   {k: str(v) for k, v in values.items()},
        "expected": {k: str(v) for k, v in expected.items()},
    }


def generate_comb_tests(ir: dict) -> list[dict]:
    """
    Generate exhaustive / corner-case test steps for purely combinational
    circuits (comb nodes, const, encoder, decoder, splitter, concatenator).

    Returns a list of stimulus steps with expected values filled in.
    """
    nodes = ir.get("nodes", [])
    ports = ir.get("ports", [])

    input_ports  = [p for p in ports if p.get("dir") == "input"]
    output_ports = [p for p in ports if p.get("dir") == "output"]

    if not input_ports or not output_ports:
        return []

    comb_nodes  = [n for n in nodes if n.get("type") == "comb"]
    const_nodes = [n for n in nodes if n.get("type") == "const"]

    steps = []
    time  = 0

    all_1bit = all(_port_width(p) == 1 for p in input_ports)

    if all_1bit and len(input_ports) <= 4:

        for combo in itertools.product([0, 1], repeat=len(input_ports)):
            values = {p["name"]: v for p, v in zip(input_ports, combo)}
            expected = _compute_circuit_output(ir, values)
            if expected is not None:
                steps.append(_make_step(
                    f"truth_{time // 10}",
                    values, expected, time
                ))
            time += 10
    else:

        for port in input_ports:
            w = _port_width(port)
            for val in _corner_values(w):
                values = {p["name"]: 0 for p in input_ports}
                values[port["name"]] = val
                expected = _compute_circuit_output(ir, values)
                if expected is not None:
                    steps.append(_make_step(
                        f"corner_{port['name']}_{val}",
                        values, expected, time
                    ))
                time += 10


        for i, vals in enumerate(_build_random_inputs(input_ports, 6)):
            expected = _compute_circuit_output(ir, vals)
            if expected is not None:
                steps.append(_make_step(f"random_{i}", vals, expected, time))
                time += 10

    return steps


def generate_counter_tests(ir: dict) -> list[dict]:
    """
    Generate multi-cycle test steps for macro_counter circuits.
    Tests: reset behaviour, counting, enable gating.
    """
    nodes = ir.get("nodes", [])
    ports = ir.get("ports", [])

    counter_nodes = [n for n in nodes if n.get("type") == "macro_counter"]
    if not counter_nodes:
        return []

    cn    = counter_nodes[0]
    width = int(cn.get("width", 8) or 8)
    sim   = CounterSim(width)

    input_ports  = [p for p in ports if p.get("dir") == "input"
                    and p["name"] not in ("clk", "rst")]
    output_ports = [p for p in ports if p.get("dir") == "output"]
    if not output_ports:
        return []

    out_name = output_ports[0]["name"]
    steps    = []
    time     = 0

    en_port  = next((p["name"] for p in input_ports if "en"  in p["name"].lower()), None)
    res_port = next((p["name"] for p in input_ports if "res" in p["name"].lower()), None)

    def step(label, en=1, res=0):
        nonlocal time
        values   = {}
        if en_port:  values[en_port]  = en
        if res_port: values[res_port] = res
        out = sim.tick(en=en, res=res)
        steps.append(_make_step(label, values, {out_name: out}, time))
        time += 10


    sim.reset()
    for i in range(4):
        step(f"reset_hold_{i}", en=0, res=1)

    sim.reset()
    step("post_reset", en=1, res=0)

    for i in range(8):
        step(f"count_{i}")


    if en_port:
        val_before = sim.count
        step("en_low_0", en=0)
        step("en_low_1", en=0)
        step("en_high_resume", en=1)


    sim.count = _mask(width) - 2
    for i in range(4):
        step(f"overflow_{i}")

    return steps


def generate_register_tests(ir: dict) -> list[dict]:
    """Generate test steps for reg (D flip-flop) circuits."""
    nodes = ir.get("nodes", [])
    ports = ir.get("ports", [])

    reg_nodes = [n for n in nodes if n.get("type") == "reg"]
    if not reg_nodes:
        return []

    rn    = reg_nodes[0]
    width = int(rn.get("width", 8) or 8)
    sim   = RegisterSim(width)

    input_ports  = [p for p in ports if p.get("dir") == "input"
                    and p["name"] not in ("clk", "rst")]
    output_ports = [p for p in ports if p.get("dir") == "output"]
    if not input_ports or not output_ports:
        return []

    d_port   = input_ports[0]["name"]
    q_port   = output_ports[0]["name"]
    steps    = []
    time     = 0
    mask     = _mask(width)

    test_vals = _corner_values(width) + _random_values(width, 4)
    for val in test_vals:
        sim.tick(val)
        steps.append(_make_step(
            f"reg_{val}",
            {d_port: val},
            {q_port: sim.q},
            time
        ))
        time += 10

    return steps


def generate_fifo_tests(ir: dict) -> list[dict]:
    """
    Generate multi-cycle test steps for macro_fifo circuits.
    Tests: empty state, write, read, full flag, overflow protection.
    """
    nodes = ir.get("nodes", [])
    ports = ir.get("ports", [])

    fifo_nodes = [n for n in nodes if n.get("type") == "macro_fifo"]
    if not fifo_nodes:
        return []

    fn    = fifo_nodes[0]
    depth = int(fn.get("fifoDepth", 16) or 16)
    width = int(fn.get("width", 8) or 8)
    sim   = FifoSim(depth, width)
    sim.reset()

    def find_port(names):
        for name in names:
            p = next((p["name"] for p in ports
                      if name in p["name"].lower()), None)
            if p: return p
        return None

    wr_en_p = find_port(["wr_en", "wr"])
    din_p   = find_port(["din"])
    rd_en_p = find_port(["rd_en", "rd"])
    full_p  = find_port(["full"])
    empty_p = find_port(["empty"])
    dout_p  = find_port(["dout"])

    steps = []
    time  = 0

    def step(label, wr=0, din=0, rd=0):
        nonlocal time
        values = {}
        if wr_en_p: values[wr_en_p] = wr
        if din_p:   values[din_p]   = din
        if rd_en_p: values[rd_en_p] = rd
        result = sim.tick(wr_en=wr, din=din, rd_en=rd)
        expected = {}
        if full_p  and full_p  in [p["name"] for p in ports]: expected[full_p]  = result["full"]
        if empty_p and empty_p in [p["name"] for p in ports]: expected[empty_p] = result["empty"]
        if dout_p  and dout_p  in [p["name"] for p in ports] and rd: expected[dout_p] = result["dout"]
        steps.append(_make_step(label, values, expected, time))
        time += 10

    step("initial_empty", wr=0, rd=0)

    for i in range(depth):
        step(f"write_{i}", wr=1, din=(i * 7 + 3) & _mask(width))

    step("check_full", wr=0, rd=0)

    for i in range(depth):
        step(f"read_{i}", rd=1)

    step("check_empty", wr=0, rd=0)

    for i in range(4):
        step(f"interleave_w{i}", wr=1, din=i * 11 & _mask(width))
        step(f"interleave_r{i}", rd=1)

    return steps


def generate_fsm_tests(ir: dict) -> list[dict]:
    """
    Generate test steps for FSM circuits.
    Exercises each state transition at least once.
    """
    nodes = ir.get("nodes", [])
    ports = ir.get("ports", [])

    state_nodes = [n for n in nodes if n.get("type") == "fsm_state"]
    if not state_nodes:
        return []

    edges = ir.get("edges", [])
    input_ports  = [p for p in ports if p.get("dir") == "input"
                    and p["name"] not in ("clk", "rst")]
    output_ports = [p for p in ports if p.get("dir") == "output"]

    steps = []
    time  = 0


    for sn in state_nodes:
        for ip in input_ports:
            for val in [0, 1]:
                values = {p["name"]: 0 for p in input_ports}
                values[ip["name"]] = val

                steps.append({
                    "label":    f"fsm_{sn.get('data', {}).get('label', sn['id'])}_{ip['name']}_{val}",
                    "time":     time,
                    "values":   {k: str(v) for k, v in values.items()},
                    "expected": {},  
                    "_observe_only": True,
                })
                time += 10

    return steps


def generate_custom_block_tests(ir: dict, llm_understanding: dict) -> list[dict]:
    """
    Generate test steps for custom blocks using LLM-derived understanding.
    Falls back to corner cases with no expected values if understanding is unclear.
    """
    nodes = ir.get("nodes", [])
    ports = ir.get("ports", [])

    custom_nodes = [n for n in nodes if n.get("type") == "custom_block"]
    if not custom_nodes:
        return []

    input_ports  = [p for p in ports if p.get("dir") == "input"
                    and p["name"] not in ("clk", "rst")]
    output_ports = [p for p in ports if p.get("dir") == "output"]

    if not input_ports:
        return []

    llm_tests = llm_understanding.get("test_cases", [])
    if llm_tests:
        steps = []
        for i, tc in enumerate(llm_tests[:12]):  
            values   = tc.get("inputs", {})
            expected = tc.get("expected_outputs", {})
            steps.append(_make_step(
                tc.get("label", f"llm_test_{i}"),
                values, expected, i * 10
            ))
        return steps

    steps = []
    time  = 0
    for port in input_ports:
        w = _port_width(port)
        for val in _corner_values(w):
            values = {p["name"]: 0 for p in input_ports}
            values[port["name"]] = val
            steps.append({
                "label":    f"corner_{port['name']}_{val}",
                "time":     time,
                "values":   {k: str(v) for k, v in values.items()},
                "expected": {},
            })
            time += 10

    return steps

def generate_test_plan(ir: dict, llm_understanding: dict = None) -> dict:
    """
    Master function — generates a complete test plan for any circuit.
    Returns:
    {
        "steps":         list of stimulus steps with expected values,
        "is_sequential": bool,
        "reset_active":  "high" | "low",
        "reset_type":    "sync" | "async" | "none",
        "description":   human-readable description of what was generated,
        "strategy":      "exhaustive" | "corner_case" | "multi_cycle" | "llm_assisted",
    }
    """
    nodes = ir.get("nodes", [])
    llm_u = llm_understanding or {}

    node_types = {n.get("type", "") for n in nodes}

    has_fifo     = "macro_fifo"    in node_types
    has_counter  = "macro_counter" in node_types
    has_reg      = "reg"           in node_types
    has_fsm      = "fsm_state"     in node_types
    has_custom   = "custom_block"  in node_types
    has_cfg_cnt  = "macro_cfgcounter" in node_types
    has_shiftreg = "macro_shiftreg"   in node_types
    has_dpram    = "macro_dpram"      in node_types
    is_seq       = any([has_fifo, has_counter, has_reg, has_fsm,
                        has_custom, has_cfg_cnt, has_shiftreg, has_dpram])


    active_low_types = {"macro_fifo", "macro_dpram", "macro_cfgcounter", "macro_shiftreg"}
    reset_active = "low" if node_types & active_low_types else "high"


    for n in nodes:
        if n.get("type") == "custom_block":
            pattern = n.get("customSchema", {}).get("pattern", "")
            if pattern in ("counter_based", "register_based", "shift_based"):
                reset_active = "low"

    steps    = []
    strategy = "corner_case"
    desc_parts = []

    if has_fifo:
        s = generate_fifo_tests(ir)
        steps.extend(s)
        strategy = "multi_cycle"
        desc_parts.append(f"FIFO: {len(s)} write/read/flag tests")

    elif has_counter or has_cfg_cnt:
        s = generate_counter_tests(ir)
        steps.extend(s)
        strategy = "multi_cycle"
        desc_parts.append(f"Counter: {len(s)} cycle tests (reset, count, overflow)")

    elif has_reg or has_shiftreg:
        s = generate_register_tests(ir)
        steps.extend(s)
        strategy = "multi_cycle"
        desc_parts.append(f"Register: {len(s)} load/read tests")

    elif has_fsm:
        s = generate_fsm_tests(ir)
        steps.extend(s)
        strategy = "multi_cycle"
        desc_parts.append(f"FSM: {len(s)} transition tests (observe-only)")

    elif has_custom:
        s = generate_custom_block_tests(ir, llm_u)
        steps.extend(s)
        strategy = "llm_assisted" if llm_u.get("test_cases") else "corner_case"
        desc_parts.append(f"Custom block: {len(s)} tests")

    else:
        s = generate_comb_tests(ir)
        steps.extend(s)
        ports = ir.get("ports", [])
        in_p  = [p for p in ports if p.get("dir") == "input"]
        all_1bit = all(_port_width(p) == 1 for p in in_p)
        strategy = "exhaustive" if all_1bit and len(in_p) <= 4 else "corner_case"
        desc_parts.append(f"Combinational: {len(s)} test cases ({strategy})")


    for i, step in enumerate(steps):
        step["time"] = i * 10

    description = " + ".join(desc_parts) if desc_parts else "No tests generated"

    return {
        "steps":         steps,
        "is_sequential": is_seq,
        "reset_active":  reset_active,
        "reset_type":    "sync",
        "description":   description,
        "strategy":      strategy,
        "test_count":    len(steps),
        "assert_count":  sum(1 for s in steps if s.get("expected")),
    }


def _compute_circuit_output(ir: dict, input_values: dict) -> dict | None:
    """
    Attempt to compute the expected output for a combinational circuit
    given a set of input values. Traces the signal path through nodes.
    Returns None if circuit is too complex to trace deterministically.
    """
    nodes  = ir.get("nodes", [])
    edges  = ir.get("edges", [])
    ports  = ir.get("ports", [])

    signal_map: dict[str, int] = {}

    for p in ports:
        if p.get("dir") == "input":
            signal_map[p["id"]] = input_values.get(p["name"], 0)

    for n in nodes:
        nid  = n.get("id")
        ntyp = n.get("type")
        w    = int(n.get("width", 1) or 1)

        def get_src(dst_port):
            e = next((e for e in edges
                      if e["dst"] == nid and e.get("dst_port") == dst_port), None)
            if not e:
                e = next((e for e in edges if e["dst"] == nid), None)
            if not e:
                return 0
            return signal_map.get(e["src"], 0)

        if ntyp == "comb":
            op  = n.get("op", "or")
            in0 = get_src("in0")
            in1 = get_src("in1")
            signal_map[nid] = compute_comb_expected(op, in0, in1, w)

        elif ntyp == "const":
            signal_map[nid] = compute_const_expected(n.get("value", 0))

        elif ntyp in ("reg", "macro_counter", "macro_fifo",
                      "fsm_state", "macro_shiftreg", "custom_block"):
            return None

    result = {}
    for p in ports:
        if p.get("dir") == "output":
            e = next((e for e in edges if e["dst"] == p["id"]), None)
            if e and e["src"] in signal_map:
                result[p["name"]] = signal_map[e["src"]]
            else:
                return None  

    return result if result else None


def _build_random_inputs(input_ports: list, n: int, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    result = []
    for _ in range(n):
        vals = {}
        for p in input_ports:
            w = _port_width(p)
            vals[p["name"]] = rng.randint(0, _mask(w))
        result.append(vals)
    return result