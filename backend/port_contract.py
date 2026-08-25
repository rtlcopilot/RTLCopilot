from __future__ import annotations

import math

# Width spec sentinels
ONE        = "1"
DATA       = "data"
ADDR       = "addr"
CLOG2_DATA = "clog2(data)"
TWICE_DATA = "2*data"
SERIAL     = "serial"
FREE       = None


# Handle spelling aliases -> canonical handle name.
# Keyed by (pattern, alias); a bare alias key applies to every pattern.
ALIASES: dict[str, str] = {
    "enable":       "en",
    "load_value":   "load_val",
    "reset":        "res",
    "pulse_out":    "out",
    "a_empty":      "ae",
    "almost_empty": "ae",
}

# Aliases that are only valid for one pattern. `out` is canonical for comb,
# mux and macro_edgedet, so it can only mean `q` on a shift register — hence
# the pattern scope rather than a global entry.
PATTERN_ALIASES: dict[tuple[str, str], str] = {
    ("macro_shiftreg", "out"): "q",
    ("macro_counter",  "out"): "count",
    ("macro_sync",     "out"): "q",
    ("reg",            "out"): "q",
}


def is_placeholder(handle: str) -> bool:
    """True for Stage-0 stand-in handles like <condition_signals>.

    These are filled in by Stage 3 with real signal names. Until then they must
    be excluded from every width and connectivity check — treating them as real
    1-bit ports produces conflicts nothing can fix.
    """
    h = str(handle or "").strip()
    return h.startswith("<") and h.endswith(">")


def canonical(handle: str, pattern: str | None = None) -> str:
    """Map an accepted handle spelling onto its canonical name.

    Pass `pattern` where it is known: some spellings (notably `out`) are only
    aliases for a specific pattern and canonical elsewhere.
    """
    if not handle:
        return handle
    h = str(handle).strip()
    if pattern:
        scoped = PATTERN_ALIASES.get((str(pattern).strip(), h))
        if scoped:
            return scoped
    return ALIASES.get(h, h)


# The contract 
# pattern -> {"inputs": {handle: spec}, "outputs": {handle: spec}}
#
# Indexed handle families (mux in0/in1/..., sel0/sel1/...) are declared with a
# trailing '*' and matched by prefix in _lookup_spec().

PATTERN_PORTS: dict[str, dict[str, dict]] = {

    # combinational
    # `comb` widths depend on comb_op, so its data ports carry DATA here and
    # resolve_width() narrows the OUTPUT for predicate ops (eq/gt/lt/...) and
    # widens it for mul. Inputs are always DATA regardless of op — this is the
    # fix for bitwise gates being stamped 1-bit while their operands are N-bit.
    "comb": {
        "inputs":  {"in*": DATA},
        "outputs": {"out": DATA},
    },
    "mux": {
        "inputs":  {"in*": DATA, "sel*": ONE},   # sel is split into 1-bit handles
        "outputs": {"out": DATA},
    },
    "const": {
        "inputs":  {"in": DATA},                 # optional pass-through driver
        "outputs": {"out": DATA},
    },
    "input":  {"inputs": {}, "outputs": {"out": DATA}},
    "output": {"inputs": {"in": DATA}, "outputs": {}},
    "probe":  {"inputs": {"in": FREE}, "outputs": {"out": FREE}},

    # Bit-slicing / joining nodes deliberately have no width contract: the
    # whole point of a splitter is that in and out widths differ.
    "splitter":     {"inputs": {"in": FREE}, "outputs": {"out": FREE}},
    "concatenator": {"inputs": {"in*": FREE}, "outputs": {"out": FREE}},
    "custom_block": {"inputs": {}, "outputs": {}},   # widths come from customPorts

    # sequential primitives
    "reg": {
        "inputs":  {"d": DATA, "en": ONE},
        "outputs": {"q": DATA},
    },
    "macro_sync": {
        # 2-FF CDC synchroniser: one instance per crossing bit.
        "inputs":  {"d": ONE},
        "outputs": {"q": ONE},
    },
    "macro_counter": {
        "inputs":  {"en": ONE, "res": ONE},
        "outputs": {"count": DATA, "tc": ONE},
    },
    "macro_cfgcounter": {
        "inputs":  {"en": ONE, "load": ONE, "load_val": DATA},
        "outputs": {"count": DATA, "tc": ONE},
    },
    "macro_shiftreg": {
        # din/q are the parallel side, sin/sout the serial side. Which side is
        # DATA and which is 1 bit depends on srMode — see resolve_width().
        "inputs":  {"din": DATA, "sin": SERIAL, "en": ONE, "load": ONE},
        "outputs": {"q": DATA, "sout": SERIAL},
    },
    "macro_fifo": {
        "inputs":  {"wr_en": ONE, "rd_en": ONE, "din": DATA},
        "outputs": {"dout": DATA, "full": ONE, "empty": ONE, "ae": ONE},
    },
    "macro_penc": {
        "inputs":  {"data_in": DATA},
        "outputs": {"index": CLOG2_DATA, "valid": ONE},
    },
    "macro_edgedet": {
        "inputs":  {"signal_in": ONE},
        "outputs": {"out": ONE},
    },
    "macro_dpram": {
        "inputs":  {"we_a": ONE, "addr_a": ADDR, "din_a": DATA,
                    "we_b": ONE, "addr_b": ADDR, "din_b": DATA},
        "outputs": {"dout_a": DATA, "dout_b": DATA},
    },
    "macro_rom": {
        "inputs":  {"addr": ADDR},
        "outputs": {"dout": DATA},
    },
    "encoder": {
        "inputs":  {"data_in": DATA},
        "outputs": {"out": CLOG2_DATA},
    },
    "decoder": {
        "inputs":  {"data_in": CLOG2_DATA},
        "outputs": {"out": DATA},
    },

    # control
    # FSM condition inputs and Moore outputs are single-bit by construction.
    "fsm": {
        "inputs":  {"*": ONE},
        "outputs": {"*": ONE},
    },
    "fsm_state": {
        "inputs":  {"*": ONE},
        "outputs": {"*": ONE},
    },
}

