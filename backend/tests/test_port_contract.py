"""
test_port_contract.py — validates the port contract and lints every entry in
_KNOWN_HIERARCHIES against it.

Run:  python3 -m tests.test_port_contract     (from backend/)

The lint is the point: a known circuit that declares a handle the contract
does not model, or an import width that disagrees with the contract, would
produce canvas DRC errors for the user. Catching that here means a broken
hierarchy never ships.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import port_contract as pc
from known_circuits import _KNOWN_HIERARCHIES
from block_mapper import GENERIC_VOCABULARY, map_concepts_to_primitives

FAILURES: list[str] = []
WARNINGS: list[str] = []


def fail(msg):
    FAILURES.append(msg)


def warn(msg):
    WARNINGS.append(msg)


def _int(v, default=8):
    try:
        return max(1, int(str(v).strip()))
    except (TypeError, ValueError):
        return default


# ── 1. contract self-consistency ────────────────────────────────────────────

def test_contract_basics():
    # bitwise ops must be operand-width on BOTH sides (the 8-bit ALU bug)
    for op in ("and", "or", "xor", "not"):
        for d in ("inputs", "outputs"):
            h = "in0" if d == "inputs" else "out"
            w = pc.resolve_width("comb", h, direction=d, data_width=8, comb_op=op)
            if w != 8:
                fail(f"comb({op}).{h} resolved to {w}, expected 8")

    # predicates: operands wide, result 1 bit
    for op in ("eq", "gt", "lt"):
        if pc.resolve_width("comb", "in0", data_width=8, comb_op=op) != 8:
            fail(f"comb({op}).in0 should be 8 bits")
        if pc.resolve_width("comb", "out", direction="outputs",
                            data_width=8, comb_op=op) != 1:
            fail(f"comb({op}).out should be 1 bit")

    # mul widens
    if pc.resolve_width("comb", "out", direction="outputs",
                        data_width=8, comb_op="mul") != 16:
        fail("comb(mul).out should be 2*data")

    # every sel bit is its own 1-bit handle
    pw = pc.port_widths("mux", data_width=8, mux_size=8)
    if sorted(pw["inputs"]) != sorted([f"in{i}" for i in range(8)] +
                                      [f"sel{i}" for i in range(3)]):
        fail(f"8:1 mux handle set wrong: {sorted(pw['inputs'])}")
    if any(pw["inputs"][f"sel{i}"] != 1 for i in range(3)):
        fail("mux sel bits must be 1 bit each")

    # aliases resolve
    if pc.resolve_width("macro_cfgcounter", "enable", data_width=8) != 1:
        fail("alias enable->en did not resolve")

    # unconstrained handles return None, not 1
    if pc.resolve_width("splitter", "in") is not None:
        fail("splitter.in must be unconstrained (None)")

    # unknown handles raise rather than silently resolving
    try:
        pc.resolve_width("reg", "not_a_handle")
        fail("unknown handle did not raise KeyError")
    except KeyError:
        pass


# ── 2. the mapper produces contract-consistent concepts ─────────────────────

def test_mapper_covers_vocabulary():
    concepts = [{"generic_type": g, "suggested_id": g} for g in GENERIC_VOCABULARY]
    mapped, err = map_concepts_to_primitives(concepts)
    if err:
        fail(f"mapper rejected part of its own vocabulary: {err}")
        return
    if len(mapped) != len(GENERIC_VOCABULARY):
        fail(f"mapped {len(mapped)} of {len(GENERIC_VOCABULARY)} generics")

    for m in mapped:
        if m["pattern"] in ("fsm", "fsm_state"):
            continue
        hw = m["handle_widths"]
        for direction in ("inputs", "outputs"):
            for handle, width in hw[direction].items():
                if width is not None and width < 1:
                    fail(f"{m['id']}.{handle} resolved to {width}")
        # advertised handle list must match the resolved width map
        if set(m["handles"]["inputs"]) != set(hw["inputs"]):
            fail(f"{m['id']}: handles/handle_widths disagree on inputs")


# ── 3. lint every known hierarchy against the contract ──────────────────────

def test_known_hierarchies():
    for key, hier in _KNOWN_HIERARCHIES.items():
        scs = {sc["id"]: sc for sc in hier.get("sub_circuits", [])}

        for sc_id, sc in scs.items():
            pattern = sc["pattern"]
            if pattern in ("fsm", "fsm_state"):
                continue          # handle names are design signals
            data    = sc.get("data", {})
            dw      = _int(data.get("width", 8))
            aw      = _int(data.get("addrWidth", 6), 6)
            comb_op = sc.get("comb_op") or data.get("op")
            sr_mode = data.get("srMode")
            mux_sz  = _int(data.get("muxSize", 2), 2)

            expected = pc.port_widths(
                pattern, data_width=dw, comb_op=comb_op,
                addr_width=aw, sr_mode=sr_mode, mux_size=mux_sz)

            for imp in sc.get("imports", []):
                h = pc.canonical(imp.get("handle", ""), pattern)
                if h not in expected["inputs"]:
                    fail(f"[{key}] {sc_id}: import handle '{h}' not declared "
                         f"for pattern '{pattern}' "
                         f"(valid: {sorted(expected['inputs'])})")
                    continue
                want = expected["inputs"][h]
                got  = _int(imp.get("width", want))
                if want is not None and got != want:
                    fail(f"[{key}] {sc_id}.{h}: declared width {got}, "
                         f"contract says {want}")

            for exp in sc.get("exports", []):
                h = pc.canonical(exp.get("handle", ""), pattern)
                if not h:
                    continue      # FSM-style exports carry signal names only
                if h not in expected["outputs"]:
                    fail(f"[{key}] {sc_id}: export handle '{h}' not declared "
                         f"for pattern '{pattern}' "
                         f"(valid: {sorted(expected['outputs'])})")
                    continue
                want = expected["outputs"][h]
                got  = _int(exp.get("width", want))
                if want is not None and got != want:
                    fail(f"[{key}] {sc_id}.{h}: export width {got}, "
                         f"contract says {want}")

            # required inputs must actually be driven
            # An import whose `from` is "external" is only really driven if a
            # top_level_input routes to it. Counting the import entry alone let
            # the ALU ship with op_sub/op_and/... floating.
            driven = {pc.canonical(i.get("handle", ""), pattern)
                      for i in sc.get("imports", [])
                      if i.get("from") not in ("external", "", None)}
            tl_driven = {pc.canonical(t.get("dst_handle", ""), pattern)
                         for t in hier.get("top_level_inputs", [])
                         if t.get("to") == sc_id}
            driven |= tl_driven
            # Control handles (en/load/wr_en/rd_en) are autowired from FSM
            # outputs at assembly time, so they are legitimately absent from a
            # static hierarchy that contains an FSM.
            has_fsm = any(x.get("pattern") == "fsm" for x in scs.values())
            autowired = {"en", "load", "wr_en", "rd_en"} if has_fsm else set()
            for req in pc.required_inputs(pattern, comb_op=comb_op,
                                          sr_mode=sr_mode, mux_size=mux_sz):
                if req not in driven and req not in autowired:
                    warn(f"[{key}] {sc_id}: required input '{req}' undriven")

        # internal source references must exist
        for sc_id, sc in scs.items():
            for imp in sc.get("imports", []):
                frm = imp.get("from", "external")
                if frm not in ("external", "", None) and frm not in scs:
                    fail(f"[{key}] {sc_id}: import from unknown block '{frm}'")


def main():
    test_contract_basics()
    test_mapper_covers_vocabulary()
    test_known_hierarchies()

    print(f"\n{'='*66}")
    if WARNINGS:
        print(f"WARNINGS ({len(WARNINGS)}):")
        for w in WARNINGS:
            print(f"  ! {w}")
    if FAILURES:
        print(f"\nFAILURES ({len(FAILURES)}):")
        for f in FAILURES:
            print(f"  x {f}")
        print(f"{'='*66}")
        return 1
    print(f"PASS — contract consistent, {len(_KNOWN_HIERARCHIES)} known "
          f"hierarchies lint clean ({len(WARNINGS)} warnings)")
    print(f"{'='*66}")
    return 0


if __name__ == "__main__":
    sys.exit(main())