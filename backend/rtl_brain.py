from __future__ import annotations

import asyncio
import cosim as _cosim
import datetime as _dt
import os
import json
import re
import math
import traceback as _tb
from fastapi import HTTPException
from block_mapper import map_concepts_to_primitives, GENERIC_VOCABULARY, get_stage0_vocabulary_prompt
from known_circuits import PRIMITIVE_BLOCK_SPECS as _PRIM_SPECS, _KNOWN_HIERARCHIES as _KC_HIERARCHIES, _CIRCUIT_KEYWORDS as _KC_KEYWORDS
import port_contract as _pc
from core import *
from prompts import *
from ir_checks import *
import state
from state import _FSM_TRANSITION_TABLES
from verilog_tools import _iverilog_compile_check
from hierarchical_v2 import _run_hierarchical_v2_from_hierarchy
from generation_errors import GenerationFailure as _GenFail


def _build_vocabulary_prompt() -> str:
    """
    Build the primitive block vocabulary string injected into Stage 1 prompt.
    Derived from PRIMITIVE_BLOCK_SPECS so it stays in sync automatically.
    Includes exact handle names so LLM uses correct port identifiers.
    """
    lines = ["PRIMITIVE BLOCKS (always available — use pattern name exactly):"]
    for pattern, spec in _PRIM_SPECS.items():
        # Use exact handle names — LLM MUST use these in imports/exports
        inputs  = ", ".join(
            f"{p['name']} (handle='{p['name']}')" for p in spec["ports"]["inputs"]
        )
        outputs = ", ".join(
            f"{p['name']} (handle='{p['name']}')" for p in spec["ports"]["outputs"]
        )
        lines.append(
            f"  {pattern}:\n"
            f"    description: {spec['description']}\n"
            f"    inputs  (use exact handle names): {inputs}\n"
            f"    outputs (use exact handle names): {outputs}\n"
            f"    usage:   {spec['usage']}"
        )

    lines.append("\nKNOWN VERIFIED CIRCUITS (can be used as sub-modules — use pattern='known_circuit'):")
    for key, hier in _KC_HIERARCHIES.items():
        top_ins  = [p["name"] for p in hier.get("top_level_inputs",  [])]
        top_outs = [p["name"] for p in hier.get("top_level_outputs", [])]
        lines.append(
            f"  {key}: {hier['description']}\n"
            f"    top-level inputs:  {top_ins}\n"
            f"    top-level outputs: {top_outs}"
        )

    lines.append(
        "\nRULES:\n"
        "  - Every sub_circuit pattern MUST be one of the primitive block names above,\n"
        "    or 'known_circuit' for a known verified circuit.\n"
        "  - NEVER invent a pattern name that is not in this list.\n"
        "  - If the circuit cannot be built from these blocks, say so explicitly\n"
        "    in the description field and return an empty sub_circuits list."
    )
    return "\n".join(lines)


def _rtl_brain_extract_json(raw: str) -> dict | None:
    """Extract and parse JSON from LLM response. Returns None on failure."""
    try:
        if "```json" in raw:
            s = raw.find("```json") + 7
            e = raw.find("```", s)
            raw = raw[s:e].strip()
        elif "```" in raw:
            s = raw.find("```") + 3
            e = raw.rfind("```")
            raw = raw[s:e].strip()

        if "{" not in raw:
            return None
        depth, start, end = 0, raw.find("{"), -1
        for i, ch in enumerate(raw[raw.find("{"):], raw.find("{")):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            return None
        return json.loads(raw[start:end+1])
    except Exception:
        return None


def _build_stage0_vocabulary() -> str:
    """Returns the closed generic vocabulary injected into Stage 0 prompt."""
    return get_stage0_vocabulary_prompt()


# Set when Stage 0's LLM call fails for a reason the user can fix in Settings
# (bad key, wrong provider, retired model ID) rather than a model-quality
# problem. Without this, all three surface as "couldn't decompose your request".
# Datapath control handles that an FSM drives. Stage 1 is forbidden from
# wiring these; _rtl_brain_autowire_fsm connects them from FSM outputs.
_FSM_OWNED_HANDLES = {"en", "load", "wr_en", "rd_en", "res"}

# Comparison operators Stage 0 may request via a concept's compare_op field.
_VALID_COMPARE_OPS = {"eq", "neq", "gt", "lt", "gte", "lte"}


def _apply_compare_ops(concepts: list, mapped: list) -> list:
    """Honour Stage 0's compare_op on comparator-class blocks.

    block_mapper maps every 'comparator' to comb_op=eq, because that is what
    the word means in isolation. But a peak detector asks for a comparator and
    means '>'; the emitted design then compared for equality and silently
    became a sample register. The vocabulary name and the operation were fixed
    to each other with no way for the request to influence it.

    Stage 0 now names the operator, and it is applied here so neither
    block_mapper nor prompts.py needs to change.
    """
    by_id = {}
    for c in concepts or []:
        cid = c.get("suggested_id") or c.get("generic_type")
        op = str(c.get("compare_op", "")).lower().strip()
        if cid and op in _VALID_COMPARE_OPS:
            by_id[cid] = op
    for m in mapped or []:
        want = by_id.get(m.get("id"))
        if want and m.get("pattern") == "comb" and m.get("comb_op") != want:
            print(f"[MAPPER] '{m['id']}' compare_op: "
                  f"{m.get('comb_op')} -> {want} (from Stage 0)", flush=True)
            m["comb_op"] = want
    return mapped

_stage0_config_error: str | None = None


def _set_config_error(msg: str) -> None:
    global _stage0_config_error
    _stage0_config_error = msg


# ── rate-limit aware LLM call ───────────────────────────────────────────────
# Free tiers meter tokens per MINUTE, but this pipeline fires 3-4 sequential
# calls within seconds, so one generation can exhaust a whole minute's budget
# partway through and fail at Stage 1 or 2 having already done the work of
# Stage 0.
#
# Providers say exactly how long to wait ("Please try again in 22.95s"), and
# retrying immediately — as the pipeline used to — guarantees a second failure
# and burns the retry allowance for nothing. Waiting is slower but finishes.

_RETRY_AFTER_RE = re.compile(r"try again in\s+([0-9.]+)\s*s", re.I)
_MAX_RATE_LIMIT_WAIT = float(os.environ.get("LLM_MAX_RATE_WAIT", "75"))


def _retry_after_seconds(exc: Exception) -> float | None:
    """Seconds the provider asked us to wait, or None if not a rate limit."""
    name, msg = type(exc).__name__, str(exc)
    if "RateLimit" not in name and "429" not in msg and "rate_limit" not in msg:
        return None
    hdrs = getattr(getattr(exc, "response", None), "headers", None) or {}
    for key in ("retry-after", "x-ratelimit-reset-tokens"):
        raw = hdrs.get(key)
        if raw:
            try:
                return float(str(raw).rstrip("s"))
            except (TypeError, ValueError):
                pass
    m = _RETRY_AFTER_RE.search(msg)
    return float(m.group(1)) if m else 5.0


async def _llm_create(llm, *, stage: str = "?", **kwargs):
    """chat.completions.create with rate-limit backoff.

    Sleeps for the interval the provider specifies rather than retrying blind.
    Any non-rate-limit error is raised immediately — a bad key or a retired
    model will not fix itself by waiting.
    """
    for attempt in range(3):
        try:
            return llm.chat.completions.create(**kwargs)
        except Exception as e:
            wait = _retry_after_seconds(e)
            if wait is None or attempt == 2:
                raise
            if wait > _MAX_RATE_LIMIT_WAIT:
                print(f"[{stage}] rate limited, provider wants {wait:.0f}s "
                      f"(over the {_MAX_RATE_LIMIT_WAIT:.0f}s cap) — giving up",
                      flush=True)
                raise
            print(f"[{stage}] rate limited — waiting {wait:.1f}s as the "
                  f"provider asked (attempt {attempt + 1}/3)", flush=True)
            await asyncio.sleep(wait + 1.0)
    raise RuntimeError("unreachable")

def _draft_explanation(base: str, ir_issues: list, compile_err: str,
                       dump_path: str | None) -> str:
    """Plain-language account of what the tool is unsure about.

    Built from the IR checks and the compiler output rather than another LLM
    call — the findings are already known precisely, and a model asked to
    describe them could only add noise (and consume rate-limit budget).
    """
    lines = [base.strip() or "I built a draft of this circuit.", ""]
    lines.append("**This draft does not compile yet, so I have not enabled "
                 "RTL export.** The blocks are on your canvas so you can see "
                 "the structure and fix the problems below.")

    widths, drivers, floating, others = [], [], [], []
    for issue in ir_issues or []:
        t = str(issue)
        (widths if "WIDTH MISMATCH" in t else
         drivers if "MULTIPLE DRIVERS" in t else
         floating if "DISCONNECTED" in t else others).append(t)

    if widths:
        lines += ["", "**Widths I'm unsure about** — these connections carry a "
                      "different number of bits at each end. Usually one block's "
                      "width parameter is wrong, or the wrong output handle was "
                      "wired:"]
        lines += [f"  - {w.split(':', 1)[-1].strip()}" for w in widths[:6]]
    if drivers:
        lines += ["", "**Inputs driven from two places** — pick one source and "
                      "delete the other edge. A pin can only have one driver:"]
        lines += [f"  - {d.split(':', 1)[-1].strip()}" for d in drivers[:6]]
    if floating:
        lines += ["", "**Outputs nothing reads** — either wire them onward or "
                      "remove the block:"]
        lines += [f"  - {f.split(':', 1)[-1].strip()}" for f in floating[:6]]
    if others:
        lines += ["", "**Other issues:**"]
        lines += [f"  - {o}" for o in others[:4]]

    errs = [l.strip() for l in str(compile_err).splitlines() if l.strip()][:4]
    if errs:
        lines += ["", "**The Verilog compiler reported:**"]
        lines += [f"  - {e}" for e in errs]

    lines += ["", "Fix these on the canvas and press **DRC Test**, then "
                  "generate RTL again."]
    if dump_path:
        lines += ["", f"_The non-compiling Verilog was saved to {dump_path} "
                      f"for inspection._"]
    return "\n".join(lines)