# comb ops whose output is a single-bit predicate, regardless of operand width.
COMB_PREDICATE_OPS = frozenset({"eq", "neq", "ne", "lt", "gt", "lte", "gte",
                                "le", "ge"})
# comb ops that are bitwise/arithmetic: output width == operand width.
COMB_WIDE_OPS = frozenset({"add", "sub", "and", "or", "xor", "xnor", "nand",
                           "nor", "not", "buf", "shl", "shr", "sra"})
# comb ops whose output is wider than the operands.
COMB_WIDENING_OPS = {"mul": TWICE_DATA}
# Single-operand ops — in1 must not be reported as unconnected for these.
COMB_UNARY_OPS = frozenset({"not", "buf"})

# Shift-register modes: (parallel-side spec, serial-side spec) validity.
_SR_SERIAL_OUT = frozenset({"PISO", "SISO"})
_SR_SERIAL_IN  = frozenset({"SIPO", "SISO"})


def _lookup_spec(pattern: str, handle: str, direction: str):
    """Find the width spec for a handle, honouring '*' families.

    Returns (found, spec). `found` is False when the pattern declares no such
    handle, which callers may treat as an error (unknown handle) rather than
    as an unconstrained width.
    """
    ports = PATTERN_PORTS.get(pattern)
    if not ports:
        return False, FREE
    table = ports.get(direction, {})
    if handle in table:
        return True, table[handle]
    # wildcard families: "in*" matches in0, in1, ...; "*" matches anything
    for key, spec in table.items():
        if key.endswith("*") and handle.startswith(key[:-1]):
            return True, spec
    return False, FREE


