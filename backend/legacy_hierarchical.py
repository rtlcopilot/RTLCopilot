

from __future__ import annotations

from generation_errors import (
    GenerationFailure as _GenFail,
    unsupported_block as _unsupported_block,
)

import json
import re
import traceback as _tb
from fastapi import HTTPException
from core import *
from prompts import *
import state


def _h_extract_json(raw: str) -> str | None:
    """Pull the first JSON object out of a raw LLM response."""
    for fence in ("```json", "```"):
        if fence in raw:
            s = raw.find(fence) + len(fence)
            e = raw.find("```", s)
            if e != -1:
                return raw[s:e].strip()
    if "{" in raw:
        depth, start = 0, raw.find("{")
        for ci, ch in enumerate(raw[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return raw[start:ci+1]
    return None


def _h_build_order(sub_circuits: list[dict]) -> list[str]:
    """
    Topological sort: return build order from leaves (no deps) to root.
    Falls back to the LLM-suggested order if a cycle is detected.
    """
    name_set = {sc["name"] for sc in sub_circuits}
    deps = {sc["name"]: [d for d in sc.get("depends_on", []) if d in name_set]
            for sc in sub_circuits}
    order, visited, temp = [], set(), set()

    def visit(n):
        if n in temp:
            return   # cycle -- skip
        if n in visited:
            return
        temp.add(n)
        for dep in deps.get(n, []):
            visit(dep)
        temp.discard(n)
        visited.add(n)
        order.append(n)

    for sc in sub_circuits:
        visit(sc["name"])
    return order


def _h_sanitise_sc(circuit_data: dict, prefix: str, width_hint: str,
                   x_off: float, y_off: float) -> tuple[list, list]:
    """
    Sanitise one sub-circuit's LLM output.
    Prefixes every node ID with `prefix` to avoid canvas collisions.
    Adds data.subCircuit for frontend colour-coding.
    Reuses the existing _VALID_TYPES / _src_handle / _tgt_handle helpers.
    """
    final_nodes, seen_ids = [], set()
    id_remap: dict[str, str] = {}

    for i, n in enumerate(circuit_data.get("nodes", [])):
        raw_id = re.sub(r'[^a-zA-Z0-9_]', '_',
                        str(n.get("id") or f"node_{i}").strip())
        nid = f"{prefix}__{raw_id}"
        base, sfx = nid, 1
        while nid in seen_ids:
            nid = f"{base}_{sfx}"; sfx += 1
        seen_ids.add(nid)
        id_remap[raw_id]          = nid
        id_remap[n.get("id", "")] = nid

        d        = n.get("data") or {}
        raw_type = str(n.get("type", "comb")).strip()
        if raw_type not in _VALID_TYPES:
            # Tier 1: never substitute silently. An unknown type used to
            # become a comb adder, producing a finished-looking circuit that
            # was wrong with nothing to indicate it.
            raise _unsupported_block(raw_type, sorted(_VALID_TYPES))

        raw_w = str(d.get("width") or n.get("width") or width_hint).strip()
        if raw_type == "macro_edgedet":
            raw_w = "1"

        fsm_outputs = []
        if raw_type == "fsm_state":
            for row in (d.get("fsmOutputs") or n.get("fsmOutputs") or []):
                if isinstance(row, dict):
                    sig = str(row.get("signal", "")).strip()
                    val = str(row.get("value",  "0")).strip()
                    if sig:
                        fsm_outputs.append({"signal": sig, "value": val})

        final_nodes.append({
            "id":   nid,
            "type": raw_type,
            "position": {
                "x": float(n.get("x") or (i * 250 + 100)) + x_off,
                "y": float(n.get("y") or 200) + y_off,
            },
            "data": {
                "name":        str(d.get("name") or n.get("name") or nid),
                "width":       raw_w,
                "op":          str(d.get("op")         or n.get("op")        or "add"),
                "value":       str(d.get("value")      or n.get("value")     or "0"),
                "muxSize":     str(d.get("muxSize")    or n.get("muxSize")   or "2"),
                "bitIndex":    str(d.get("bitIndex")   or "0"),
                "fifoDepth":   str(d.get("fifoDepth")  or "16"),
                "aeThresh":    str(d.get("aeThresh")   or "4"),
                "lsbPriority": int(d.get("lsbPriority")  or 0),
                "edgeType":    int(d.get("edgeType")     or 0),
                "addrWidth":   str(d.get("addrWidth")    or "6"),
                "countDir":    int(d.get("countDir")     or 1),
                "fsmOutputs":  fsm_outputs,
                "subCircuit":  prefix,
            },
        })

    ntype_map = {n["id"]: n["type"] for n in final_nodes}
    ndata_map = {n["id"]: n["data"] for n in final_nodes}
    final_edges, seen_handles, edge_counts = [], {}, {}

    for i, e in enumerate(circuit_data.get("edges", [])):
        raw_src = str(e.get("source") or "").strip()
        raw_tgt = str(e.get("target") or "").strip()
        src = id_remap.get(raw_src) or f"{prefix}__{re.sub(r'[^a-zA-Z0-9_]','_',raw_src)}"
        tgt = id_remap.get(raw_tgt) or f"{prefix}__{re.sub(r'[^a-zA-Z0-9_]','_',raw_tgt)}"

        if src not in ntype_map or tgt not in ntype_map:
            continue

        sh  = str(e.get("sourceHandle") or _src_handle(ntype_map[src])).strip()
        ec  = edge_counts.get(tgt, 0)
        rth = str(e.get("targetHandle", "")).strip()
        th  = rth if rth else _tgt_handle(ntype_map[tgt], ndata_map.get(tgt, {}), ec)

        is_fsm = (ntype_map.get(src) == "fsm_state" and
                  ntype_map.get(tgt) == "fsm_state")

        if not is_fsm:
            key = (tgt, th)
            if key in seen_handles:
                continue
            seen_handles[key] = True

        edge_counts[tgt] = ec + 1
        condition = str(e.get("condition", "1")).strip() or "1"
        if is_fsm and "." in condition:
            parts = condition.split(".")
            if len(parts) == 2 and parts[1] in ("out", "q", "in", "dout"):
                condition = parts[0].strip()

        entry = {
            "id": f"e_{prefix}_{i}",
            "source": src, "sourceHandle": sh,
            "target": tgt, "targetHandle": th,
            "animated": False,
        }
        if is_fsm:
            entry["type"] = "fsm"
            entry["data"] = {"condition": condition, "isFsm": True, "isEditing": False}
        final_edges.append(entry)

    return final_nodes, final_edges


def _h_find_boundary_node(sc_name: str, port_name: str,
                          node_type: str, node_ids: set,
                          all_nodes: list) -> str | None:
    """
    Find the real prefixed node ID for a declared boundary port.

    For output ports: also checks fsm_state nodes that declare the signal
    in their fsmOutputs — FSM signals are exposed via sourceHandle, not
    via a separate output node.
    """
    candidates = [
        f"{sc_name}__{port_name}",
        f"{sc_name}__{port_name}_{node_type}",
        f"{sc_name}__{node_type}_{port_name}",
        f"{sc_name}__{port_name}_node",
        f"{sc_name}__{port_name}_out",
        f"{sc_name}__{port_name}_output",
    ]
    matched = next((c for c in candidates if c in node_ids), None)

    if not matched:
        matched = next(
            (n["id"] for n in all_nodes
             if n["id"].startswith(f"{sc_name}__")
             and n["type"] == node_type
             and port_name.lower() in n["data"].get("name", "").lower()),
            None
        )

    if not matched and node_type == "output":
        fsm_match = next(
            (n for n in all_nodes
             if n["id"].startswith(f"{sc_name}__")
             and n["type"] == "fsm_state"
             and any(
                 row.get("signal", "").strip().lower() == port_name.lower()
                 for row in n["data"].get("fsmOutputs", [])
             )),
            None
        )
        if fsm_match:
            return f"{fsm_match['id']}::fsm_signal::{port_name}"

    return matched


def _h_build_relay_context(sc: dict, built_scs: dict) -> str:
    """
    Build the relay context string injected into a sub-circuit's build prompt.
    Handles both regular output nodes and FSM signal outputs (virtual IDs).
    """
    lines = []
    for dep_name in sc.get("depends_on", []):
        if dep_name not in built_scs:
            continue
        dep_info = built_scs[dep_name]
        lines.append(f"Already-built sub-circuit: {dep_name}")
        lines.append(f"  Role: {dep_info['role']}")
        lines.append("  Exported boundary output nodes (use these exact node IDs):")
        for port in dep_info["output_ports"]:
            nid = port["node_id"]
            if "::fsm_signal::" in nid:
                fsm_node_id, _, sig_name = nid.partition("::fsm_signal::")
                lines.append(
                    f"    FSM SIGNAL: source={fsm_node_id}  sourceHandle={sig_name}  "
                    f"signal={port['signal']}  width={port['width']}"
                )
                lines.append(
                    f"    Use source={fsm_node_id} and sourceHandle={sig_name} "
                    f"when wiring this FSM output to another block."
                )
            else:
                lines.append(
                    f"    node_id={nid}  signal={port['signal']}  "
                    f"width={port['width']}"
                )
        lines.append("  Use these node IDs as sources when wiring signals from "
                     f"{dep_name} into this sub-circuit.")
    return "\n".join(lines)


def _h_user_prompt(sc: dict, width_hint: str, relay_context: str) -> str:
    """
    Build the user message for one sub-circuit generation call.
    Includes boundary port declarations and relay context from dependencies.
    """
    boundary = ""
    if sc.get("imports"):
        descs = "\n".join(
            f"  - {p['signal']} ({p['width']}-bit) from {p.get('from','?')}"
            for p in sc["imports"]
        )
        boundary += (
            f"\nBOUNDARY INPUTS -- create one 'input' node for each:\n{descs}\n"
            "These represent signals arriving from other sub-circuits.\n"
        )
    if sc.get("exports"):
        descs = "\n".join(
            f"  - {p['signal']} ({p['width']}-bit)"
            for p in sc["exports"]
        )
        boundary += (
            f"\nBOUNDARY OUTPUTS -- create one 'output' node for each:\n{descs}\n"
            "These represent signals leaving this sub-circuit.\n"
        )

    fsm_hint = ""
    if sc.get("needs_fsm") and sc.get("fsm_states"):
        states      = sc["fsm_states"]
        states_str  = " -> ".join(states)

        output_sigs = [p["signal"] for p in sc.get("exports", [])]

        cond_sigs   = [p["signal"] for p in sc.get("imports", [])]

        state_hints = []
        for i, s in enumerate(states):
            if i == 0:
                vals = ", ".join(f"{sig}=0" for sig in output_sigs)
                state_hints.append(f"  {s} (RESET state): {vals if vals else 'all outputs 0'}")
            else:
                state_hints.append(f"  {s}: set appropriate outputs to 1 for this phase")
        state_hints_str = "\n".join(state_hints)

        relay_cond_lines = []
        if relay_context:
            for rline in relay_context.splitlines():
                if "node_id=" in rline and "fsm_signal" not in rline:
                    parts = dict(kv.split("=", 1) for kv in rline.strip().split() if "=" in kv)
                    if "node_id" in parts and "signal" in parts:
                        relay_cond_lines.append(
                            f"  - For condition signal '{parts['signal']}': "
                            f"create input node, wire from {parts['node_id']}, "
                            f"use that input node id as the FSM condition string."
                        )

        relay_cond_hint = ""
        if relay_cond_lines:
            relay_cond_hint = (
                f"\nRELAY CONDITION WIRING (use these exact source node IDs):\n"
                + "\n".join(relay_cond_lines) + "\n"
                + "  IMPORTANT: the condition field in FSM transition edges must be\n"
                + "  the INPUT NODE ID you create, NOT the original signal name.\n"
            )

        fsm_hint = (
            f"\nFSM REQUIRED -- use fsm_state nodes only. Follow FSM RULES strictly.\n"
            f"\nStates in order: {states_str}\n"
            f"\nPer-state output values:\n{state_hints_str}\n"
            f"\nfsmOutputs declaration (EVERY state must declare ALL of these signals):\n"
            + "".join(f'  {{\"signal\": \"{sig}\", \"value\": \"0_or_1\"}}\n' for sig in output_sigs)
            + f"\nCondition signals (create one 'input' node for each, width='1'):\n"
            + "".join(f"  - {sig}\n" for sig in cond_sigs)
            + relay_cond_hint
            + f"\nTransition wiring rules:\n"
            f"  - Wire states in sequence: {states_str} and back to {states[0]}\n"
            f"  - Use condition INPUT NODE IDs in the 'condition' edge field\n"
            f"  - Last data state transitions back to {states[0]} on completion condition\n"
            f"  - NEVER wire fsm_state outputs to output nodes -- they are internal regs\n"
            f"  - Only fsm_state.out -> fsm_state.in edges for transitions\n"
        )

    counter_hint = ""
    if "macro_cfgcounter" in str(sc.get("prompt", "")).lower() or        "baud" in str(sc.get("name", "")).lower() or        "counter" in str(sc.get("name", "")).lower():
        counter_hint = (
            "\nCOUNTER EXPORT RULES:\n"
            "  - Use macro_cfgcounter (NOT macro_counter) for baud rate generation.\n"
            "  - macro_cfgcounter has TWO outputs: count (N-bit) and tc (1-bit terminal count).\n"
            "  - The tc output fires a 1-bit pulse when count reaches its terminal value.\n"
            "  - For the boundary output node, export 'tc' (1-bit), not 'count'.\n"
            "  - Wire the tc output pin (sourceHandle='tc') to the boundary output node.\n"
        )

    relay = ""
    if relay_context:
        relay = (
            "\nRELAY CONTEXT -- signals available from already-built sub-circuits:\n"
            + relay_context
            + "\nReference these node IDs directly in your edge source/target fields.\n"
        )

    return (
        f"Sub-circuit to build: {sc['prompt']}\n"
        f"Role: {sc['role']}\n"
        f"Global data width: {width_hint}-bit\n"
        f"{boundary}"
        f"{fsm_hint}"
        f"{counter_hint}"
        f"{relay}"
        "\nBEFORE outputting JSON, verify:\n"
        "[ ] Every type is from BLOCK REFERENCE -- no invented types\n"
        "[ ] Every input handle has exactly one incoming edge\n"
        "[ ] Every output handle has at least one outgoing edge\n"
        "[ ] Multi-output blocks have ALL outputs wired\n"
        "[ ] 1-bit control nodes have width='1'\n"
        "[ ] Every edge has sourceHandle and targetHandle\n"
        "[ ] FSM states (if any) all share the same fsmOutputs signal names\n\n"
        "Output the JSON now:"
    )


async def _run_hierarchical(prompt: str, width_hint: str, current_user: str, llm=None, model=None) -> dict:
    """Core hierarchical generation logic. Called from ai_assist and ai_assist_hierarchical."""
    print(f"\n{'='*60}", flush=True)
    print(f"[HIER] REQUEST: {prompt}", flush=True)
    print(f"[HIER] Width hint: {width_hint}-bit", flush=True)
    print(f"{'='*60}", flush=True)

    try:
        print("\n[PHASE 1] Decomposing into sub-circuits...", flush=True)
        if llm is None:
            if _llm_client is None:
                raise HTTPException(status_code=403, detail={"code": "byok_required", "message": "No API key set. Please enter your API key in Settings."})
            llm = _llm_client
        if model is None: model = _LLM_MODEL
        decomp_resp = llm.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _H_DECOMPOSE_PROMPT},
                {"role": "user",   "content": f"Circuit to decompose: {prompt}"},
            ],
            temperature=0.0,
            max_tokens=2000,
        )
        decomp_raw  = decomp_resp.choices[0].message.content.strip()
        decomp_json = _h_extract_json(decomp_raw)
        if not decomp_json:
            print("[PHASE 1] ERROR: Could not extract JSON from decomposition response", flush=True)
            print(f"[PHASE 1] Raw response: {decomp_raw[:300]}", flush=True)
            return {"explanation": "Decomposition failed. Try /ai_assist for simpler designs.",
                    "nodes": [], "edges": []}

        decomp       = json.loads(decomp_json)
        sub_circuits = decomp.get("sub_circuits", [])[:6]
        if not sub_circuits:
            print("[PHASE 1] ERROR: No sub-circuits in response", flush=True)
            return {"explanation": "No sub-circuits returned.", "nodes": [], "edges": []}

        print(f"[PHASE 1] Got {len(sub_circuits)} sub-circuits:", flush=True)
        for sc in sub_circuits:
            fsm_tag  = " [FSM: " + ", ".join(sc.get("fsm_states", [])) + "]" if sc.get("needs_fsm") else ""
            deps_tag = f" | deps: {sc['depends_on']}" if sc.get("depends_on") else " | (leaf)"
            exports  = [e["signal"] for e in sc.get("exports", [])]
            imports  = [i["signal"] for i in sc.get("imports", [])]
            print(f"  - {sc['name']}{fsm_tag}{deps_tag}", flush=True)
            print(f"    role: {sc['role']}", flush=True)
            if imports:  print(f"    imports: {imports}", flush=True)
            if exports:  print(f"    exports: {exports}", flush=True)

        suggested_order = decomp.get("build_order", [])
        print(f"[PHASE 1] LLM suggested build order: {suggested_order}", flush=True)

        sc_by_name = {sc["name"]: sc for sc in sub_circuits}

        build_order = _h_build_order(sub_circuits)
        print("[PHASE 2] Skipped. Build order: " + str(build_order), flush=True)

        print(f"\n[PHASE 3] Building {len(build_order)} sub-circuits bottom-up...", flush=True)
        all_nodes: list = []
        all_edges: list = []
        built_scs: dict = {}

        SC_COLS   = 3
        X_SPACING = 1600
        Y_SPACING = 1000

        sc_index = {sc["name"]: i for i, sc in enumerate(sub_circuits)}

        for sc_name in build_order:
            sc = sc_by_name.get(sc_name)
            if not sc:
                print(f"  [{sc_name}] SKIP -- not found in sc_by_name", flush=True)
                continue

            idx   = sc_index.get(sc_name, len(built_scs))
            col   = idx % SC_COLS
            row   = idx // SC_COLS
            x_off = col * X_SPACING
            y_off = row * Y_SPACING

            relay_ctx = _h_build_relay_context(sc, built_scs)
            has_relay = bool(relay_ctx)
            print(f"\n  [{sc_name}] Building... {'(with relay context)' if has_relay else '(leaf -- no relay)'}", flush=True)
            if sc.get("needs_fsm"):
                print(f"  [{sc_name}] FSM states: {sc.get('fsm_states', [])}", flush=True)
            if has_relay:
                for line in relay_ctx.splitlines():
                    print(f"  [{sc_name}]   relay> {line}", flush=True)

            user_msg = _h_user_prompt(sc, width_hint, relay_ctx)

            try:
                sc_resp = llm.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user",   "content": user_msg},
                    ],
                    temperature=0.0,
                    max_tokens=2500,
                )
                sc_raw  = sc_resp.choices[0].message.content.strip()
                sc_json = _h_extract_json(sc_raw)
                if not sc_json:
                    print(f"  [{sc_name}] ERROR: No JSON in response -- skipping", flush=True)
                    continue
                sc_data = json.loads(sc_json)
            except Exception:
                print(f"  [{sc_name}] ERROR: LLM call or parse failed", flush=True)
                _tb.print_exc()
                continue

            sc_nodes, sc_edges = _h_sanitise_sc(sc_data, sc_name, width_hint, x_off, y_off)
            all_nodes.extend(sc_nodes)
            all_edges.extend(sc_edges)
            print(f"  [{sc_name}] Built -> {len(sc_nodes)} nodes, {len(sc_edges)} edges", flush=True)

            node_ids = {n["id"] for n in all_nodes}
            output_ports = []
            for exp in sc.get("exports", []):
                nid = _h_find_boundary_node(sc_name, exp["signal"], "output",
                                            node_ids, all_nodes)
                if nid:
                    output_ports.append({
                        "node_id": nid,
                        "signal":  exp["signal"],
                        "width":   exp.get("width", width_hint),
                    })
                    print(f"  [{sc_name}] Export resolved: {exp['signal']} -> {nid}", flush=True)
                else:
                    print(f"  [{sc_name}] WARNING: Export '{exp['signal']}' node not found", flush=True)
                    sc_nodes_list = [n for n in all_nodes if n["id"].startswith(f"{sc_name}__")]
                    print(f"  [{sc_name}]   Available nodes: {[n['id'] + '(' + n['type'] + ')' for n in sc_nodes_list]}", flush=True)

            built_scs[sc_name] = {
                "role":         sc.get("role", ""),
                "output_ports": output_ports,
            }

        print(f"\n[PHASE 3] Done -- total: {len(all_nodes)} nodes, {len(all_edges)} edges", flush=True)

        if not all_nodes:
            print("[PHASE 3] ERROR: No nodes generated at all", flush=True)
            return {"explanation": "All sub-circuit generations failed. Please try again.",
                    "nodes": [], "edges": []}

        print("[PHASE 4] Assembly skipped -- sub-circuits placed on canvas for manual wiring.", flush=True)
        print("[PHASE 4] Sub-circuits: " + str(list(built_scs.keys())), flush=True)

        sc_names = [sc.get("name", "") for sc in sub_circuits]
        print(f"\n{'='*60}", flush=True)
        print(f"[HIER] DONE -- {len(all_nodes)} nodes, {len(all_edges)} edges total", flush=True)
        print(f"[HIER] Sub-circuits: {sc_names}", flush=True)
        print(f"{'='*60}\n", flush=True)
        return {
            "explanation": (
                f"Built {len(sub_circuits)} sub-circuits in dependency order: "
                f"{', '.join(sc_names)}."
            ),
            "nodes":              all_nodes,
            "edges":              all_edges,
            "hierarchical":       True,
            "sub_circuit_names":  sc_names,
        }

    except json.JSONDecodeError as exc:
        print(f"[HIER] JSON PARSE ERROR: {exc}", flush=True)
        return {"explanation": f"JSON parse error: {exc}", "nodes": [], "edges": []}
    except Exception:
        print("[HIER] INTERNAL ERROR:", flush=True)
        _tb.print_exc()
        return {"explanation": "Internal error in hierarchical generation.", "nodes": [], "edges": []}

__all__ = [_n for _n in dir() if not _n.startswith("__")]