# ── Stage V — behavioural equivalence ───────────────────────────────────────

_STAGE_V_SYSTEM = (
    "You write behavioural Verilog-2001 reference models.\n\n"
    "Given a circuit description and an exact port list, output ONE module\n"
    "named ref_model implementing the description directly with always/assign\n"
    "blocks. Do NOT instantiate anything. Do NOT add or rename ports.\n\n"
    "Output ONLY Verilog source. No markdown fences, no commentary."
)


def _ports_from_result(result: dict) -> tuple[list, list, bool, str | None]:
    """Port lists for co-simulation, taken from the emitted top module.

    Reading the real port list (rather than the hierarchy's intent) guarantees
    the reference model is built against exactly what the design exposes.
    """
    ins, outs, has_clk, rst = [], [], False, None
    for p in result.get("ports", []) or []:
        name = str(p.get("name", "")).strip()
        if not name:
            continue
        try:
            w = int(str(p.get("width", "1")).strip())
        except (TypeError, ValueError):
            w = 1                    # parameterised width — treat as 1 for stimulus
        low = name.lower()
        if low in ("clk", "clock"):
            has_clk = True
            continue
        if low in ("rst", "reset", "rst_n", "resetn"):
            rst = name
            continue
        (ins if p.get("dir") == "input" else outs).append(
            {"name": name, "width": max(1, w)})
    return ins, outs, has_clk, rst


async def _stage_v_equivalence(prompt: str, result: dict, llm, model) -> dict:
    """Check the design against a reference derived from the PROMPT.

    Every other check in the pipeline derives its expectations from the design
    itself, so a design that is internally consistent but is the wrong circuit
    passes them all. This is the only check with an independent source of
    truth, which is exactly why it can catch a peak detector that compares for
    equality instead of magnitude.
    """
    if not _cosim.iverilog_available():
        return {"status": "skipped", "reason": "iverilog not on PATH"}
    vf = result.get("verilog_files") or {}
    if "top.v" not in vf:
        return {"status": "skipped", "reason": "no top.v"}

    ins, outs, has_clk, rst = _cosim.ports_from_verilog(vf["top.v"])
    if not ins or not outs:
        return {"status": "skipped", "reason": "no comparable ports"}

    decls = []
    if has_clk:
        decls.append("input clk")
    if rst:
        decls.append(f"input {rst}")
    for p in ins:
        decls.append(f"input [{p['width']-1}:0] {p['name']}"
                     if p["width"] > 1 else f"input {p['name']}")
    for p in outs:
        decls.append(f"output reg [{p['width']-1}:0] {p['name']}"
                     if p["width"] > 1 else f"output reg {p['name']}")

    user = (f"Circuit description:\n{prompt}\n\n"
            f"Implement exactly this module header:\n\n"
            f"module ref_model(\n    " + ",\n    ".join(decls) + "\n);\n\n"
            + (f"Reset is {rst}, active high, synchronous.\n" if rst else "")
            + "Write the behaviour the description asks for.")

    try:
        resp = await _llm_create(
            llm, stage="RTL_BRAIN SV", model=model,
            messages=[{"role": "system", "content": _STAGE_V_SYSTEM},
                      {"role": "user", "content": user}],
            temperature=0.0, max_tokens=1500)
        src = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return {"status": "skipped", "reason": f"reference model call failed: {e}"}

    src = re.sub(r"^```[a-zA-Z]*\n?|```$", "", src, flags=re.M).strip()
    if "module ref_model" not in src:
        return {"status": "skipped", "reason": "reference model malformed"}

    verdict = _cosim.compare(vf, src, ins, outs,
                             has_clk=has_clk, reset_name=rst)
    verdict["reference_source"] = src
    return verdict