def resolve_width(
    pattern: str,
    handle: str,
    *,
    data_width: int = 8,
    direction: str = "inputs",
    comb_op: str | None = None,
    addr_width: int = 6,
    sr_mode: str | None = None,
) -> int | None:
    """Resolve a (pattern, handle) pair to a concrete bit width.

    Returns None when the handle is deliberately unconstrained (splitter,
    concatenator, probe, custom_block) — callers must skip width checks then
    rather than defaulting to 1.

    Raises KeyError for a handle the pattern does not declare, so a bad handle
    name surfaces as an error instead of silently resolving to the node width.
    """
    pattern = str(pattern or "").strip()
    handle  = canonical(handle, pattern)
    dw      = max(1, int(data_width or 1))
    aw      = max(1, int(addr_width or 1))

    # Placeholder handles (<condition_signals>, <fsm_output_signals>) are
    # stand-ins that Stage 3 replaces with real signal names. They are not
    # ports and have no width.
    #
    # The FSM pattern declares {"*": ONE}, so the wildcard matched these and
    # resolved them to 1 bit — which made the assembler report
    #   WIDTH CONFLICT fifo.dout(32) -> ctrl.<condition_signals>(1)
    # against a handle that does not exist yet. Retrying Stage 1 could never
    # clear it, so every multi-FSM design failed validation on a phantom.
    if is_placeholder(handle):
        return None

    found, spec = _lookup_spec(pattern, handle, direction)
    if not found:
        raise KeyError(f"{pattern} declares no {direction[:-1]} handle '{handle}'")

    # comb: the op decides the output width; operands stay at data width.
    if pattern == "comb" and direction == "outputs":
        op = str(comb_op or "").lower().strip()
        if op in COMB_PREDICATE_OPS:
            return 1
        if op in COMB_WIDENING_OPS:
            spec = COMB_WIDENING_OPS[op]

    # shift register: the serial side is 1 bit, the parallel side is data
    # width, and which handles are live depends on srMode.
    if pattern == "macro_shiftreg" and spec is SERIAL:
        return 1

    if spec is FREE:
        return None
    if spec == ONE:
        return 1
    if spec == DATA:
        return dw
    if spec == ADDR:
        return aw
    if spec == SERIAL:
        return 1
    if spec == CLOG2_DATA:
        return max(1, math.ceil(math.log2(max(dw, 2))))
    if spec == TWICE_DATA:
        return 2 * dw
    # numeric literal spec
    try:
        return max(1, int(spec))
    except (TypeError, ValueError):
        return dw


def port_widths(
    pattern: str,
    *,
    data_width: int = 8,
    comb_op: str | None = None,
    addr_width: int = 6,
    sr_mode: str | None = None,
    mux_size: int = 2,
) -> dict[str, dict[str, int | None]]:
    """Concrete {"inputs": {...}, "outputs": {...}} width maps for one node.

    Indexed handle families are expanded to real handle names: a mux with
    mux_size=8 yields in0..in7 and sel0..sel2, which is what Stage 1 must
    wire and what the canvas DRC checks against.
    """
    ports = PATTERN_PORTS.get(str(pattern or "").strip())
    if not ports:
        return {"inputs": {}, "outputs": {}}

    n_in     = max(2, int(mux_size or 2))
    sel_bits = max(1, math.ceil(math.log2(n_in)))
    unary    = str(comb_op or "").lower().strip() in COMB_UNARY_OPS
    out: dict[str, dict] = {"inputs": {}, "outputs": {}}

    for direction in ("inputs", "outputs"):
        for key in ports.get(direction, {}):
            if key == "*":
                continue                       # caller supplies FSM signal names
            if key == "in*" and pattern == "mux":
                names = [f"in{i}" for i in range(n_in)]
            elif key == "sel*":
                names = [f"sel{i}" for i in range(sel_bits)]
            elif key == "in*" and pattern == "comb":
                names = ["in0"] if unary else ["in0", "in1"]
            elif key == "in*":
                names = ["in0", "in1"]
            elif key.endswith("*"):
                names = [key[:-1] + "0"]
            else:
                names = [key]
            for nm in names:
                out[direction][nm] = resolve_width(
                    pattern, nm, data_width=data_width, direction=direction,
                    comb_op=comb_op, addr_width=addr_width, sr_mode=sr_mode)


    if pattern == "macro_shiftreg":
        mode = str(sr_mode or "PISO").upper().strip()
        keep_in  = "sin" if mode in _SR_SERIAL_IN  else "din"
        keep_out = "sout" if mode in _SR_SERIAL_OUT else "q"
        for h in ("din", "sin"):
            if h != keep_in:
                out["inputs"].pop(h, None)
        for h in ("q", "sout"):
            if h != keep_out:
                out["outputs"].pop(h, None)

    return out


def one_bit_handles(pattern: str) -> set[str]:
    """Handles that are 1 bit for every data width — the derived form of the
    hand-maintained _ONE_BIT_HANDLES tables this module replaces."""
    result = set()
    ports = PATTERN_PORTS.get(pattern, {})
    for direction in ("inputs", "outputs"):
        for handle, spec in ports.get(direction, {}).items():
            if spec in (ONE, SERIAL) and not handle.endswith("*"):
                result.add(handle)
            elif spec in (ONE, SERIAL) and handle.endswith("*"):
                result.add(handle)          # keep the family marker
    return result


def required_inputs(pattern: str, *, comb_op: str | None = None,
                    sr_mode: str | None = None,
                    mux_size: int = 2) -> list[str]:
    """Input handles that must be driven for the node to be meaningful.

    Deliberately narrower than "every declared input": optional enables and
    load ports are excluded, because warning about an unconnected `load` on
    every counter is noise, not a design rule.
    """
    if pattern == "comb":
        op = str(comb_op or "").lower().strip()
        return ["in0"] if op in COMB_UNARY_OPS else ["in0", "in1"]

    if pattern == "mux":
        n_in     = max(2, int(mux_size or 2))
        sel_bits = max(1, math.ceil(math.log2(n_in)))
        return ([f"in{i}" for i in range(n_in)] +
                [f"sel{i}" for i in range(sel_bits)])

    if pattern == "macro_shiftreg":
        mode = str(sr_mode or "PISO").upper().strip()
        return ["sin" if mode in _SR_SERIAL_IN else "din", "en"]

    return list(_REQUIRED_INPUTS.get(pattern, []))


_REQUIRED_INPUTS: dict[str, list[str]] = {
    "reg":               ["d"],
    "macro_sync":        ["d"],
    "macro_counter":     ["en"],
    "macro_cfgcounter":  ["en"],
    "macro_shiftreg":    ["en"],
    "macro_fifo":        ["din", "wr_en", "rd_en"],
    "macro_penc":        ["data_in"],
    "macro_edgedet":     ["signal_in"],
    "macro_dpram":       ["addr_a", "addr_b"],
    "macro_rom":         ["addr"],
    "encoder":           ["data_in"],
    "decoder":           ["data_in"],
    "output":            ["in"],
}


def handle_contract() -> dict:
    """JSON-serialisable contract for the frontend canvas DRC.

    Shipping the symbolic specs (rather than widths resolved against some
    assumed DATA_WIDTH) lets the canvas resolve per node, using each node's
    own width/addrWidth/muxSize/srMode — the same inputs the backend uses.
    """
    return {
        "version": 1,
        "specs": {
            "ONE": ONE, "DATA": DATA, "ADDR": ADDR,
            "CLOG2_DATA": CLOG2_DATA, "TWICE_DATA": TWICE_DATA,
            "SERIAL": SERIAL, "FREE": "free",
        },
        "patterns": {
            pat: {
                "inputs":  {h: ("free" if s is FREE else s)
                            for h, s in ports.get("inputs", {}).items()},
                "outputs": {h: ("free" if s is FREE else s)
                            for h, s in ports.get("outputs", {}).items()},
            }
            for pat, ports in PATTERN_PORTS.items()
        },
        "aliases": dict(ALIASES),
        "pattern_aliases": {f"{p}.{a}": c
                            for (p, a), c in PATTERN_ALIASES.items()},
        "comb_predicate_ops": sorted(COMB_PREDICATE_OPS),
        "comb_wide_ops":      sorted(COMB_WIDE_OPS),
        "comb_widening_ops":  dict(COMB_WIDENING_OPS),
        "required_inputs":    {k: list(v) for k, v in _REQUIRED_INPUTS.items()},
        "shiftreg_serial_out": sorted(_SR_SERIAL_OUT),
        "shiftreg_serial_in":  sorted(_SR_SERIAL_IN),
    }


def describe_handles(pattern: str, *, mux_size: int = 2,
                     sr_mode: str | None = None) -> dict[str, list[str]]:
    """Handle name lists for Stage 1 prompt construction — the expanded,
    canonical names the LLM is allowed to wire (never invented, never
    abbreviated)."""
    pw = port_widths(pattern, mux_size=mux_size, sr_mode=sr_mode)
    return {"inputs": list(pw["inputs"].keys()),
            "outputs": list(pw["outputs"].keys())}