async def _rtl_brain_stage0(prompt: str, width_hint: str, llm=None, model=None) -> tuple:
    """
    Stage 0 — Generic decomposition.
    LLM outputs generic block names from closed GENERIC_VOCABULARY.
    Returns (concepts_list, None) on success.
    Returns (None, clarification_str) when LLM needs more info.
    Returns (None, None) on hard failure.
    """
    if llm is None:
        if _llm_client is None:
            raise HTTPException(status_code=403, detail={"code": "byok_required", "message": "No API key set. Please enter your API key in Settings."})
        llm = _llm_client
    if model is None: model = _LLM_MODEL
    vocab    = _build_stage0_vocabulary()
    user_msg = (
        f"Circuit to build: {prompt}\n"
        f"Default data width: {width_hint}-bit\n\n"
        f"{vocab}\n\n"
        f"{constraints_prompt(prompt)}\n\n"
        "Decompose this circuit into generic functional blocks.\n"
        "Use ONLY generic_type values from the vocabulary above.\n"
        "For each FSM/control/sequencing block, include fsm_states and fsm_outputs.\n"
        "COMPARISONS: 'comparator' defaults to EQUALITY (==). If the circuit\n"
        "needs a magnitude comparison — maximum, minimum, larger, smaller,\n"
        "exceeds, above, below, at least — you MUST add a \"compare_op\" field\n"
        "to that block with one of: eq, neq, gt, lt, gte, lte. A peak detector\n"
        "needs compare_op=gt; a floor detector needs lt.\n"
        "Output the JSON now:"
    )
    try:
        resp = await _llm_create(llm, stage="RTL_BRAIN S0",
            model=model,
            messages=[
                {"role": "system", "content": _RTL_BRAIN_STAGE0_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=3000,   # Stage 0 — reasoning models need headroom
        )
        raw  = resp.choices[0].message.content.strip()
        data = _rtl_brain_extract_json(raw)
        if not data:
            # A response that ends mid-token was cut off by max_tokens, not
            # malformed by the model. Saying "parse failed" sends you looking
            # at the prompt when the fix is the token budget.
            _fin = getattr(resp.choices[0], "finish_reason", None)
            if _fin == "length":
                print("[RTL_BRAIN S0] Response TRUNCATED (hit max_tokens) — "
                      "raise the Stage 0 budget", flush=True)
                _set_config_error(
                    "The model's reply was cut off before it finished. The "
                    "token budget for this stage is too small for the "
                    "selected model.")
            else:
                print("[RTL_BRAIN S0] JSON parse failed", flush=True)
            print(f"[RTL_BRAIN S0] Raw: {raw[:300]}", flush=True)
            return None, None

        if data.get("clarification_needed"):
            questions = data.get("questions", ["Could you provide more details?"])
            clarification = (
                "I need a bit more information to build this circuit:\n\n"
                + "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
            )
            print(f"[RTL_BRAIN S0] Clarification needed: {questions}", flush=True)
            return None, clarification

        concepts = data.get("concepts", [])
        if not concepts:
            print("[RTL_BRAIN S0] Empty concepts list", flush=True)
            return None, None

        print(f"[RTL_BRAIN S0] Decomposed into {len(concepts)} generic blocks:", flush=True)
        for c in concepts:
            print(f"  {c.get('suggested_id')} = {c.get('generic_type')}", flush=True)
        return concepts, None

    except Exception as e:
        global _stage0_config_error
        _n, _m = type(e).__name__, str(e)
        if "Authentication" in _n or "invalid_api_key" in _m or "401" in _m:
            _stage0_config_error = ("The provider rejected the API key (401). "
                "The key does not match the selected provider's endpoint.")
        elif "NotFound" in _n or "model_not_found" in _m or "does not exist" in _m:
            _stage0_config_error = ("The provider does not recognise the "
                "selected model. Hosted providers retire model IDs.")
        elif "429" in _m or "rate" in _m.lower():
            _stage0_config_error = ("The provider refused the request "
                "(rate limit or quota exhausted).")
        _tb.print_exc()
        return None, None


def _concepts_to_stage1_constraint(mapped_concepts: list) -> str:
    """
    Build a hard constraint block for Stage 1 from Python-mapped concepts.
    Stage 1 receives fixed primitives with exact handle names — no invention.

    ROOT CAUSE FIX: When an FSM exists, control handles on datapath blocks
    (wr_en, rd_en, en, load on FIFO/counter/shiftreg) are stripped from
    Stage 1's view entirely. Stage 1 cannot wire what it cannot see.
    These handles are owned by the FSM and wired deterministically by
    _extract_control_requirements + Stage 3 + _autowire_control_outputs.
    """

    _has_fsm = any(c.get("pattern") == "fsm" for c in mapped_concepts)

    _FSM_OWNED = {"wr_en", "rd_en", "en", "load"}
    _FSM_CONTROLLED_PATTERNS = {"macro_fifo", "macro_cfgcounter", "macro_shiftreg", "reg"}

    lines = [
        "PRIMITIVES LOCKED BY PYTHON MAPPER — do NOT change pattern or handles:",
        "Your ONLY job: define connections, parameters, top-level I/O.",
        "Handle names are fixed — copy EXACTLY from the handles field.",
        "",
    ]
    for c in mapped_concepts:
        op_str = f", comb_op='{c['comb_op']}'" if c.get("comb_op") else ""

        inputs = list(c['handles']['inputs'])
        if _has_fsm and c.get("pattern") in _FSM_CONTROLLED_PATTERNS:
            stripped = [h for h in inputs if h in _FSM_OWNED]
            inputs   = [h for h in inputs if h not in _FSM_OWNED]
            if stripped:
                print(f"[S1_CONSTRAINT] Stripped FSM-owned handles from {c['id']}: {stripped}", flush=True)

        lines.append(
            f"  id='{c['id']}' pattern='{c['pattern']}'{op_str}\n"
            f"    role: {c['role']}\n"
            f"    handles: inputs={inputs} outputs={c['handles']['outputs']}\n"
            f"    width: {c.get('width_hint','8')}\n"
            f"    connection_hints: {c.get('connection_hints','')}\n"
            f"    mapper_notes: {c.get('mapper_notes','')}"
        )
        if c.get("fsm_states"):
            lines.append(f"    fsm_states: {c['fsm_states']}")
            lines.append(f"    fsm_outputs: {c['fsm_outputs']}")
    return "\n".join(lines)


async def _rtl_brain_stage1(
    prompt: str, width_hint: str, mapped_concepts: list, llm=None, model=None,
    temperature: float = 0.0
) -> dict | None:
    """
    Stage 1 — Wiring + parameters only.
    Receives fixed primitives from Python mapper with handles already stamped.
    LLM only decides connections, parameters, and top-level I/O.
    Never invents handle names.
    """
    constraint = _concepts_to_stage1_constraint(mapped_concepts)
    handle_summary = "\n".join(
        f"  {c['id']} ({c['pattern']}): "
        f"inputs={c['handles']['inputs']} outputs={c['handles']['outputs']}"
        for c in mapped_concepts
    )

    user_msg = (
        f"Circuit: {prompt}\n"
        f"Data width: {width_hint}-bit\n\n"
        f"{constraint}\n\n"
        f"HANDLE REFERENCE (copy exactly):\n{handle_summary}\n\n"
        "Define connections, parameters, and top-level I/O.\n"
        "Use ONLY the handle names shown above — no other names.\n"
        "Output the JSON now:"
    )
    try:
        if llm is None:
            if _llm_client is None:
                raise HTTPException(status_code=403, detail={"code": "byok_required", "message": "No API key set. Please enter your API key in Settings."})
            llm = _llm_client
        if model is None: model = _LLM_MODEL
        resp = await _llm_create(llm, stage="RTL_BRAIN S1",
            model=model,
            messages=[
                {"role": "system", "content": _RTL_BRAIN_STAGE1_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            # A retry at temperature 0 returns the identical answer, so
            # feeding the errors back changes nothing. The caller raises
            # this on retry to let the model explore a different wiring.
            temperature=temperature,
            max_tokens=4000,   # Stage 1 — providers reserve this against
                               # the TPM budget, so keep it tight
        )
        raw  = resp.choices[0].message.content.strip()
        data = _rtl_brain_extract_json(raw)
        if not data:
            print("[RTL_BRAIN S1] JSON parse failed", flush=True)
            print(f"[RTL_BRAIN S1] Raw: {raw[:300]}", flush=True)
            return None
        print(
            f"[RTL_BRAIN S1] {len(data.get('connections',[]))} connections, "
            f"{len(data.get('top_level_inputs',[]))} inputs, "
            f"{len(data.get('top_level_outputs',[]))} outputs",
            flush=True
        )
        return data
    except Exception:
        _tb.print_exc()
        return None


_COMB_1BIT_OPS = set(_pc.COMB_PREDICATE_OPS)


def _rtl_brain_fix_hierarchy(hierarchy: dict, concepts: list = None) -> dict:
    """
    Post-processor applied after Stage 1 LLM output.
    Overwrites handle names and widths using deterministic lookup tables.
    Also stamps comb_op from Stage 0 onto each comb sub-circuit.
    """
    concept_map = {c.get("suggested_id", ""): c for c in (concepts or [])}

    for sc in hierarchy.get("sub_circuits", []):
        pattern = sc.get("pattern", "")
        sc_id   = sc.get("id", "")
        rules   = _PATTERN_HANDLE_RULES.get(pattern, {})

        comb_op = None
        if pattern == "comb":
            comb_op = (
                concept_map.get(sc_id, {}).get("comb_op")
                or sc.get("data", {}).get("comb_op")
                or sc.get("comb_op")
                or "eq"
            )
            sc.setdefault("data", {})["comb_op"] = comb_op
            sc["comb_op"] = comb_op


        for imp in sc.get("imports", []):
            h = imp.get("handle", "")
            fixed_h = rules.get("input_handles", {}).get(h)
            if fixed_h:
                print(f"[RTL_BRAIN FIX] {sc_id}: import '{h}' -> '{fixed_h}'", flush=True)
                imp["handle"] = h = fixed_h
            known_w = rules.get("input_widths", {}).get(h)
            if known_w is not None:
                imp["width"] = known_w

        for exp in sc.get("exports", []):
            h = exp.get("handle", "")
            fixed_h = rules.get("output_handles", {}).get(h)
            if fixed_h:
                print(f"[RTL_BRAIN FIX] {sc_id}: export '{h}' -> '{fixed_h}'", flush=True)
                exp["handle"] = h = fixed_h
            known_w = rules.get("output_widths", {}).get(h)
            if known_w is not None:
                exp["width"] = known_w

        if pattern == "comb" and comb_op in _COMB_1BIT_OPS:
            for exp in sc.get("exports", []):
                if exp.get("handle") == "out" and exp.get("width") != "1":
                    print(f"[RTL_BRAIN FIX] {sc_id}: comb({comb_op}) output width -> '1'", flush=True)
                    exp["width"] = "1"

    print("[RTL_BRAIN FIX] Post-processing complete", flush=True)
    return hierarchy


def _rtl_brain_assemble(
    mapped_concepts: list,
    stage1: dict,
) -> dict:
    """
    Python Assembler — converts Stage 1 wiring output + mapped_concepts
    into the full hierarchy dict that _run_hierarchical_v2_from_hierarchy expects.
    
    No LLM calls — pure deterministic Python.
    Derives sub_circuits from mapped_concepts.
    Wires connections from Stage 1.
    Stamps handle names from Python mapper (never from LLM).
    Derives top-level I/O from Stage 1 declarations.
    """
    connections      = stage1.get("connections", [])
    parameters_map   = stage1.get("parameters", {})
    top_level_inputs = stage1.get("top_level_inputs", [])
    top_level_outputs= stage1.get("top_level_outputs", [])


    width_conflicts: list[dict] = []

    sub_circuits = []
    for c in mapped_concepts:
        sc_id   = c["id"]
        pattern = c["pattern"]
        handles = c["handles"]
        params  = parameters_map.get(sc_id, {})

        _IMPLICIT_PORTS = {"clk", "rst", "clock", "reset", "rst_n", "reset_n"}
        imports = []
        for conn in connections:
            if conn.get("dst_id") == sc_id:
                src_id     = conn.get("src_id", "external")
                src_handle = conn.get("src_handle", "out")
                dst_handle = conn["dst_handle"]

                if dst_handle in _IMPLICIT_PORTS:
                    print(f"[ASSEMBLER] REJECTED: {conn.get('src_id','?')}[{conn.get('src_handle','?')}] → {sc_id}[{dst_handle}] — implicit port, not a wiring target", flush=True)
                    continue

                if pattern == "fsm":
                    signal_name = f"{src_id}_{src_handle}"
                    if signal_name.startswith("<") or src_handle.startswith("<"):
                        print(f"[ASSEMBLER] Error2: stripped placeholder FSM import {signal_name}", flush=True)
                        continue
                else:
                    signal_name = dst_handle


                dst_handle = _pc.canonical(dst_handle)
                src_handle = _pc.canonical(src_handle)

                src_concept = next((mc for mc in mapped_concepts if mc["id"] == src_id), None)
                src_w = dst_w = None

                if src_concept:
                    try:
                        src_w = _pc.resolve_width(
                            src_concept["pattern"], src_handle,
                            direction="outputs",
                            data_width=src_concept.get("data_width", 8),
                            comb_op=src_concept.get("comb_op"),
                            addr_width=src_concept.get("addr_width", 6),
                            sr_mode=src_concept.get("sr_mode"))
                    except KeyError:
                        print(f"[ASSEMBLER] {src_id} has no output handle "
                              f"'{src_handle}' — falling back to sink width",
                              flush=True)

                try:
                    dst_w = _pc.resolve_width(
                        pattern, dst_handle, direction="inputs",
                        data_width=c.get("data_width", 8),
                        comb_op=c.get("comb_op"),
                        addr_width=c.get("addr_width", 6),
                        sr_mode=c.get("sr_mode"))
                except KeyError:
                    print(f"[ASSEMBLER] REJECTED: {src_id}[{src_handle}] → "
                          f"{sc_id}[{dst_handle}] — '{dst_handle}' is not a "
                          f"declared input of {pattern}", flush=True)
                    continue

                if src_w is not None and dst_w is not None and src_w != dst_w:

                    width_conflicts.append({
                        "src": src_id, "src_handle": src_handle, "src_width": src_w,
                        "dst": sc_id,  "dst_handle": dst_handle, "dst_width": dst_w,
                    })
                    print(f"[ASSEMBLER] WIDTH CONFLICT {src_id}.{src_handle}"
                          f"({src_w}) → {sc_id}.{dst_handle}({dst_w})", flush=True)

                if dst_w is not None:
                    conn_width = str(dst_w)
                elif src_w is not None:
                    conn_width = str(src_w)
                else:
                    conn_width = str(conn.get("width", "1"))

                imports.append({
                    "signal":  signal_name,
                    "handle":  dst_handle,
                    "width":   conn_width,
                    "from":    src_id,
                })

        _has_fsm_in_circuit = any(
            mc.get("pattern") == "fsm" for mc in mapped_concepts
        )
        _fsm_owned_handles = {"wr_en", "rd_en", "en", "load"}
        for tli in top_level_inputs:
            if tli.get("dst_id") == sc_id:
                tli_handle = tli.get("dst_handle", tli["name"])
                # Strip control handles when FSM is present
                if _has_fsm_in_circuit and tli_handle in _fsm_owned_handles:
                    print(f"[ASSEMBLER] N1: stripped TLI {tli['name']} → {sc_id}[{tli_handle}] — FSM owns this handle", flush=True)
                    continue
                _data_handles = {"in0", "in1", "din", "d", "data_in"}
                tli_width = tli.get("width", "8" if tli_handle in _data_handles else "1")
                imports.append({
                    "signal":  tli_handle,
                    "handle":  tli_handle,
                    "width":   tli_width,
                    "from":    "external",
                })


        _HANDLE_NORMALIZE = {
            "macro_fifo":        {"out": "dout"},
            "macro_cfgcounter":  {"out": "tc", "terminal_count": "tc",
                                  "enable": "en", "load_value": "load_val"},
            "macro_shiftreg":    {"out": "q", "output": "q"},
        }
        for conn in connections:
            if conn.get("src_id") == sc_id:
                norm = _HANDLE_NORMALIZE.get(pattern, {})
                if conn.get("src_handle") in norm:
                    old_h = conn["src_handle"]
                    conn["src_handle"] = norm[old_h]
                    print(f"[ASSEMBLER] N2: normalized {sc_id}[{old_h}] → [{conn['src_handle']}]", flush=True)

        for tlo in top_level_outputs:
            if tlo.get("src_id") == sc_id:
                norm = _HANDLE_NORMALIZE.get(pattern, {})
                if tlo.get("src_handle") in norm:
                    old_h = tlo["src_handle"]
                    tlo["src_handle"] = norm[old_h]
                    print(f"[ASSEMBLER] N2: normalized TLO {sc_id}[{old_h}] → [{tlo['src_handle']}]", flush=True)
        exports = []
        seen_handles = set()
        for conn in connections:
            if conn.get("src_id") == sc_id:
                h = conn["src_handle"]
                if h not in seen_handles:
                    exports.append({
                        "signal": h,
                        "handle": h,
                        "width":  conn.get("width", "1"),
                    })
                    seen_handles.add(h)

        for tlo in top_level_outputs:
            if tlo.get("src_id") == sc_id:
                h = tlo.get("src_handle", tlo["name"])

                if h in ("<fsm_output_signals>", "<condition_signals>", "") and pattern == "fsm":
                    fsm_outs = c.get("fsm_outputs", [])
                    h = fsm_outs[0] if fsm_outs else tlo["name"]
                    print(f"[ASSEMBLER] FSM {sc_id}: placeholder handle → '{h}'", flush=True)
                if h not in seen_handles:
                    exports.append({
                        "signal": h,
                        "handle": h,
                        "width":  tlo.get("width", "1"),
                    })
                    seen_handles.add(h)

        sc = {
            "id":          sc_id,
            "name":        sc_id,
            "pattern":     pattern,
            "role":        c.get("role", ""),
            "imports":     imports,
            "exports":     exports,
            "data":        params,
            "position":    {"x": 100 + mapped_concepts.index(c) * 400, "y": 200},
        }


        if pattern == "comb" and c.get("comb_op"):
            sc["data"]["comb_op"] = c["comb_op"]
            sc["comb_op"] = c["comb_op"]


        if pattern == "fsm":
            sc["fsm_states"]  = c.get("fsm_states", [])
            sc["fsm_outputs"] = c.get("fsm_outputs", [])

        sub_circuits.append(sc)
        print(
            f"[ASSEMBLER] {sc_id} ({pattern}): "
            f"{len(imports)} imports, {len(exports)} exports",
            flush=True
        )


    _all_handle_norms = {
        "macro_fifo":       {"out": "dout"},
        "macro_cfgcounter": {"out": "tc", "terminal_count": "tc",
                             "enable": "en", "load_value": "load_val"},
        "macro_shiftreg":   {"out": "q", "output": "q"},
    }
    _sc_pattern_map = {sc["id"]: sc["pattern"] for sc in sub_circuits}
    for tlo in top_level_outputs:
        src_id  = tlo.get("src_id", "")
        pat     = _sc_pattern_map.get(src_id, "")
        norm    = _all_handle_norms.get(pat, {})
        old_h   = tlo.get("src_handle", "")
        if old_h in norm:
            tlo["src_handle"] = norm[old_h]
            print(f"[ASSEMBLER] Error1: TLO {src_id}[{old_h}] → [{tlo['src_handle']}]", flush=True)

        if pat == "fsm" and tlo.get("src_handle","").startswith("<"):
            tlo["src_handle"] = ""

    hierarchy = {
        "description":      f"RTL Brain generated circuit",
        "parameters":       {},
        "sub_circuits":     sub_circuits,
        "signal_list":      [],
        "output_logic":     [],
        "top_level_inputs": [
            {"name": p["name"], "width": p.get("width","1"),
             "to": p.get("dst_id",""), "dst_handle": p.get("dst_handle","")}
            for p in top_level_inputs
        ],
        "top_level_outputs": [
            {"name": p["name"], "width": p.get("width","1"),
             "from": p.get("src_id",""), "src_signal": p.get("src_handle","")}
            for p in top_level_outputs
        ],
        "reset": {"signal": "rst", "polarity": "active_high", "type": "synchronous"},

        "width_conflicts": width_conflicts,
    }

    if width_conflicts:
        print(f"[ASSEMBLER] {len(width_conflicts)} width conflict(s) — "
              "hierarchy is NOT canvas-DRC-clean:", flush=True)
        for wc in width_conflicts:
            print(f"    {wc['src']}.{wc['src_handle']}({wc['src_width']}) -> "
                  f"{wc['dst']}.{wc['dst_handle']}({wc['dst_width']})", flush=True)

    for sc in sub_circuits:
        if sc["pattern"] == "fsm" and not sc["imports"]:
            print(f"[ASSEMBLER] WARNING: FSM '{sc['id']}' has no imports — "
                  "counter tc may be disconnected", flush=True)
        if sc["pattern"] == "macro_cfgcounter" and not sc["exports"]:
            print(f"[ASSEMBLER] WARNING: counter '{sc['id']}' has no exports — "
                  "tc not wired to FSM", flush=True)

    print(
        f"[ASSEMBLER] Hierarchy assembled: {len(sub_circuits)} sub-circuits, "
        f"{len(top_level_inputs)} inputs, {len(top_level_outputs)} outputs",
        flush=True
    )
    return hierarchy


def _rtl_brain_autowire_fsm(hierarchy: dict) -> dict:
    """
    Infer FSM→datapath control connections missing from Stage 1.

    For each FSM sub-circuit, look at its fsm_outputs. For each output
    signal not already wired (no connection from this FSM to a datapath block
    on that signal), check _FSM_AUTOWIRE_RULES and add the connection if a
    matching unconnected datapath block exists.

    Also adds the FSM output to the datapath block's imports if missing.
    """
    sub_circuits = hierarchy.get("sub_circuits", [])

    existing = set()
    for sc in sub_circuits:
        sc_id = sc["id"]
        for imp in sc.get("imports", []):
            existing.add((imp.get("from", ""), imp.get("handle", ""), sc_id, imp.get("handle", "")))

    added = 0
    for fsm_sc in sub_circuits:
        if fsm_sc.get("pattern") != "fsm":
            continue
        fsm_id = fsm_sc["id"]
        fsm_outputs = fsm_sc.get("fsm_outputs", [])

        for sig in fsm_outputs:
            sig_lower = sig.lower()

            already_exported = any(
                e.get("signal") == sig or e.get("handle") == sig
                for e in fsm_sc.get("exports", [])
                if any(
                    imp.get("from") == fsm_id
                    for sc2 in sub_circuits
                    for imp in sc2.get("imports", [])
                    if imp.get("signal") == f"{fsm_id}_{sig}"
                )
            )
            if already_exported:
                continue

            for sig_contains, tgt_pattern, tgt_handle in _FSM_AUTOWIRE_RULES:
                if sig_contains not in sig_lower:
                    continue


                for tgt_sc in sub_circuits:
                    if tgt_sc["id"] == fsm_id:
                        continue
                    if tgt_sc.get("pattern") != tgt_pattern:
                        continue

                    already_driven = any(
                        imp.get("handle") == tgt_handle
                        for imp in tgt_sc.get("imports", [])
                    )
                    if already_driven:
                        continue

                    signal_name = f"{fsm_id}_{sig}"
                    tgt_sc.setdefault("imports", []).append({
                        "signal":  signal_name,
                        "handle":  tgt_handle,
                        "width":   "1",
                        "from":    fsm_id,
                    })

                    if not any(e.get("handle") == sig for e in fsm_sc.get("exports", [])):
                        fsm_sc.setdefault("exports", []).append({
                            "signal": sig,
                            "handle": sig,
                            "width":  "1",
                        })
                    print(
                        f"[AUTOWIRE] {fsm_id}[{sig}] → {tgt_sc['id']}[{tgt_handle}]",
                        flush=True
                    )
                    added += 1
                    break  

    if added:
        print(f"[AUTOWIRE] Added {added} FSM→datapath connections", flush=True)
    else:
        print("[AUTOWIRE] No missing FSM→datapath connections found", flush=True)

    return hierarchy


async def _rtl_brain_stage2(hierarchy: dict, llm=None, model=None) -> dict:
    """
    Stage 2 — Connectivity extraction.
    LLM receives the fixed block graph from Stage 1 and fills in signal_list
    (comb ops, gated_by entries). Cannot invent new blocks.
    Returns {"signal_list": [...], "output_logic": [...]} or empty dicts on failure.
    """
    sc_summary = []
    for sc in hierarchy.get("sub_circuits", []):
        sc_summary.append({
            "id":      sc["id"],
            "pattern": sc["pattern"],
            "role":    sc["role"],
            "exports": [e["signal"] for e in sc.get("exports", [])],
            "imports": [
                {"signal": i["signal"], "from": i.get("from", "external")}
                for i in sc.get("imports", [])
            ],
        })


    fsm_state_ref = []
    for sc in hierarchy.get("sub_circuits", []):
        if sc.get("pattern") == "fsm":
            fsm_state_ref.append(
                f"  FSM '{sc['id']}' states: {sc.get('fsm_states', [])}"
            )
    fsm_states_hint = (
        "\nFSM STATE NAMES (use EXACTLY these in output_logic overrides):\n"
        + "\n".join(fsm_state_ref)
        if fsm_state_ref else ""
    )

    direct_wires = []
    for sc in hierarchy.get("sub_circuits", []):
        sc_id = sc["id"]
        for exp in sc.get("exports", []):
            wire_name = f"{sc_id}_{exp['handle']}"
            direct_wires.append(wire_name)
    for sc in hierarchy.get("sub_circuits", []):
        if sc.get("pattern") == "fsm":
            for imp in sc.get("imports", []):
                direct_wires.append(imp.get("signal", ""))
    direct_wires = [w for w in direct_wires if w]  

    user_msg = (
        f"Circuit: {hierarchy.get('description', '')}\n\n"
        f"Block graph (fixed — do not change):\n{json.dumps(sc_summary, indent=2)}\n\n"
        "Top-level inputs:  "
        f"{[p['name'] for p in hierarchy.get('top_level_inputs', [])]}\n"
        "Top-level outputs: "
        f"{[p['name'] for p in hierarchy.get('top_level_outputs', [])]}\n"
        f"{fsm_states_hint}\n\n"
        f"DIRECT WIRES ALREADY DECLARED — do NOT add signal_list entries for these:\n"
        f"  {direct_wires}\n"
        "These wires connect automatically. Adding them to signal_list causes redeclaration errors.\n\n"
        "Fill in signal_list ONLY for signals needing combinational transformation (not, gated_by).\n"
        "Direct wires need NO entry.\n"
        'If nothing needs transformation, return {"signal_list":[],"output_logic":[]}.\n'
        "Output the JSON now:"
    )
    if llm is None:
        if _llm_client is None:
            raise HTTPException(status_code=403, detail={"code": "byok_required", "message": "No API key set. Please enter your API key in Settings."})
        llm = _llm_client
    if model is None: model = _LLM_MODEL
    try:
        resp = await _llm_create(llm, stage="RTL_BRAIN S2",
            model=model,
            messages=[
                {"role": "system", "content": _RTL_BRAIN_STAGE2_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=4000,   # Stage 2 — signal list
        )
        raw  = resp.choices[0].message.content.strip()
        data = _rtl_brain_extract_json(raw)
        if not data:
            print("[RTL_BRAIN S2] JSON extraction failed — using empty signal_list", flush=True)
            return {"signal_list": [], "output_logic": []}
        print(f"[RTL_BRAIN S2] signal_list: {len(data.get('signal_list',[]))} entries, "
              f"output_logic: {len(data.get('output_logic',[]))} entries", flush=True)
        return data
    except Exception:
        _tb.print_exc()
        return {"signal_list": [], "output_logic": []}


def _extract_control_requirements(hierarchy: dict, fsm_id: str) -> list:
    """
    Scan non-FSM sub-circuits for undriven control handles.
    Returns requirements list for Stage 3 FSM synthesis.
    """
    requirements = []
    for sc in hierarchy.get("sub_circuits", []):
        sc_id   = sc["id"]
        pattern = sc.get("pattern", "")
        if pattern == "fsm":
            continue
        ctrl_handles = _DATAPATH_CONTROL_HANDLES.get(pattern, [])
        if not ctrl_handles:
            continue
        driven = {imp.get("handle") for imp in sc.get("imports", [])}
        for ch in ctrl_handles:
            if ch["handle"] not in driven:
                suggested = f"{sc_id}_{ch['signal']}"
                requirements.append({
                    "target_id":        sc_id,
                    "handle":           ch["handle"],
                    "suggested_signal": suggested,
                    "desc":             ch["desc"],
                    "pattern":          pattern,
                })
                driven.add(ch["handle"])
                print(
                    f"[CTRL_REQ] {sc_id}[{ch['handle']}] undriven → "
                    f"FSM {fsm_id} needs output '{suggested}'",
                    flush=True
                )
    return requirements


def _autowire_control_outputs(hierarchy: dict, fsm_id: str, fsm_table: dict) -> dict:
    """
    Wire FSM control outputs to datapath block inputs after Stage 3.
    Uses multi-tier matching. Also injects connections into hierarchy
    so the v2 cross-boundary builder can wire them in the emitter.
    """
    sub_circuits = hierarchy.get("sub_circuits", [])
    fsm_sc = next((sc for sc in sub_circuits if sc["id"] == fsm_id), None)
    if not fsm_sc:
        return hierarchy

    fsm_outputs = fsm_table.get("fsm_outputs", [])
    added = 0

    for sc in sub_circuits:
        if sc["id"] == fsm_id:
            continue
        pattern = sc.get("pattern", "")
        ctrl_handles = _DATAPATH_CONTROL_HANDLES.get(pattern, [])
        driven = {imp.get("handle") for imp in sc.get("imports", [])}

        for ch in ctrl_handles:
            if ch["handle"] in driven:
                continue
            suggested  = f"{sc['id']}_{ch['signal']}"
            sc_prefix  = sc["id"].split("_")[0]
            handle_kw  = ch["handle"].replace("_en", "").replace("_enable", "")
            match = None

            sorted_outputs = sorted(
                fsm_outputs,
                key=lambda s: (
                    0 if sc["id"] in s.lower() else
                    1 if sc["id"].split("_")[0] in s.lower() else
                    2
                )
            )
            for sig in sorted_outputs:
                sig_l = sig.lower()
                if sig == suggested:                                           
                    match = sig; break
                if sc["id"] in sig_l and ch["handle"] in sig_l:               
                    match = sig; break
                if sc["id"] in sig_l and handle_kw in sig_l:                  
                    match = sig; break
                if sc_prefix in sig_l and ch["handle"] in sig_l:              
                    match = sig; break
                if sc_prefix in sig_l and handle_kw in sig_l:                 
                    match = sig; break

            if match:
                wire_name = f"{fsm_id}_{match}"
                sc.setdefault("imports", []).append({
                    "signal": wire_name,
                    "handle": ch["handle"],
                    "width":  "1",
                    "from":   fsm_id,
                })

                if not any(e.get("handle") == match
                           for e in fsm_sc.get("exports", [])):
                    fsm_sc.setdefault("exports", []).append({
                        "signal": match,
                        "handle": match,
                        "width":  "1",
                    })

                hierarchy.setdefault("_ctrl_connections", []).append({
                    "src_id":     fsm_id,
                    "src_signal": match,
                    "dst_id":     sc["id"],
                    "dst_handle": ch["handle"],
                })
                print(
                    f"[CTRL_WIRE] {fsm_id}[{match}] → {sc['id']}[{ch['handle']}]",
                    flush=True
                )
                added += 1

    print(
        f"[CTRL_WIRE] Wired {added} control outputs" if added
        else "[CTRL_WIRE] No control outputs matched",
        flush=True
    )
    return hierarchy


async def _rtl_brain_stage3_fsm(sc_id: str, sc: dict,
                                 signal_list: list, llm=None, model=None) -> dict | None:
    """
    Stage 3 — FSM transition table extraction for one FSM sub-circuit.
    LLM receives fixed states, fixed output names, and the exact condition
    wire names from Stage 2's signal_list. Returns a transition table dict
    compatible with _FSM_TRANSITION_TABLES format, or None on failure.
    """
    fsm_states  = sc.get("fsm_states",  [])
    fsm_outputs = sc.get("fsm_outputs", [])


    condition_wires = []
    sig_names = {s["name"] for s in signal_list}
    for imp in sc.get("imports", []):
        sig = imp["signal"]
        condition_wires.append(sig)
        not_sig = f"not_{sig}"
        if not_sig in sig_names:
            condition_wires.append(not_sig)
    for s in signal_list:
        if sc_id in s.get("consumers", []) and s["name"] not in condition_wires:
            condition_wires.append(s["name"])
    condition_wires.append("1")

    ctrl_reqs = sc.get("_control_requirements", [])
    locked_ctrl_outputs = [r["suggested_signal"] for r in ctrl_reqs]
    all_outputs = list(dict.fromkeys(fsm_outputs + locked_ctrl_outputs))

    ctrl_hint = ""
    if locked_ctrl_outputs:
        ctrl_lines = [
            f"  {r['suggested_signal']} → {r['target_id']}[{r['handle']}]: {r['desc']}"
            for r in ctrl_reqs
        ]
        ctrl_hint = (
            "LOCKED CONTROL OUTPUTS — use these EXACT names, no substitutions:\n"
            + "\n".join(ctrl_lines) + "\n"
            "These names are generated by the Python assembler and MUST match exactly.\n"
            "Do NOT rename, shorten, or genericize them.\n\n"
        )

    user_msg = (
        f"FSM id: {sc_id}\n"
        f"Role: {sc.get('role', '')}\n\n"
        f"States (in sequence): {fsm_states}\n"
        f"Reset state: {fsm_states[0] if fsm_states else 'idle'}\n\n"
        f"COMPLETE OUTPUT LIST (use ALL of these, no additions, no removals):\n"
        f"  {all_outputs}\n\n"
        f"{ctrl_hint}"
        f"Available condition wires (use ONLY these):\n"
        f"  {condition_wires}\n\n"
        "Fill in the complete FSM transition table.\n"
        "fsm_outputs MUST be exactly the list above — copy it verbatim.\n"
        "Every state must declare ALL outputs in outputs_per_state.\n"
        "Every state must have at least one outgoing transition.\n"
        "Output the JSON now:"
    )
    try:
        if llm is None:
            if _llm_client is None:
                raise HTTPException(status_code=403, detail={"code": "byok_required", "message": "No API key set. Please enter your API key in Settings."})
            llm = _llm_client
        if model is None: model = _LLM_MODEL
        resp = await _llm_create(llm, stage="RTL_BRAIN S3",
            model=model,
            messages=[
                {"role": "system", "content": _RTL_BRAIN_STAGE3_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=4000,   # Stage 3 — FSM transition table
        )
        raw  = resp.choices[0].message.content.strip()
        data = _rtl_brain_extract_json(raw)
        if not data:
            print(f"[RTL_BRAIN S3] JSON extraction failed for {sc_id}", flush=True)
            return None
        print(f"[RTL_BRAIN S3] FSM '{sc_id}': {len(data.get('states',[]))} states, "
              f"{len(data.get('transitions',[]))} transitions", flush=True)
        return data
    except Exception:
        _tb.print_exc()
        return None


_RTL_BRAIN_VALID_PATTERNS = set(_PRIM_SPECS.keys()) | {"known_circuit"}


def _rtl_brain_validate(hierarchy: dict) -> list[str]:
    """
    Validate the assembled hierarchy before passing to the emitter.
    Returns a list of error strings. Empty list = valid.
    """
    errors = []

    if not hierarchy.get("sub_circuits"):
        errors.append("No sub_circuits in hierarchy")
        return errors

    for sc in hierarchy["sub_circuits"]:
        pattern = sc.get("pattern", "")
        sc_id   = sc.get("id", "?")

        if pattern not in _RTL_BRAIN_VALID_PATTERNS:
            errors.append(f"[{sc_id}] Unknown pattern '{pattern}' — not in PRIMITIVE_BLOCK_SPECS")

        if pattern == "fsm":
            if not sc.get("fsm_states"):
                errors.append(f"[{sc_id}] FSM missing fsm_states")
            if not sc.get("fsm_outputs"):
                errors.append(f"[{sc_id}] FSM missing fsm_outputs")

        if pattern == "known_circuit":
            key = sc.get("known_circuit_key", "")
            if key not in _KC_HIERARCHIES:
                errors.append(
                    f"[{sc_id}] known_circuit_key '{key}' not found in _KNOWN_HIERARCHIES"
                )

    if not hierarchy.get("top_level_outputs"):
        errors.append("No top_level_outputs defined")


    for wc in hierarchy.get("width_conflicts", []):
        if str(wc.get("dst_handle", "")).startswith("<") or \
           str(wc.get("src_handle", "")).startswith("<"):
            continue          # placeholder, not a real port
        errors.append(
            f"[{wc['dst']}] width conflict: {wc['src']}.{wc['src_handle']} is "
            f"{wc['src_width']}-bit but {wc['dst_handle']} expects "
            f"{wc['dst_width']}-bit")

    sc_ids = {sc.get("id") for sc in hierarchy.get("sub_circuits", [])}
    _has_fsm = any(sc.get("pattern") == "fsm"
                   for sc in hierarchy.get("sub_circuits", []))
    driven = {(sc.get("id"), imp.get("handle"))
              for sc in hierarchy.get("sub_circuits", [])
              for imp in sc.get("imports", [])}
    driven |= {(t.get("to"), t.get("dst_handle"))
               for t in hierarchy.get("top_level_inputs", [])}

    for sc in hierarchy.get("sub_circuits", []):
        pattern, sc_id = sc.get("pattern", ""), sc.get("id", "?")
        if pattern in ("fsm", "fsm_state"):
            continue
        data = sc.get("data", {})
        try:
            req = _pc.required_inputs(
                pattern, comb_op=sc.get("comb_op") or data.get("op"),
                sr_mode=data.get("srMode"),
                mux_size=int(str(data.get("muxSize", 2)) or 2))
        except Exception:
            req = []
        for handle in req:
            if (sc_id, handle) in driven:
                continue
            # Control handles are deliberately stripped from Stage 1's view
            # ("[S1_CONSTRAINT] Stripped FSM-owned handles") because an FSM
            # owns them, and _rtl_brain_autowire_fsm connects them afterwards.
            # Reporting them as undriven asks Stage 1 to wire handles it was
            # explicitly forbidden to wire — an instruction it cannot satisfy.
            # With an FSM present these are a warning, not a failure.
            if handle in _FSM_OWNED_HANDLES and _has_fsm:
                print(f"[VALIDATE] note: {sc_id}[{handle}] undriven — expected "
                      f"to come from an FSM output", flush=True)
                continue
            errors.append(f"[{sc_id}] required input '{handle}' is not driven")

        for imp in sc.get("imports", []):
            frm = imp.get("from", "external")
            if frm not in ("external", "", None) and frm not in sc_ids:
                errors.append(f"[{sc_id}] imports from unknown block '{frm}'")

    return errors


async def _run_rtl_brain(prompt: str, width_hint: str, current_user: str, llm=None, byok: bool = False, model=None) -> dict:
    """
    RTL Brain orchestrator — 4-stage pipeline for unknown circuits.

    Stage 0 — LLM: generic decomposition from closed vocabulary
    Python  — deterministic: maps generic → primitive + handles
    Stage 1 — LLM: wiring + parameters only (handles already fixed)
    Python  — deterministic: assembles hierarchy dict from Stage 1 output
    Stage 2 — LLM: signal_list (comb ops, gated_by)
    Stage 3 — LLM: FSM transition tables (one per FSM)
    Emitter — deterministic: proven v2 emission pipeline

    LLM never touches handle names. Python mapper enforces all handle correctness.
    Option A: replace fallback lines to cut old path entirely.
    """

    state.reset_request_state()
    global _stage0_config_error
    _stage0_config_error = None

    print(f"\n{'='*60}", flush=True)
    print(f"[RTL_BRAIN] REQUEST: {prompt}", flush=True)
    # Which endpoint and model are actually being called. Without this, a wrong
    # provider, a retired model ID and a bad key all look identical in the log.
    print(f"[RTL_BRAIN] Provider: {getattr(llm, 'base_url', '?')} | "
          f"model: {model or '(server default)'} | byok: {byok}", flush=True)
    print(f"[RTL_BRAIN] Width hint: {width_hint}-bit", flush=True)
    print(f"{'='*60}", flush=True)

    print("\n[RTL_BRAIN] Stage 0 — Generic decomposition...", flush=True)
    if llm is None:
        if _llm_client is None:
            raise HTTPException(status_code=403, detail={"code": "byok_required", "message": "No API key set. Please enter your API key in Settings."})
        llm = _llm_client
    if model is None: model = _LLM_MODEL
    raw_concepts, clarification = await _rtl_brain_stage0(prompt, width_hint, llm=llm, model=model)

    if not byok:
        try:
            print("[RTL_BRAIN] Credit deducted: Stage 0", flush=True)
        except Exception:
            pass


    if clarification:
        print(f"[RTL_BRAIN] Stage 0 requests clarification", flush=True)
        return {
            "explanation":          clarification,
            "nodes":                [],
            "edges":                [],
            "clarification_needed": True,
        }

    if not raw_concepts:
        print("[RTL_BRAIN] Stage 0 returned nothing — retrying once", flush=True)
        raw_concepts, clarification = await _rtl_brain_stage0(
            prompt, width_hint, llm=llm, model=model)
        if clarification:
            return {"explanation": clarification, "nodes": [], "edges": [],
                    "clarification_needed": True}
    if _stage0_config_error:
        raise _GenFail(
            stage="LLM configuration",
            reason=_stage0_config_error,
            suggestions=[
                "Open Settings (key icon) and check the provider, model and "
                "API key all belong together.",
                "A key issued by one provider will not authenticate against "
                "another provider's endpoint.",
            ])

    if not raw_concepts:
        raise _GenFail(
            stage="Stage 0 (decomposition)",
            reason="I couldn't break this request into blocks I can build.",
            suggestions=[
                "Describe the circuit block by block (what stores state, what "
                "compares, what counts).",
                "State the data width, clock rate and reset polarity.",
            ])


    print("\n[RTL_BRAIN] Python Mapper — generic → primitives...", flush=True)
    mapped_concepts, map_error = map_concepts_to_primitives(
        raw_concepts, design_width=width_hint)
    mapped_concepts = _apply_compare_ops(raw_concepts, mapped_concepts)

    if map_error:
        print(f"[RTL_BRAIN] Mapper needs clarification: {map_error[:80]}", flush=True)
        return {
            "explanation":          map_error,
            "nodes":                [],
            "edges":                [],
            "clarification_needed": True,
        }

    print(f"[RTL_BRAIN] Mapped {len(mapped_concepts)} primitives:", flush=True)
    for mc in mapped_concepts:
        op = f" comb_op={mc['comb_op']}" if mc.get("comb_op") else ""
        print(f"  {mc['id']}: {mc['pattern']}{op} handles={mc['handles']}", flush=True)

    print("\n[RTL_BRAIN] Stage 1 — Wiring + parameters...", flush=True)
    stage1_out = await _rtl_brain_stage1(prompt, width_hint, mapped_concepts, llm=llm, model=model)

    if not byok:
        try:
            print("[RTL_BRAIN] Credit deducted: Stage 1", flush=True)
        except Exception:
            pass

    if not stage1_out:
        print("[RTL_BRAIN] Stage 1 returned nothing — retrying once", flush=True)
        stage1_out = await _rtl_brain_stage1(
            prompt, width_hint, mapped_concepts, llm=llm, model=model)
    if not stage1_out:
        raise _GenFail(
            stage="Stage 1 (wiring)",
            reason="I decomposed the design but couldn't work out how to "
                   "connect the blocks.",
            details=[f"Blocks identified: "
                     f"{', '.join(c['id'] for c in mapped_concepts)}"],
            suggestions=["Describe the data flow between these blocks — what "
                         "feeds what, and what the top-level ports are."])


    print("\n[RTL_BRAIN] Python Assembler — building hierarchy dict...", flush=True)
    hierarchy = _rtl_brain_assemble(mapped_concepts, stage1_out)


    hierarchy = _rtl_brain_autowire_fsm(hierarchy)


    errors = _rtl_brain_validate(hierarchy)
    if errors:
        # Route the retry to the stage that OWNS the failure.
        #
        # 'FSM missing fsm_states' is a Stage 0 defect: the state list is part
        # of the decomposition, not the wiring. Retrying Stage 1 for it — which
        # is all this used to do — could never fix the problem, so the retry
        # burned a call and the generation failed anyway. Wiring errors do
        # belong to Stage 1.
        s0_errors = [e for e in errors
                     if "missing fsm_states" in e or "missing fsm_outputs" in e]
        s1_errors = [e for e in errors if e not in s0_errors]

        if s0_errors:
            print(f"[RTL_BRAIN] Validation failed on DECOMPOSITION: "
                  f"{s0_errors} — retrying Stage 0", flush=True)
            fix_prompt = (
                f"{prompt}\n\nYour previous decomposition was incomplete:\n"
                + "\n".join(f"  - {e}" for e in s0_errors)
                + "\n\nEvery state_machine / handshake_controller / "
                  "protocol_controller / arbiter / sequencer block MUST include "
                  "a non-empty fsm_states list and an fsm_outputs list.")
            retry_concepts, _clar = await _rtl_brain_stage0(
                fix_prompt, width_hint, llm=llm, model=model)
            if retry_concepts:
                remapped, remap_err = map_concepts_to_primitives(
                    retry_concepts, design_width=width_hint)
                if remapped and not remap_err:
                    mapped_concepts = remapped
                    stage1_out = await _rtl_brain_stage1(
                        prompt, width_hint, mapped_concepts,
                        llm=llm, model=model)
                    if stage1_out:
                        hierarchy = _rtl_brain_autowire_fsm(
                            _rtl_brain_assemble(mapped_concepts, stage1_out))
                        errors = _rtl_brain_validate(hierarchy)
        elif s1_errors:
            print(f"[RTL_BRAIN] Validation failed on WIRING: {s1_errors} — "
                  f"retrying Stage 1 with the errors fed back", flush=True)
            retry_prompt = (
                f"{prompt}\n\nYour previous wiring produced these errors — fix "
                f"them. Every listed input MUST end up driven, either by "
                f"another block's output or by a top-level input port:\n"
                + "\n".join(f"  - {e}" for e in s1_errors))
            stage1_out = await _rtl_brain_stage1(
                retry_prompt, width_hint, mapped_concepts, llm=llm, model=model,
                temperature=0.4)
            if stage1_out:
                hierarchy = _rtl_brain_autowire_fsm(
                    _rtl_brain_assemble(mapped_concepts, stage1_out))
                errors = _rtl_brain_validate(hierarchy)

            # If the same errors survive, Stage 1 is not the problem: the
            # decomposition is missing a block. "required input 'd' is not
            # driven" on a peak detector means Stage 0 produced a comparator
            # and a register but no mux — there is nothing that COULD drive it,
            # so no amount of rewiring will help. Escalate to Stage 0.
            if errors and set(errors) == set(s1_errors):
                print(f"[RTL_BRAIN] Same errors after rewiring — the "
                      f"decomposition is likely incomplete. Retrying Stage 0.",
                      flush=True)
                fix_prompt = (
                    f"{prompt}\n\nA previous decomposition could not be wired "
                    f"up. These inputs had nothing available to drive them:\n"
                    + "\n".join(f"  - {e}" for e in errors)
                    + "\n\nInclude every block the datapath needs. A value that "
                      "is conditionally updated needs a multiplexer to choose "
                      "between the old and new value. A block's data input must "
                      "come from somewhere.")
                more, _clar2 = await _rtl_brain_stage0(
                    fix_prompt, width_hint, llm=llm, model=model)
                if more:
                    remapped, rerr = map_concepts_to_primitives(
                        more, design_width=width_hint)
                    remapped = _apply_compare_ops(more, remapped)
                    if remapped and not rerr:
                        mapped_concepts = remapped
                        stage1_out = await _rtl_brain_stage1(
                            prompt, width_hint, mapped_concepts,
                            llm=llm, model=model)
                        if stage1_out:
                            hierarchy = _rtl_brain_autowire_fsm(
                                _rtl_brain_assemble(mapped_concepts, stage1_out))
                            errors = _rtl_brain_validate(hierarchy)

        if errors:
            # Log what survived the retry. Previously these only reached the
            # user's chat window, so the terminal showed the first round's
            # errors and nothing about why the retry did not help.
            print(f"[RTL_BRAIN] Validation STILL failing after retry: "
                  f"{errors}", flush=True)
    if errors:
        raise _GenFail(
            stage="hierarchy validation",
            reason="The assembled design didn't pass its structural checks.",
            details=errors,
            suggestions=["Add the missing detail the errors point at, or ask "
                         "for a simpler version first and extend it on canvas."])


    print("\n[RTL_BRAIN] Stage 2 — Connectivity extraction...", flush=True)
    s2 = await _rtl_brain_stage2(hierarchy, llm=llm, model=model)
    hierarchy["signal_list"]  = s2.get("signal_list",  [])
    hierarchy["output_logic"] = s2.get("output_logic", [])

    if not byok:
        try:
            print("[RTL_BRAIN] Credit deducted: Stage 2", flush=True)
        except Exception:
            pass

    print("\n[RTL_BRAIN] Stage 3 — FSM tables...", flush=True)
    _has_fsm = any(sc.get("pattern") == "fsm" for sc in hierarchy["sub_circuits"])
    if not _has_fsm:
        print("[RTL_BRAIN] No FSM sub-circuits — skipping Stage 3", flush=True)

    for sc in hierarchy["sub_circuits"]:
        if sc.get("pattern") != "fsm":
            continue
        sc_id = sc["id"]
        print(f"[RTL_BRAIN] Stage 3 — FSM: {sc_id}", flush=True)
        ctrl_reqs = _extract_control_requirements(hierarchy, sc_id)
        sc["_control_requirements"] = ctrl_reqs
        table = await _rtl_brain_stage3_fsm(
            sc_id, sc, hierarchy.get("signal_list", []), llm=llm, model=model
        )
        if not table:
            print(f"[RTL_BRAIN] Stage 3 failed for {sc_id} — retrying once", flush=True)
            table = await _rtl_brain_stage3_fsm(
                sc_id, sc, hierarchy.get("signal_list", []), llm=llm, model=model)
        if not table:
            raise _GenFail(
                stage=f"Stage 3 (FSM '{sc_id}')",
                reason="I couldn't derive a valid state transition table.",
                details=[f"States requested: {sc.get('fsm_states', [])}"],
                suggestions=[
                    "Describe the state machine explicitly: the states, and "
                    "what event moves it from each state to the next.",
                ])

        if not byok:
            try:
                print(f"[RTL_BRAIN] Credit deducted: Stage 3 FSM '{sc_id}'", flush=True)
            except Exception:
                pass


        _FSM_TRANSITION_TABLES[sc_id] = table
        print(f"[RTL_BRAIN] Registered FSM table for '{sc_id}'", flush=True)

        fsm_sc = next((s for s in hierarchy["sub_circuits"] if s["id"] == sc_id), None)
        if fsm_sc and table.get("fsm_outputs"):
            _valid_ctrl_patterns = set(_DATAPATH_CONTROL_HANDLES.keys())
            _valid_targets = {
                r["suggested_signal"]
                for r in sc.get("_control_requirements", [])
            }
            _user_visible = set(sc.get("fsm_outputs", []))
            _all_valid = _valid_targets | _user_visible
            raw_outputs = table["fsm_outputs"]
            filtered = [o for o in raw_outputs if o in _all_valid]

            stripped = set(raw_outputs) - set(filtered)
            if stripped:
                print(f"[RTL_BRAIN] P1: stripped phantom FSM outputs: {stripped}", flush=True)
                for state_vals in table.get("outputs_per_state", {}).values():
                    for phantom in stripped:
                        state_vals.pop(phantom, None)
            table["fsm_outputs"] = filtered
            fsm_sc["fsm_outputs"] = filtered
            print(f"[RTL_BRAIN] F1: synced fsm_outputs for '{sc_id}': {filtered}", flush=True)


        hierarchy = _autowire_control_outputs(hierarchy, sc_id, table)


        for cc in hierarchy.get("_ctrl_connections", []):
            dst_sc = next((s for s in hierarchy["sub_circuits"]
                           if s["id"] == cc["dst_id"]), None)
            if dst_sc:
                already = any(imp.get("handle") == cc["dst_handle"]
                              and imp.get("from") == cc["src_id"]
                              for imp in dst_sc.get("imports", []))
                if not already:
                    dst_sc.setdefault("imports", []).append({
                        "signal": f"{cc['src_id']}_{cc['src_signal']}",
                        "handle": cc["dst_handle"],
                        "width":  "1",
                        "from":   cc["src_id"],
                    })

    print("\n[RTL_BRAIN] All stages complete — passing to v2 emitter", flush=True)
    circuit_key = prompt.lower().strip()[:40].replace(" ", "_")

    result = await _run_hierarchical_v2_from_hierarchy(
        circuit_key, hierarchy, prompt, current_user
    )



    vf = result.get("verilog_files") or {}
    if not vf:
        raise _GenFail(
            stage="Verilog emission",
            reason="The design assembled but produced no Verilog.",
            details=result.get("ir_issues", []) or None,
            suggestions=["Try a simpler version of the request first."])

    ok, err = await _iverilog_compile_check(vf)
    if not ok:
        # Blocking the canvas is right — bad Verilog should not look like a
        # success. But discarding it leaves nobody able to debug the failure,
        # so write it out and quote the offending lines. The gate protects the
        # user; the dump serves whoever has to fix the emitter.
        dump_dir = BACKEND_DIR / "failed_generations"
        dump_note = ""
        try:
            dump_dir.mkdir(exist_ok=True)
            stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = dump_dir / f"{stamp}_{circuit_key[:40]}"
            run_dir.mkdir(exist_ok=True)
            for fname, text in vf.items():
                (run_dir / fname).write_text(text, encoding="utf-8")
            (run_dir / "_error.txt").write_text(
                f"prompt: {prompt}\n\niverilog:\n{err}\n", encoding="utf-8")
            dump_note = str(run_dir)
            print(f"[RTL_BRAIN] Non-compiling Verilog written to {run_dir}",
                  flush=True)
        except Exception as _e:
            print(f"[RTL_BRAIN] could not write failure dump: {_e}", flush=True)

        # Echo the lines iverilog objected to, so the log alone is often enough.
        try:
            import re as _re
            top = vf.get("top.v", "")
            lines = top.split("\n")
            for _m in _re.finditer(r"top\.v:(\d+):", str(err)):
                n = int(_m.group(1))
                lo, hi = max(0, n - 4), min(len(lines), n + 2)
                print(f"[RTL_BRAIN] --- top.v around line {n} ---", flush=True)
                for i in range(lo, hi):
                    mark = ">>" if i == n - 1 else "  "
                    print(f"[RTL_BRAIN] {mark} {i+1:4}| {lines[i]}", flush=True)
                break
        except Exception:
            pass

        # Return the design as a DRAFT rather than discarding it.
        #
        # Blocking the canvas entirely protected the user from trusting broken
        # output, but it also threw away nine correctly-placed blocks and left
        # nothing to fix. The middle ground: show the circuit, say plainly what
        # is wrong with it, and refuse to hand over RTL until it is fixed.
        #
        # The distinction that matters is that broken output must never look
        # finished. It is labelled, the defects are listed, and rtl_ready stays
        # false so nobody exports Verilog that does not compile.
        result["compile_failed"] = True
        result["rtl_ready"]      = False
        result.pop("verilog_files", None)
        result["failed_verilog_path"] = dump_note or None
        result["explanation"] = _draft_explanation(
            result.get("explanation", ""), result.get("ir_issues", []), err,
            dump_note)
        print("[RTL_BRAIN] Returning DRAFT circuit (does not compile) — "
              "canvas populated, RTL export disabled", flush=True)
        return result

    # ── Stage V: does it do what was asked? ────────────────────────────────
    if os.environ.get("RTL_BRAIN_EQUIV_CHECK", "1") != "0":
        try:
            eq = await _stage_v_equivalence(prompt, result, llm, model)
        except Exception as _e:
            eq = {"status": "skipped", "reason": f"{type(_e).__name__}: {_e}"}
        result["equivalence"] = {k: v for k, v in eq.items()
                                 if k != "reference_source"}
        print(f"[RTL_BRAIN SV] equivalence: {eq.get('status')} "
              f"{eq.get('reason', '')}", flush=True)
        if eq.get("status") == "mismatch":
            # Not an error: the reference may be the wrong one. The design goes
            # on canvas so the engineer can adjudicate, but RTL export is held
            # back because the tool cannot vouch for it.
            result["rtl_ready"] = False
            result["verilog_files"] = vf
            result["explanation"] = (
                (result.get("explanation", "") or "").strip()
                + "\n\n" + _cosim.describe(eq))
            for d in eq.get("divergences", [])[:3]:
                print(f"[RTL_BRAIN SV]   step {d['step']} in={d['inputs']} "
                      f"out={d['outputs']}", flush=True)

    if not result.get("ir_issues"):
        print(f"[RTL_BRAIN] iverilog clean — caching as '{circuit_key}'", flush=True)
        state.RUNTIME_CIRCUITS[circuit_key] = hierarchy
        state.RUNTIME_KEYWORDS[circuit_key] = [prompt.lower().strip()]

    return result


_PATTERN_HANDLE_RULES: dict = {
    "macro_cfgcounter": {
        "input_handles":  {"enable": "en", "cnt_en": "en", "load_value": "load_val"},
        "output_handles": {"out": "tc", "terminal_count": "tc"},
        "output_widths":  {"tc": "1", "count": "8"},
        "input_widths":   {"en": "1", "load": "1"},
    },
    "comb": {
        "input_handles":  {"in": "in0", "input": "in0", "a": "in0", "b": "in1"},
        "output_handles": {},
        "output_widths":  {},
        "input_widths":   {},
    },
    "macro_fifo": {
        "input_handles":  {},
        "output_handles": {},
        "output_widths":  {"full": "1", "empty": "1", "ae": "1"},
        "input_widths":   {"wr_en": "1", "rd_en": "1"},
    },
    "macro_shiftreg": {
        "input_handles":  {},
        "output_handles": {"out": "sout"},
        "output_widths":  {"sout": "1"},
        "input_widths":   {"en": "1", "load": "1"},
    },
    "macro_sync": {
        "input_handles":  {},
        "output_handles": {},
        "output_widths":  {"q": "1"},
        "input_widths":   {"d": "1"},
    },
    "fsm":        {"input_handles": {}, "output_handles": {}, "output_widths": {}, "input_widths": {}},
    "reg":        {"input_handles": {}, "output_handles": {}, "output_widths": {}, "input_widths": {}},
    "macro_penc": {"input_handles": {}, "output_handles": {}, "output_widths": {"valid": "1"}, "input_widths": {}},
    "macro_dpram":{"input_handles": {}, "output_handles": {}, "output_widths": {}, "input_widths": {"we_a": "1", "we_b": "1"}},
    "mux":        {"input_handles": {}, "output_handles": {}, "output_widths": {}, "input_widths": {"sel": "1"}},
}


_FSM_AUTOWIRE_RULES: list[tuple[str, str, str]] = [
    ("shift_en",      "macro_shiftreg",    "en"),
    ("shift_enable",  "macro_shiftreg",    "en"),
    ("load",          "macro_shiftreg",    "load"),
    ("load",          "macro_cfgcounter",  "load"),
    ("en",            "macro_cfgcounter",  "en"),
    ("enable",        "macro_cfgcounter",  "en"),
    ("cnt_en",        "macro_cfgcounter",  "en"),
    ("count_en",      "macro_cfgcounter",  "en"),
    ("rd_en",         "macro_fifo",        "rd_en"),
    ("wr_en",         "macro_fifo",        "wr_en"),
    ("fifo_en",       "macro_fifo",        "wr_en"),
    ("fifo_enable",   "macro_fifo",        "wr_en"),
    ("write_en",      "macro_fifo",        "wr_en"),
    ("sample_en",     "macro_fifo",        "wr_en"),
    ("record_en",     "macro_fifo",        "wr_en"),
    ("adc_enable",    "macro_fifo",        "wr_en"),
    ("adc_en",        "macro_fifo",        "wr_en"),
    ("capture_en",    "macro_fifo",        "wr_en"),
    ("store_en",      "macro_fifo",        "wr_en"),
    ("data_en",       "macro_fifo",        "wr_en"),
    ("add_enable",    "comb",              "in1"),
    ("shift_en",      "macro_cfgcounter",  "en"),  
]


_DATAPATH_CONTROL_HANDLES: dict = {
    "macro_cfgcounter": [
        {"handle": "en",    "signal": "count_enable",  "desc": "count enable — 1 to count"},
        {"handle": "load",  "signal": "counter_load",  "desc": "synchronous counter load"},
    ],
    "macro_fifo": [
        {"handle": "wr_en", "signal": "fifo_write_en", "desc": "FIFO write enable"},
        {"handle": "rd_en", "signal": "fifo_read_en",  "desc": "FIFO read enable"},
    ],
    "macro_shiftreg": [
        {"handle": "en",    "signal": "shift_enable",  "desc": "shift enable — 1 to shift"},
        {"handle": "load",  "signal": "shift_load",    "desc": "parallel load strobe"},
    ],
    "reg": [
        {"handle": "en",    "signal": "reg_enable",    "desc": "register capture enable"},
    ],
}

__all__ = [_n for _n in dir() if not _n.startswith("__")]