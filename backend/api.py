# -*- coding: utf-8 -*-
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import json
import re as re
import os
import math
import subprocess
from pathlib import Path
from openai import OpenAI
import tempfile
from datetime import datetime, timezone
import traceback as _tb
from block_mapper import (
    map_concepts_to_primitives,
    get_stage0_vocabulary_prompt,
    GENERIC_VOCABULARY,
)
from known_circuits import (
    _KNOWN_HIERARCHIES as _KC_HIERARCHIES,
    _FSM_TRANSITION_TABLES as _KC_FSM_TABLES,
    _CIRCUIT_KEYWORDS as _KC_KEYWORDS,
    get_circuit_key as _kc_classify,
    PRIMITIVE_BLOCK_SPECS as _PRIM_SPECS,
)
from net_ir import build_net_ir, validate_net_ir, get_driver_wire
import port_contract as _pc
from semantic_library import generate_test_plan
from generation_errors import (
    GenerationFailure as _GenFail,
    unsupported_block as _unsupported_block,
)


from core import *
from models import *
from prompts import *
from ir_checks import *
from verilog_tools import *
from legacy_hierarchical import *
from hierarchical_v2 import *
from rtl_brain import *
import state
from state import _FSM_TRANSITION_TABLES
import hmac
import hashlib
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv(Path(__file__).parent / ".env")

_enable_docs   = os.environ.get("ENABLE_DOCS",    "false").lower() == "true"
app = FastAPI(
    docs_url="/docs" if _enable_docs else None,
    redoc_url="/redoc" if _enable_docs else None,
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
]
_prod_origin = os.environ.get("ALLOWED_ORIGINS", "")
if _prod_origin:
    _ALLOWED_ORIGINS.extend([o.strip() for o in _prod_origin.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-User-Api-Key", "X-User-Api-Provider", "X-User-Model"],
    max_age=600,
)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"]  = "nosniff"
        response.headers["X-Frame-Options"]         = "DENY"
        response.headers["Referrer-Policy"]         = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"]        = "1; mode=block"
        return response

app.add_middleware(SecurityHeadersMiddleware)

@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 2_000_000:
        return JSONResponse(
            {"error": "Payload too large. Maximum request size is 2MB."},
            status_code=413
        )
    return await call_next(request)


PLAN_CONFIG = {
}


@app.post("/generate_verilog")
def generate_verilog(payload: GenerateRequest):
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", dir=str(CODEGEN_DIR),
        delete=False, encoding="utf-8"
    ) as tf:
        json.dump(payload.ir, tf, indent=2)
        ir_path = tf.name
    try:
        result = subprocess.run(
            ["python", str(EMIT_SCRIPT), ir_path],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(CODEGEN_DIR)
        )
    finally:
        Path(ir_path).unlink(missing_ok=True)
    if result.returncode != 0:
        print("[generate_verilog ERROR]", result.stderr, flush=True)
        return {"status": "error", "stderr": result.stderr, "stdout": result.stdout}
    try:
        files = json.loads(result.stdout)
    except Exception:
        files = {"top.v": result.stdout}
    if "top.v" in files:
        with open(TOP_VERILOG, "w") as f:
            f.write(files["top.v"])
    for fname, code in files.items():
        if fname != "top.v":
            with open(CODEGEN_DIR / fname, "w") as f:
                f.write(code)
    return {"status": "ok", "files": files}


@app.post("/generate_testbench")
def generate_testbench(payload: TBRequest):
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", dir=str(CODEGEN_DIR),
        delete=False, encoding="utf-8"
    ) as tf:
        json.dump({"ir": payload.ir, "stimulus": payload.stimulus}, tf, indent=2)
        tb_ir_path = tf.name
    try:
        result = subprocess.run(
            ["python", str(TB_SCRIPT), tb_ir_path],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(CODEGEN_DIR)
        )
    finally:
        Path(tb_ir_path).unlink(missing_ok=True)
    if result.returncode != 0 or not result.stdout.strip():
        return {
            "status": "error",
            "testbench": f"// Testbench generation failed:\n// {result.stderr.strip() or 'empty output'}",
            "stderr": result.stderr,
        }
    return {"status": "ok", "testbench": result.stdout}



def _classify_prompt(prompt: str) -> str:
    """
    Single routing decision for all circuit generation requests.

    Returns:
      "known"   — prompt matches a known circuit in _KNOWN_HIERARCHIES
                  → use deterministic IR-first v2 flow
      "complex" — prompt implies multi-block design but not in known library
                  → use LLM hierarchical decomposition flow
      "simple"  — short, straightforward single-block request
                  → use single LLM call
    """
    try:
        key, _ = _v2_classify(prompt)
        if key:
            return "known"
    except Exception:
        pass

    p = prompt.lower()
    complex_keywords = [
        "controller", "transmitter", "receiver", "protocol",
        "state machine", "handshake", "arbiter", "scheduler",
        "pipeline", "dma", "viterbi", "fir filter", "iir filter",
        "processor", "cpu", "alu", "decoder", "encoder logic",
    ]
    word_count = len(prompt.strip().split())
    if any(k in p for k in complex_keywords) or word_count > 10:
        return "complex"

    return "simple"


@app.post("/ai_assist")
@limiter.limit("10/minute")
async def ai_assist(
    request: Request,
    payload: ChatRequest,
    current_user: str = Depends(_get_current_user)
):
    user_api_key, user_provider, user_model = _extract_user_api_key(request)
    byok = bool(user_api_key)
    llm, _byok_model = _get_llm_client(user_api_key, user_provider, user_model)

    if not byok:
        try:
            sb = _supabase()
            if not byok:
                raise HTTPException(
                    status_code=403,
                    detail={"code": "byok_required", "message": "Please provide your own API key in Settings to use AI features."}
                )
        except HTTPException:
            raise
        except RuntimeError:
            pass
        except Exception:
            _tb.print_exc()

    width_hint = "8"
    m = re.search(r'\b(\d+)\s*[-\u2013]?\s*bit\b', payload.prompt, re.IGNORECASE)
    if m:
        width_hint = m.group(1)

    route = _classify_prompt(payload.prompt)
    print(f"[ai_assist] Route: {route} | prompt: {payload.prompt[:60]}", flush=True)

    if route == "known":
        return await _run_hierarchical_v2(payload.prompt, current_user, byok=byok)

    if route == "complex":
        # Tier 1: a failed generation returns an explicit, actionable failure
        # payload and leaves the canvas untouched — never a silent fallback
        # circuit the user has no reason to distrust.
        try:
            return await _run_rtl_brain(payload.prompt, width_hint, current_user,
                                        llm=llm, byok=byok, model=_byok_model)
        except _GenFail as gf:
            print(f"[ai_assist] generation failed: {gf}", flush=True)
            return gf.to_response()


    user_message = (
        f"Circuit to build: {payload.prompt}\n\n"
        f"Global data width: {width_hint}-bit "
        f"(use this for ALL data nodes unless the description specifies otherwise).\n\n"
        "BEFORE outputting JSON, mentally verify:\n"
        "[ ] Every block type is from BLOCK REFERENCE -- no invented types\n"
        "[ ] Every input handle on every block has exactly one incoming edge\n"
        "[ ] Every output handle on every block has at least one outgoing edge\n"
        "[ ] Multi-output blocks (fifo, penc, dpram, cfgcounter) have ALL outputs wired\n"
        "[ ] All 1-bit control inputs have width='1' in their node data\n"
        "[ ] All data wires have matching width at both ends\n"
        "[ ] Every edge has both sourceHandle and targetHandle\n"
        "[ ] No handle names are invented -- only names from BLOCK REFERENCE\n"
        "[ ] Every output node has exactly one incoming edge\n\n"
        "Output the JSON now:"
    )

    raw = ""
    try:
        completion = llm.chat.completions.create(
            model=_byok_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.0,
            max_tokens=4000,
        )
        raw = completion.choices[0].message.content.strip()

        json_str = None
        if "```json" in raw:
            s = raw.find("```json") + 7
            e = raw.find("```", s)
            json_str = raw[s:e].strip()
        elif raw.count("```") >= 2:
            s = raw.find("```") + 3
            e = raw.rfind("```")
            json_str = raw[s:e].strip()
        elif "{" in raw:
            depth, start, end = 0, raw.find("{"), -1
            for ci, ch in enumerate(raw[start:], start):
                if ch == "{": depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0: end = ci; break
            if end != -1:
                json_str = raw[start:end+1]

        if not json_str:
            raise ValueError("No JSON object found in AI response")

        circuit_data = json.loads(json_str)

        final_nodes, seen_ids = [], set()

        for i, n in enumerate(circuit_data.get("nodes", [])):
            nid = re.sub(r'[^a-zA-Z0-9_]', '_', str(n.get("id") or f"node_{i}").strip())
            base, sfx = nid, 1
            while nid in seen_ids:
                nid = f"{base}_{sfx}"; sfx += 1
            seen_ids.add(nid)

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

            # Sanitize fsmOutputs for fsm_state nodes
            raw_fsm_outputs = []
            if raw_type == "fsm_state":
                raw_outputs = d.get("fsmOutputs") or n.get("fsmOutputs") or []
                for row in raw_outputs:
                    if isinstance(row, dict):
                        sig = str(row.get("signal", "")).strip()
                        val = str(row.get("value",  "0")).strip()
                        if sig:
                            raw_fsm_outputs.append({"signal": sig, "value": val})

            final_nodes.append({
                "id":   nid,
                "type": raw_type,
                "position": {
                    "x": float(n.get("x") or (i * 250 + 100)),
                    "y": float(n.get("y") or 200),
                },
                "data": {
                    "name":        str(d.get("name")        or n.get("name")      or nid),
                    "width":       raw_w,
                    "op":          str(d.get("op")          or n.get("op")        or "add"),
                    "value":       str(d.get("value")       or n.get("value")     or "0"),
                    "muxSize":     str(d.get("muxSize")     or n.get("muxSize")   or "2"),
                    "bitIndex":    str(d.get("bitIndex")    or "0"),
                    "fifoDepth":   str(d.get("fifoDepth")   or "16"),
                    "aeThresh":    str(d.get("aeThresh")    or "4"),
                    "lsbPriority": int(d.get("lsbPriority") or 0),
                    "edgeType":    int(d.get("edgeType")    or 0),
                    "addrWidth":   str(d.get("addrWidth")   or "6"),
                    "countDir":    int(d.get("countDir")    or 1),
                    "fsmOutputs":  raw_fsm_outputs,
                },
            })

        ntype = {n["id"]: n["type"] for n in final_nodes}
        ndata = {n["id"]: n["data"] for n in final_nodes}
        final_edges, edge_counts, seen_handles = [], {}, {}

        for i, e in enumerate(circuit_data.get("edges", [])):
            src = re.sub(r'[^a-zA-Z0-9_]', '_', str(e.get("source") or "").strip())
            tgt = re.sub(r'[^a-zA-Z0-9_]', '_', str(e.get("target") or "").strip())
            if not src or not tgt: continue
            if src not in ntype: continue
            if tgt not in ntype: continue

            sh = str(e.get("sourceHandle") or _src_handle(ntype[src])).strip()
            ec = edge_counts.get(tgt, 0)
            th = str(e.get("targetHandle") or _tgt_handle(ntype[tgt], ndata.get(tgt,{}), ec)).strip()

            is_fsm_edge = (ntype.get(src) == "fsm_state" and ntype.get(tgt) == "fsm_state")

            if not is_fsm_edge:
                key = (tgt, th)
                if key in seen_handles: continue
                seen_handles[key] = True
            edge_counts[tgt] = ec + 1

            condition = str(e.get("condition", "1")).strip() or "1"
            if is_fsm_edge and "." in condition:
                parts = condition.split(".")
                if len(parts) == 2 and parts[1] in ("out", "q", "in", "dout"):
                    condition = parts[0].strip()
            edge_entry = {
                "id": f"e_{i}", "source": src, "sourceHandle": sh,
                "target": tgt, "targetHandle": th, "animated": False,
            }
            if is_fsm_edge:
                edge_entry["type"] = "fsm"
                edge_entry["data"] = {"condition": condition, "isFsm": True, "isEditing": False}

            final_edges.append(edge_entry)

        driven  = {e["target"] for e in final_edges}
        sourced = {e["source"] for e in final_edges}

        for onode in [n for n in final_nodes if n["type"] == "output"]:
            if onode["id"] in driven:
                continue
            dangling = [
                n for n in final_nodes
                if n["type"] not in ("output", "input", "const", "fsm_state") and n["id"] not in sourced
            ]
            cands = dangling or [n for n in final_nodes if n["type"] not in ("output", "input", "const", "fsm_state")]
            cands.sort(key=lambda n: (
                0 if n["type"].startswith("macro") else
                1 if n["type"] == "reg" else
                2 if n["type"] == "comb" else 3,
                -n["position"]["x"]
            ))
            if cands:
                src_n = cands[0]
                key   = (onode["id"], "in")
                if key not in seen_handles:
                    seen_handles[key] = True
                    sourced.add(src_n["id"])
                    final_edges.append({
                        "id": f"auto_{onode['id']}",
                        "source": src_n["id"], "sourceHandle": _src_handle(src_n["type"]),
                        "target": onode["id"], "targetHandle": "in",
                        "animated": False,
                    })

        sourced = {e["source"] for e in final_edges}

        MULTI_OUT = {
            "macro_fifo":        [("dout","data"), ("full","full"), ("empty","empty"), ("ae","ae")],
            "macro_penc":        [("index","index"), ("valid","valid")],
            "macro_dpram":       [("dout_a","dout_a"), ("dout_b","dout_b")],
            "macro_cfgcounter":  [("count","count"), ("tc","tc")],
        }

        auto_x_base = max((n["position"]["x"] for n in final_nodes), default=100) + 300
        auto_y      = 100
        auto_idx    = 0

        for n in list(final_nodes):
            ntype_n = n["type"]

            if ntype_n in MULTI_OUT:
                for (port_handle, port_label) in MULTI_OUT[ntype_n]:
                    already = any(
                        e["source"] == n["id"] and e["sourceHandle"] == port_handle
                        for e in final_edges
                    )
                    if already:
                        continue
                    base_w = n["data"].get("width", "8")
                    if port_handle in ("full","empty","ae","valid","tc"):
                        out_w = "1"
                    elif port_handle == "index":
                        out_w = str(max(1, math.ceil(math.log2(max(int(base_w), 2)))))
                    else:
                        out_w = base_w
                    out_id = f"auto_out_{n['id']}_{port_handle}"
                    final_nodes.append({
                        "id":   out_id,
                        "type": "output",
                        "position": {"x": auto_x_base, "y": auto_y + auto_idx * 150},
                        "data": {
                            "name": f"{n['data']['name']}_{port_label}",
                            "width": out_w,
                            "op":"add","value":"0","muxSize":"2",
                            "bitIndex":"0","fifoDepth":"16","aeThresh":"4",
                            "lsbPriority":0,"edgeType":0,"addrWidth":"6","countDir":1,
                        },
                    })
                    final_edges.append({
                        "id": f"auto_e_{out_id}",
                        "source": n["id"], "sourceHandle": port_handle,
                        "target": out_id,  "targetHandle": "in",
                        "animated": False,
                    })
                    auto_idx += 1
            else:
                if n["id"] in sourced or ntype_n in ("output", "input", "const", "fsm_state"):
                    continue
                out_id = f"auto_out_{n['id']}"
                final_nodes.append({
                    "id":   out_id,
                    "type": "output",
                    "position": {"x": auto_x_base, "y": auto_y + auto_idx * 150},
                    "data": {
                        "name": n["data"]["name"] + "_out",
                        "width": n["data"].get("width", "8"),
                        "op":"add","value":"0","muxSize":"2",
                        "bitIndex":"0","fifoDepth":"16","aeThresh":"4",
                        "lsbPriority":0,"edgeType":0,"addrWidth":"6","countDir":1,
                    },
                })
                final_edges.append({
                    "id": f"auto_e_{out_id}",
                    "source": n["id"], "sourceHandle": _src_handle(ntype_n),
                    "target": out_id,  "targetHandle": "in",
                    "animated": False,
                })
                sourced.add(n["id"])
                auto_idx += 1

        if not byok:
            try:
                sb = _supabase()
            except Exception:
                pass

        return {
            "explanation": str(circuit_data.get("explanation","Circuit generated.")),
            "nodes": final_nodes,
            "edges": final_edges,
        }

    except json.JSONDecodeError as e:
        return {"explanation": f"AI returned malformed JSON: {e}", "nodes": [], "edges": []}
    except _GenFail as gf:
        # Tier 1: an unsupported block type reaches here instead of being
        # silently rewritten to an adder.
        print(f"[ai_assist] generation failed: {gf}", flush=True)
        return gf.to_response()
    except Exception:
        _tb.print_exc()
        return {"explanation": "Internal error -- check backend logs.", "nodes": [], "edges": []}


@app.get("/handle_contract")
def get_handle_contract():
    """The port width contract, for the canvas DRC.

    The frontend used to maintain its own resolveOutWidth / expectedPinWidth
    tables, which drifted from the backend's. Serving the contract means the
    canvas checks exactly the rules the emitter obeys. Symbolic specs (not
    pre-resolved widths) are returned so the canvas can resolve per node using
    each node's own width / addrWidth / muxSize / srMode.
    """
    return _pc.handle_contract()


@app.get("/projects")
@limiter.limit("60/minute")
async def list_projects(
    request: Request,
    current_user: str = Depends(_get_current_user)
):
    if _OFFLINE_MODE:
        db = _local_db_read()
        projects = list(db.get("projects", {}).values())
        projects.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
        return {"status": "ok", "projects": projects}
    try:
        sb = _supabase()
        res = (sb.table("projects")
                 .select("id, name, description, created_at, updated_at")
                 .eq("user_id", current_user)
                 .order("updated_at", desc=True)
                 .execute())
        return {"status": "ok", "projects": res.data}
    except HTTPException:
        raise
    except RuntimeError as e:
        return {"status": "not_configured", "error": str(e), "projects": []}
    except Exception:
        _tb.print_exc()
        return {"status": "error", "error": "Internal server error", "projects": []}


@app.post("/projects")
@limiter.limit("60/minute")
async def save_project(
    request: Request,
    payload: ProjectSaveRequest,
    current_user: str = Depends(_get_current_user)
):
    if _OFFLINE_MODE:
        import uuid, datetime
        db = _local_db_read()
        pid = str(uuid.uuid4())
        now = datetime.datetime.utcnow().isoformat()
        project = {"id": pid, "user_id": "local_user", "name": payload.name,
                   "description": payload.description, "canvas": payload.canvas,
                   "created_at": now, "updated_at": now}
        db.setdefault("projects", {})[pid] = project
        _local_db_write(db)
        return {"status": "ok", "project": project}
    try:
        sb = _supabase()
        res = sb.table("projects").insert({
            "user_id":     current_user,
            "name":        payload.name,
            "description": payload.description,
            "canvas":      payload.canvas,
        }).execute()
        return {"status": "ok", "project": res.data[0] if res.data else {}}
    except HTTPException:
        raise
    except RuntimeError as e:
        return {"status": "not_configured", "error": str(e)}
    except Exception:
        _tb.print_exc()
        return {"status": "error", "error": "Internal server error"}


@app.put("/projects/{project_id}")
@limiter.limit("60/minute")
async def update_project(
    request: Request,
    project_id: str,
    payload: ProjectUpdateRequest,
    current_user: str = Depends(_get_current_user)
):
    if _OFFLINE_MODE:
        import datetime
        db = _local_db_read()
        project = db.get("projects", {}).get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        if payload.name is not None: project["name"] = payload.name
        if payload.description is not None: project["description"] = payload.description
        if payload.canvas is not None: project["canvas"] = payload.canvas
        project["updated_at"] = datetime.datetime.utcnow().isoformat()
        _local_db_write(db)
        return {"status": "ok", "project": project}
    try:
        sb = _supabase()
        check = (sb.table("projects")
                   .select("user_id")
                   .eq("id", project_id)
                   .single()
                   .execute())
        if not check.data:
            raise HTTPException(status_code=404, detail="Project not found")
        if check.data["user_id"] != current_user:
            raise HTTPException(status_code=403, detail="Access denied")

        updates = {k: v for k, v in {
            "name":        payload.name,
            "description": payload.description,
            "canvas":      payload.canvas,
        }.items() if v is not None}
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        res = sb.table("projects").update(updates).eq("id", project_id).execute()
        return {"status": "ok", "project": res.data[0] if res.data else {}}
    except HTTPException:
        raise
    except RuntimeError as e:
        return {"status": "not_configured", "error": str(e)}
    except Exception:
        _tb.print_exc()
        return {"status": "error", "error": "Internal server error"}


@app.delete("/projects/{project_id}")
@limiter.limit("60/minute")
async def delete_project(
    request: Request,
    project_id: str,
    current_user: str = Depends(_get_current_user)
):
    if _OFFLINE_MODE:
        db = _local_db_read()
        if project_id in db.get("projects", {}):
            del db["projects"][project_id]
            _local_db_write(db)
        return {"status": "ok"}
    try:
        sb = _supabase()
        check = (sb.table("projects")
                   .select("user_id")
                   .eq("id", project_id)
                   .single()
                   .execute())
        if not check.data:
            raise HTTPException(status_code=404, detail="Project not found")
        if check.data["user_id"] != current_user:
            raise HTTPException(status_code=403, detail="Access denied")

        sb.table("projects").delete().eq("id", project_id).execute()
        return {"status": "ok"}
    except HTTPException:
        raise
    except RuntimeError as e:
        return {"status": "not_configured", "error": str(e)}
    except Exception:
        _tb.print_exc()
        return {"status": "error", "error": "Internal server error"}


@app.get("/projects/{project_id}/load")
@limiter.limit("60/minute")
async def load_project(
    request: Request,
    project_id: str,
    current_user: str = Depends(_get_current_user)
):
    if _OFFLINE_MODE:
        db = _local_db_read()
        project = db.get("projects", {}).get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return {"status": "ok", "project": project}
    try:
        sb = _supabase()
        res = (sb.table("projects")
                 .select("*")
                 .eq("id", project_id)
                 .eq("user_id", current_user)
                 .single()
                 .execute())
        if not res.data:
            raise HTTPException(status_code=404, detail="Project not found or access denied")
        return {"status": "ok", "project": res.data}
    except HTTPException:
        raise
    except RuntimeError as e:
        return {"status": "not_configured", "error": str(e)}
    except Exception:
        _tb.print_exc()
        return {"status": "error", "error": "Internal server error"}


@app.post("/ai_chat")
@limiter.limit("30/minute")
async def ai_chat(
    request: Request,
    payload: dict,
    current_user: str = Depends(_get_current_user)
):
    """Conversational Q&A about circuits -- does NOT deduct credits."""
    llm, _chat_model = _get_llm_client(*_extract_user_api_key(request))
    prompt  = str(payload.get("prompt", ""))[:1000]
    history = payload.get("history", [])[-6:]
    nodes   = payload.get("current_nodes", [])

    canvas_summary = ""
    if nodes:
        names = [n.get("name", n.get("id", "?")) for n in nodes[:10]]
        canvas_summary = f"Current canvas has {len(nodes)} blocks: {', '.join(names)}."

    system = (
        "You are RTL Copilot's assistant -- a friendly, knowledgeable hardware design tutor. "
        "You help users understand RTL concepts, explain circuit decisions, and suggest improvements. "
        "Keep answers concise and practical. If the user asks you to build or modify a circuit, "
        "tell them to switch to Build mode. Do not output JSON."
    )
    messages = [{"role": "system", "content": system}]
    if canvas_summary:
        messages.append({"role": "system", "content": canvas_summary})
    for h in history:
        if h.get("role") in ("user", "assistant"):
            messages.append({"role": h["role"], "content": str(h.get("content", ""))})
    messages.append({"role": "user", "content": prompt})

    try:
        completion = llm.chat.completions.create(
            model=_chat_model,
            messages=messages,
            temperature=0.4,
            max_tokens=600,
        )
        reply = completion.choices[0].message.content.strip()
        return {"status": "ok", "reply": reply}
    except Exception:
        _tb.print_exc()
        return {"status": "error", "reply": "Sorry, I couldn't process that. Please try again."}



@app.post("/pd_assist")
async def pd_assist(
    request: Request,
    payload: dict,
):
    """PD-aware AI assistant for RTL Copilot. Deducts 1 credit per call."""
    _byok_key_pd, _provider_pd, _model_pd = _extract_user_api_key(request)
    _byok_pd = bool(_byok_key_pd)
    _llm_pd, _byok_model_pd = _get_llm_client(_byok_key_pd, _provider_pd, _model_pd)

    mode     = payload.get("mode", "error")
    stage    = payload.get("stage", "unknown")
    logs     = payload.get("logs", [])
    run_meta = payload.get("run_meta", {})
    verilog  = payload.get("verilog", "")
    config   = payload.get("config", {})

    # The PD verification layer (pdtools/pd_verification.py) already computed
    # the failing checks AND the fixes deterministically. The LLM's ONLY job
    # here is a plain-English explanation — it never computes values.
    if mode == "check_explain":
        ce_checks   = [c for c in payload.get("checks", []) if isinstance(c, dict)][:10]
        ce_fixes    = [f for f in payload.get("fixes", []) if isinstance(f, dict)][:5]
        ce_guidance = str(payload.get("guidance") or "")[:600]

        checks_str = "\n".join(
            f"- [{str(c.get('status', '?')).upper()}] {c.get('label', '?')}: "
            f"{c.get('value', '?')}{c.get('unit', '')} — {c.get('message', '')}"
            for c in ce_checks) or "none"
        fixes_str = "\n".join(
            f"- {f.get('label', '?')} ({f.get('stage', '?')} → {f.get('field', '?')}): "
            f"{f.get('current_value')} → {f.get('proposed_value')}\n"
            f"  computed from: {f.get('context', '')}"
            for f in ce_fixes) or "none"

        ce_system = (
            "You are an expert ASIC physical design engineer inside RTL Copilot, a no-code "
            "visual ASIC tool. A deterministic verification layer already analyzed the failing "
            "checks and ALREADY COMPUTED the fixes from first principles. Your only job is to "
            "explain, in plain English, what failed and what the pre-computed fixes will do. "
            "Do not suggest additional fixes or config values — fixes are already computed. "
            "Do not modify, question, or recompute the proposed values. Never suggest bash "
            "commands. Reference the actual numbers given. "
            'Respond ONLY with JSON, no markdown fences: '
            '{"explanation": "2-3 sentences explaining what failed and what the fixes will do"}'
        )
        ce_user = (
            "Stage: " + stage + "\n\n"
            "Failing checks:\n" + checks_str + "\n\n"
            "Pre-computed fixes (already final — explain, don't change):\n" + fixes_str +
            (("\n\nDeterministic guidance (no config fix available): " + ce_guidance) if ce_guidance else "") +
            "\n\nReturn the JSON now."
        )
        try:
            completion = _llm_pd.chat.completions.create(
                model=_byok_model_pd,
                messages=[
                    {"role": "system", "content": ce_system},
                    {"role": "user",   "content": ce_user},
                ],
                temperature=0.1,
                max_tokens=250,
            )
            raw = completion.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
            try:
                parsed = json.loads(raw)
                explanation = str(parsed.get("explanation", "")).strip() or raw
            except Exception:
                explanation = raw
            # Same guard as the other modes — never leak shell/tcl blocks
            explanation = re.sub(r"```[\s\S]*?```", "", explanation).strip()
            return {"status": "ok", "explanation": explanation}
        except Exception:
            _tb.print_exc()
            return {"status": "error",
                    "explanation": "AI explanation unavailable — the computed fixes are still valid."}

    all_logs_str = payload.get("allLogs", "")
    all_logs     = all_logs_str.split("\n") if all_logs_str else logs

    full_log = "\n".join(all_logs)

    wns_m     = re.search(r'wns\s+(?:max\s+)?([\-\d\.]+)', full_log, re.IGNORECASE)
    tns_m     = re.search(r'tns\s+(?:max\s+)?([\-\d\.]+)', full_log, re.IGNORECASE)
    slack_m   = re.search(r'([\d\.]+)\s+slack \(MET\)', full_log)  
    hold_m    = re.search(r'([\d\.]+)\s+slack \(MET\).*?min', full_log, re.DOTALL)
    power_m   = re.search(r'Total\s+[\d\.e\+\-]+\s+[\d\.e\+\-]+\s+[\d\.e\+\-]+\s+([\d\.e\+\-]+)', full_log)
    cells_m   = re.search(r'(\d+)\s+138\.883\s+cells', full_log)  
    cells_m2  = re.search(r'Number of instances:\s+(\d+)', full_log)
    util_m    = re.search(r'Utilization:\s+([\d\.]+)', full_log)  
    area_m    = re.search(r'Chip area for top module.*?:\s+([\d\.]+)', full_log)
    die_m     = re.search(r'Die BBox:.*?\(\s*([\d\.]+)\s+([\d\.]+)\s*\).*?\(\s*([\d\.]+)\s+([\d\.]+)', full_log)
    clk_net_m = re.search(r'clock network delay \((propagated|ideal)\)', full_log)

    viol_m    = re.search(r'Number of violations\s*=\s*(\d+)', full_log)

    cts_buf_m = re.search(r'Created\s+(\d+)\s+components', full_log)

    metrics = {
        "wns_ns":          wns_m.group(1)   if wns_m    else "unknown",
        "tns_ns":          tns_m.group(1)   if tns_m    else "unknown",
        "worst_slack_ns":  slack_m.group(1) if slack_m  else "unknown",
        "power_w":         power_m.group(1) if power_m  else "unknown",
        "cell_count":      (cells_m.group(1) if cells_m else (cells_m2.group(1) if cells_m2 else "unknown")),
        "utilization_pct": util_m.group(1)  if util_m   else "unknown",
        "chip_area_um2":   area_m.group(1)  if area_m   else "unknown",
        "clock_type":      clk_net_m.group(1) if clk_net_m else "unknown",
        "routing_violations": viol_m.group(1) if viol_m else "0",
        "die_area":        f"{die_m.group(1)} {die_m.group(2)} {die_m.group(3)} {die_m.group(4)}" if die_m else config.get("die_area", "unknown"),
    }

    insights = []
    try:
        wns_val = float(metrics["wns_ns"]) if metrics["wns_ns"] != "unknown" else None
        slack_val = float(metrics["worst_slack_ns"]) if metrics["worst_slack_ns"] != "unknown" else None
        clk_period = float(config.get("clock_period_ns", 10))

        if slack_val and slack_val > 0:
            max_freq_mhz = round(1000 / (clk_period - slack_val), 1)
            insights.append(f"Worst slack is {slack_val}ns on a {clk_period}ns period -- the design can run at ~{max_freq_mhz}MHz. You could reduce Clock Period to {round(clk_period - slack_val * 0.8, 1)}ns.")

        util = float(metrics["utilization_pct"]) if metrics["utilization_pct"] != "unknown" else None
        
        util_pct = util  
        if util_pct and util_pct < 10:
            insights.append(f"Core utilization is only {util_pct}% -- die is massively oversized. Reduce Die Area in Floorplan Config to save area and improve wire lengths.")
        elif util_pct and util_pct > 70:
            insights.append(f"Core utilization is {util_pct}% -- very high, likely causing routing congestion. Increase Die Area or reduce Density in Placement Config.")

        cells = int(metrics["cell_count"]) if metrics["cell_count"] != "unknown" else None
        if cells and cells < 20:
            insights.append(f"Only {cells} cells -- this is a very small design. Aggressive synthesis optimization (ABC Strategy=speed, Opt Level=3) won't help much.")

        if metrics["clock_type"] == "ideal":
            insights.append("Clock network delay is still IDEAL - CTS was not run or SPEF was not loaded. Run CTS then SPEF before Timing for accurate results.")

        if int(metrics["routing_violations"]) > 0:
            insights.append(f"Routing completed with {metrics['routing_violations']} DRC violations remaining. Reduce Placement Density or increase Die Area.")

    except Exception:
        pass


    error_lines = [l for l in all_logs if any(k in l for k in ["[ERROR", "Error:"])]
    error_text  = "\n".join(error_lines[:30]) if error_lines else "No explicit errors."

    stages_done = list(run_meta.get("stages", {}).keys())
    cell_lib    = run_meta.get("cell_lib", config.get("cell_lib", "sky130_fd_sc_hd"))
    corner      = run_meta.get("corner",   config.get("corner", "tt"))
    stages_str  = ", ".join(stages_done) if stages_done else "none"
    log_tail    = "\n".join(all_logs[-50:])

    system_prompt = (
        "You are an expert ASIC physical design engineer inside RTL Copilot -- a no-code visual ASIC tool. "
        "The user interacts through a GUI with Config panels, NOT a terminal. "
        "NEVER suggest bash commands. ALWAYS reference exact Config panel field names. "
        "Be SPECIFIC to this exact design -- reference the actual numbers from the metrics provided. "
        "Do NOT give generic advice that applies to any design. "
        "Every recommendation must cite a specific number from the design metrics. "
        "Config field names: Cell Library, Corner, Clock Period, ABC Strategy, Opt Level, Flatten, "
        "Die Area, Core Utilization, Core Margin, Density, Cell Padding, Timing Driven, Clock Port, "
        "Clock Uncertainty, Bottom Layer, Top Layer, Congestion Iterations, "
        "VDD Net, VSS Net, Straps Layer, Strap Width, Strap Pitch, Max Slew, Max Cap, Buffer Cells."
    )

    if mode == "error":
        user_message = (
            "RTL Copilot user hit an error at the " + stage + " stage.\n\n"
            "DESIGN: " + (verilog[:400] if verilog else "not provided") + "\n\n"
            "PDK: Sky130A | Library: " + cell_lib + " | Corner: " + corner + "\n"
            "Completed stages: " + stages_str + "\n"
            "Config: " + str(config) + "\n\n"
            "EXTRACTED METRICS:\n" + "\n".join(f"  {k}: {v}" for k, v in metrics.items()) + "\n\n"
            "ERRORS:\n" + error_text + "\n\n"
            "LOG (last 50 lines):\n" + log_tail + "\n\n"
            "Respond with:\n"
            "1. What went wrong -- cite the specific error code and exact numbers\n"
            "2. Root cause -- reference the specific metric that caused it\n"
            "3. Exact fix -- name the Config panel and field, give the specific value to set\n"
            "4. Any Sky130-specific notes"
        )
    elif mode == "qor":
        user_message = (
            "RTL Copilot user completed the " + stage + " stage. Analyze the ACTUAL numbers.\n\n"
            "DESIGN VERILOG:\n" + (verilog[:500] if verilog else "not provided") + "\n\n"
            "PDK: Sky130A | Library: " + cell_lib + " | Corner: " + corner + "\n"
            "Clock period: " + str(config.get("clock_period_ns", 10)) + "ns\n"
            "Completed stages: " + stages_str + "\n\n"
            "EXTRACTED METRICS (use these exact numbers):\n" +
            "\n".join(f"  {k}: {v}" for k, v in metrics.items()) + "\n\n"
            "PRE-COMPUTED INSIGHTS:\n" +
            ("\n".join(f"  - {i}" for i in insights) if insights else "  none") + "\n\n"
            "LOG (last 50 lines):\n" + log_tail + "\n\n"
            "Provide QoR analysis that references the ACTUAL numbers above:\n"
            "1. Tapeout readiness -- cite specific metrics\n"
            "2. Performance headroom -- calculate actual max frequency from slack\n"
            "3. Top 3 specific improvements -- each must reference an actual number from metrics\n"
            "4. Sky130-specific notes for this specific design"
        )
    else:  
        user_message = (
            "RTL Copilot user wants a full optimization guide for their design.\n\n"
            "DESIGN VERILOG:\n" + (verilog[:600] if verilog else "not provided") + "\n\n"
            "PDK: Sky130A | Library: " + cell_lib + " | Corner: " + corner + "\n"
            "Completed stages: " + stages_str + "\n"
            "Full run config: " + str(run_meta) + "\n\n"
            "EXTRACTED METRICS:\n" +
            "\n".join(f"  {k}: {v}" for k, v in metrics.items()) + "\n\n"
            "PRE-COMPUTED INSIGHTS:\n" +
            ("\n".join(f"  - {i}" for i in insights) if insights else "  none") + "\n\n"
            "Provide a design-specific optimization guide. Every point must reference actual numbers.\n"
            "1. Synthesis -- is ABC Strategy / Opt Level worth changing for this specific design?\n"
            "2. Floorplan -- what exact Die Area makes sense given the cell count and utilization?\n"
            "3. Placement -- what Density given current utilization?\n"
            "4. Timing closure -- what Clock Period can this design actually achieve?\n"
            "5. Power -- what is the dominant power component and how to reduce it?\n"
            "Do NOT give generic advice. Every recommendation must cite a specific number."
        )

    try:
        completion = _llm_pd.chat.completions.create(
            model=_byok_model_pd,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.2,
            max_tokens=900,
        )
        reply = completion.choices[0].message.content.strip()
        reply = re.sub(r"```(?:bash|shell|sh|tcl|openroad|python)?[\s\S]*?```", "[Use the RTL Copilot Config panel]", reply)
        if not _byok_pd:
            try:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header.split(" ", 1)[1]
                    sb = _supabase()
                    user_resp = sb.auth.get_user(token)
                    if user_resp and user_resp.user:
                        pass  # auth verified
            except Exception:
                pass
        return {"status": "ok", "reply": reply}
    except Exception:
        _tb.print_exc()
        return {"status": "error", "reply": "AI assistant unavailable. Please try again."}


@app.post("/pd_timing_fix")
async def pd_timing_fix(
    request: Request,
    payload: dict,
):
    """Analyzes timing failures and returns a structured fix plan. Deducts 1 credit."""
    _byok_key_ptf, _provider_ptf, _model_ptf = _extract_user_api_key(request)
    _byok_ptf = bool(_byok_key_ptf)
    _llm_ptf, _byok_model_ptf = _get_llm_client(_byok_key_ptf, _provider_ptf, _model_ptf)

    all_logs_str = str(payload.get("allLogs", ""))[:30000]
    configs      = payload.get("configs", {})
    verilog      = str(payload.get("verilog", ""))[:600]

    wns_m    = re.search(r'wns\s+(?:max\s+)?([\-\d\.]+)', all_logs_str, re.IGNORECASE)
    tns_m    = re.search(r'tns\s+(?:max\s+)?([\-\d\.]+)', all_logs_str, re.IGNORECASE)
    slack_m  = re.search(r'([\-\d\.]+)\s+slack \((MET|VIOLATED)\)', all_logs_str)
    hold_m   = re.search(r'([\-\d\.]+)\s+slack \(VIOLATED\).*?min', all_logs_str, re.DOTALL)
    cells_m  = re.search(r'(\d+)\s+138\.\d+\s+cells', all_logs_str)
    util_m   = re.search(r'Utilization:\s+([\d\.]+)', all_logs_str)

    path_cells = re.findall(r'\+[\d\.]+ns\s+\S+\s+\(sky130_fd_sc_hd__(\w+)\)', all_logs_str)
    comb_depth = len([c for c in path_cells if 'dfxtp' not in c and 'dfrtp' not in c])

    wns       = float(wns_m.group(1))   if wns_m    else None
    tns       = float(tns_m.group(1))   if tns_m    else None
    slack     = float(slack_m.group(1)) if slack_m  else None
    hold_viol = float(hold_m.group(1))  if hold_m   else None
    cells     = int(cells_m.group(1))   if cells_m  else None
    util      = float(util_m.group(1))  if util_m   else None

    clk_period   = float(configs.get("timing", {}).get("clock_period_ns", 10))
    clk_uncert   = float(configs.get("timing", {}).get("clock_uncertainty_ns", 0.1))
    placement_td = configs.get("placement", {}).get("timing_driven", True)
    density      = float(configs.get("placement", {}).get("density", 0.6))

    strategies = []

    if wns is not None and wns < 0:
        violation = abs(wns)

        if slack is not None:
            cp_delay = clk_period + abs(slack) if slack < 0 else clk_period - slack
        else:
            cp_delay = clk_period + violation
        recommended_period = round(cp_delay * 1.15, 1)
        if recommended_period > clk_period:
            strategies.append({
                "type": "relax_clock",
                "priority": 1,
                "description": f"Your critical path takes {cp_delay:.2f}ns but clock period is {clk_period}ns. Relax Clock Period to {recommended_period}ns (15% margin).",
                "config_changes": {
                    "synthesis": {"clock_period_ns": recommended_period},
                    "cts":       {"clock_period_ns": recommended_period},
                    "timing":    {"clock_period_ns": recommended_period},
                },
                "stages_to_rerun": ["synthesis", "placement", "cts", "routing", "spef", "timing"],
                "expected_improvement": f"WNS {wns:.2f}ns -> ~+{recommended_period * 0.1:.2f}ns (MET)",
            })

        if not placement_td and violation < 1.0:
            strategies.append({
                "type": "timing_driven_placement",
                "priority": 2,
                "description": "Timing-driven placement is OFF. Enabling it will place cells to minimize critical path delay.",
                "config_changes": {
                    "placement": {"timing_driven": True},
                },
                "stages_to_rerun": ["placement", "cts", "routing", "spef", "timing"],
                "expected_improvement": f"Typically recovers 0.2-0.5ns. WNS {wns:.2f}ns -> may become MET.",
            })

        if violation < 0.3 and clk_uncert >= 0.1:
            new_uncert = round(clk_uncert * 0.5, 2)
            strategies.append({
                "type": "reduce_uncertainty",
                "priority": 3,
                "description": f"Violation is small ({violation:.2f}ns). Reducing Clock Uncertainty from {clk_uncert}ns to {new_uncert}ns may close timing without re-synthesis.",
                "config_changes": {
                    "timing": {"clock_uncertainty_ns": new_uncert},
                },
                "stages_to_rerun": ["timing"],
                "expected_improvement": f"Recovers {clk_uncert - new_uncert:.2f}ns. WNS {wns:.2f}ns -> ~{wns + (clk_uncert - new_uncert):.2f}ns",
            })

        if comb_depth > 4:
            strategies.append({
                "type": "optimize_synthesis",
                "priority": 4,
                "description": f"Critical path has {comb_depth} combinational cells. Increasing synthesis optimization may reduce logic depth.",
                "config_changes": {
                    "synthesis": {"abc_strategy": "speed", "opt_level": 3},
                },
                "stages_to_rerun": ["synthesis", "placement", "cts", "routing", "spef", "timing"],
                "expected_improvement": "May reduce combinational depth by 1-2 levels, recovering 0.1-0.3ns.",
            })

        if density > 0.7:
            new_density = round(density - 0.15, 2)
            strategies.append({
                "type": "reduce_density",
                "priority": 5,
                "description": f"Placement density is {density} which may cause routing congestion and longer wire delays. Reducing to {new_density}.",
                "config_changes": {
                    "placement": {"density": new_density},
                },
                "stages_to_rerun": ["placement", "cts", "routing", "spef", "timing"],
                "expected_improvement": "Reduces wire delays, typically recovers 0.1-0.2ns on congested designs.",
            })

    elif hold_viol is not None and hold_viol < 0:
        strategies.append({
            "type": "fix_hold",
            "priority": 1,
            "description": f"Hold violation of {hold_viol:.2f}ns. Increasing Clock Uncertainty adds hold margin without affecting setup.",
            "config_changes": {
                "cts":    {"clock_uncertainty_ns": round(clk_uncert + abs(hold_viol) + 0.05, 2)},
                "timing": {"clock_uncertainty_ns": round(clk_uncert + abs(hold_viol) + 0.05, 2)},
            },
            "stages_to_rerun": ["cts", "routing", "spef", "timing"],
            "expected_improvement": f"Hold slack {hold_viol:.2f}ns -> ~+0.05ns (MET)",
        })

    strategies.sort(key=lambda s: s["priority"])
    strategies = strategies[:2]

    if not strategies:
        return {
            "status": "ok",
            "timing_met": True,
            "message": "Timing is already met -- no fixes needed.",
            "strategies": [],
        }

    system_prompt = (
        "You are a senior ASIC physical design engineer. "
        "Explain a timing fix plan in 2-3 sentences. Be direct and specific. "
        "Reference exact numbers. No bullet points."
    )
    user_msg = (
        f"Design has WNS={wns}ns, TNS={tns}ns on a {clk_period}ns clock. "
        f"Combinational depth={comb_depth}, utilization={util}%, cells={cells}. "
        f"Proposed fix: {strategies[0]['description']} "
        f"Expected: {strategies[0]['expected_improvement']}. "
        "Write a 2-sentence explanation of why this will work."
    )

    explanation = ""
    try:
        completion = _llm_ptf.chat.completions.create(
            model=_byok_model_ptf,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=150,
        )
        explanation = completion.choices[0].message.content.strip()
    except Exception:
        explanation = strategies[0]["description"]

    if not _byok_ptf:
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1]
                sb = _supabase()
                user_resp = sb.auth.get_user(token)
                if user_resp and user_resp.user:
                    pass  
        except Exception:
            pass

    return {
        "status": "ok",
        "timing_met": False,
        "wns": wns,
        "tns": tns,
        "clk_period": clk_period,
        "explanation": explanation,
        "strategies": strategies,
    }

@app.post("/pd_chat")
async def pd_chat(
    request: Request,
    payload: dict,
):
    """Conversational PD assistant with full design context. Deducts 1 credit per message."""
    _byok_key_pdc, _provider_pdc, _model_pdc = _extract_user_api_key(request)
    _byok_pdc = bool(_byok_key_pdc)
    _llm_pdc, _byok_model_pdc = _get_llm_client(_byok_key_pdc, _provider_pdc, _model_pdc)
    message         = str(payload.get("message", ""))[:1000]
    history         = payload.get("history", [])[-8:]
    run_meta        = payload.get("run_meta", {})
    verilog         = str(payload.get("verilog", ""))[:600]
    all_logs_str    = str(payload.get("allLogs", ""))[:20000]
    completed       = payload.get("completedStages", [])
    configs         = payload.get("configs", {})

    wns_m   = re.search(r'wns\s+(?:max\s+)?([\-\d\.]+)', all_logs_str, re.IGNORECASE)
    slack_m = re.search(r'([\d\.]+)\s+slack \(MET\)', all_logs_str)
    power_m = re.search(r'Total\s+[\d\.e\+\-]+\s+[\d\.e\+\-]+\s+[\d\.e\+\-]+\s+([\d\.e\+\-]+)', all_logs_str)
    util_m  = re.search(r'Utilization:\s+([\d\.]+)', all_logs_str)
    cells_m = re.search(r'(\d+)\s+138\.\d+\s+cells', all_logs_str)

    metrics_summary = (
        "WNS: " + (wns_m.group(1) + "ns" if wns_m else "unknown") + " | "
        "Slack: " + (slack_m.group(1) + "ns" if slack_m else "unknown") + " | "
        "Power: " + (power_m.group(1) + "W" if power_m else "unknown") + " | "
        "Utilization: " + (util_m.group(1) + "%" if util_m else "unknown") + " | "
        "Cells: " + (cells_m.group(1) if cells_m else "unknown")
    )

    cell_lib = run_meta.get("cell_lib", configs.get("timing", {}).get("cell_lib", "sky130_fd_sc_hd"))
    corner   = run_meta.get("corner",   configs.get("timing", {}).get("corner", "tt"))
    clk_ns   = configs.get("timing", {}).get("clock_period_ns", 10)

    system_prompt = (
        "You are a senior ASIC physical design engineer inside RTL Copilot. "
        "Answer in 2-3 sentences max. No bullet points. No numbered lists. "
        "CRITICAL TIMING RULES: "
        "Positive slack = timing MET (good). Negative slack = timing VIOLATED (bad). "
        "0.77ns slack is POSITIVE = design passes timing. Never say positive slack is a problem. "
        "WNS=0.00 means no violations. Slack (MET) means the path passed. "
        "ONLY reference these exact Config panel fields: "
        "Clock Period, Die Area, Core Utilization, Core Margin, Density, Cell Padding, "
        "Timing Driven, Clock Port, Clock Uncertainty, Bottom Layer, Top Layer, "
        "Congestion Iterations, Antenna Fixing, ABC Strategy, Opt Level, Flatten, "
        "Strap Width, Strap Pitch, Max Slew, Max Cap, Buffer Cells. "
        "NEVER mention Max Fanout, Max Load, Setup Time, Hold Time, retiming, or any field "
        "not in that list. Always cite exact numbers from the design metrics. "
        "Be direct. Never end with a question."
    )
    context = (
        "DESIGN CONTEXT:\n"
        "PDK: Sky130A | Library: " + cell_lib + " | Corner: " + corner + " | Clock: " + str(clk_ns) + "ns\n"
        "Completed stages: " + ", ".join(completed) + "\n"
        "Key metrics: " + metrics_summary + "\n"
    )
    if verilog:
        context += "Verilog: " + verilog + "\n"

    messages = [{"role": "system", "content": system_prompt + "\n\n" + context}]
    for h in history:
        if h.get("role") in ("user", "assistant"):
            messages.append({"role": h["role"], "content": str(h.get("content", ""))})
    messages.append({"role": "user", "content": message})

    try:
        completion = _llm_pdc.chat.completions.create(
            model=_byok_model_pdc,
            messages=messages,
            temperature=0.3,
            max_tokens=300,
        )
        reply = completion.choices[0].message.content.strip()

        if not _byok_pdc:
            try:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header.split(" ", 1)[1]
                    sb = _supabase()
                    user_resp = sb.auth.get_user(token)
                    if user_resp and user_resp.user:
                        pass  # auth verified
            except Exception:
                pass

        return {"status": "ok", "reply": reply}
    except Exception:
        _tb.print_exc()
        return {"status": "error", "reply": "AI assistant unavailable. Please try again."}

@app.post("/feedback")
async def submit_feedback(payload: FeedbackRequest):
    try:
        sb = _supabase()
        sb.table("feedback").insert({
            "rating":   payload.rating,
            "text":     payload.text or "",
            "trigger":  payload.trigger or "",
            "user_id":  payload.user_id,
        }).execute()
        return {"status": "ok"}
    except RuntimeError as e:
        print(f"Feedback not stored: {e}")
        return {"status": "ok"}
    except Exception:
        _tb.print_exc()
        return {"status": "ok"}


def _detect_pattern(payload_inputs, payload_outputs, payload_internal, payload_behaviour):
    """
    Detects which pattern best fits the user's description.
    Returns "counter_based" | "combinational" | "register_based" | "shift_based" | "unsupported"
    """
    behaviour_lower = payload_behaviour.lower()
    has_internal    = len(payload_internal) > 0

    shift_keywords = ["shift", "lfsr", "delay line", "serial", "pipeline stage",
                      "scramble", "descramble", "crc", "tap", "feedback", "stages",
                      "shift register", "serial to parallel", "parallel to serial"]
    if any(kw in behaviour_lower for kw in shift_keywords):
        return "shift_based"

    counter_keywords = ["counter", "count up", "count down", "counts up", "counts down",
                        "pwm", "period", "duty cycle", "watchdog", "timeout", "baud",
                        "clock divider", "frequency", "pulse width", "cycles"]
    if any(kw in behaviour_lower for kw in counter_keywords) or has_internal:
        return "counter_based"

    register_keywords = ["accumulate", "accumulator", "store", "register", "latch",
                         "sample and hold", "peak", "running", "average", "pipeline",
                         "hold", "capture", "enable"]
    if any(kw in behaviour_lower for kw in register_keywords):
        return "register_based"

    comb_keywords = ["compar", "add", "subtract", "multiply", "logic", "bitwise",
                     "xor", "and", "or", "not", "invert", "encode", "decode",
                     "select", "mux", "saturat", "clamp", "threshold", "mask",
                     "parity", "sum", "difference", "output depends", "function of"]
    if any(kw in behaviour_lower for kw in comb_keywords):
        return "combinational"

    return "unsupported"




@app.post("/generate_custom_block")
@limiter.limit("20/minute")
async def generate_custom_block(
    request: Request,
    payload: CustomBlockRequest,
    current_user: str = Depends(_get_current_user)
):
    """
    Takes the structured form input from the custom block modal.
    1. Detects pattern (counter / combinational / register)
    2. AI maps it to a strict schema using pattern-specific prompt
    3. Deterministic emit script generates Verilog
    4. iverilog -tnull validates syntax
    5. Returns schema + Verilog to frontend
    """
    try:
        pattern = _detect_pattern(
            payload.inputs,
            payload.outputs,
            payload.internal_signals,
            payload.behaviour
        )

        if pattern == "unsupported":
            return {
                "status": "unsupported",
                "error": (
                    f"The block '{payload.name}' doesn't match any of our supported "
                    f"patterns (counter-based, combinational, register-based, shift-based). "
                    f"This could be a complex arithmetic pipeline, a full protocol controller, "
                    f"or a multi-pattern block. Please send us feedback and we'll consider "
                    f"adding support."
                ),
                "block_description": f"{payload.name}: {payload.behaviour[:200]}",
            }

        prompt_map = {
            "counter_based":  _CUSTOM_BLOCK_SCHEMA_COUNTER,
            "combinational":  _CUSTOM_BLOCK_SCHEMA_COMB,
            "register_based": _CUSTOM_BLOCK_SCHEMA_REGISTER,
            "shift_based":    _CUSTOM_BLOCK_SCHEMA_SHIFT,
        }
        system_prompt = prompt_map[pattern]

        user_message = f"""
Block name: {payload.name}
Description: {payload.description}

Inputs:
{chr(10).join(f"  - {p.get('name','?')} width={p.get('width','8')} -- {p.get('description','')}" for p in payload.inputs)}

Outputs:
{chr(10).join(f"  - {p.get('name','?')} width={p.get('width','1')} -- {p.get('description','')}" for p in payload.outputs)}

Internal signals:
{chr(10).join(f"  - {s.get('name','?')} width={s.get('width','8')} -- {s.get('description','')}" for s in payload.internal_signals) or "  none specified"}

Behaviour:
{payload.behaviour}

Output the JSON schema now:
"""

        completion = _llm_client.chat.completions.create(
            model=_LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.0,
            max_tokens=1500,
        )
        raw = completion.choices[0].message.content.strip()

        json_str = None
        if "```json" in raw:
            s = raw.find("```json") + 7
            e = raw.find("```", s)
            json_str = raw[s:e].strip()
        elif "```" in raw:
            s = raw.find("```") + 3
            e = raw.rfind("```")
            json_str = raw[s:e].strip()
        elif "{" in raw:
            depth, start, end = 0, raw.find("{"), -1
            for ci, ch in enumerate(raw[start:], start):
                if ch == "{": depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0: end = ci; break
            if end != -1:
                json_str = raw[start:end+1]

        if not json_str:
            return {"status": "error", "error": "AI could not produce a valid schema. Try simplifying your description."}

        schema = json.loads(json_str)

        if not schema.get("name"):
            return {"status": "error", "error": "Schema missing block name."}
        if not schema.get("ports"):
            return {"status": "error", "error": "Schema missing ports."}

        schema["name"] = re.sub(r'[^a-zA-Z0-9_]', '_', schema["name"].strip())

        detected_pattern = schema.get("pattern", pattern)
        if detected_pattern == "combinational":
            from emit_custom_comb import emit_custom_comb
            verilog = emit_custom_comb(schema)
        elif detected_pattern == "register_based":
            from emit_custom_register import emit_custom_register
            verilog = emit_custom_register(schema)
        elif detected_pattern == "shift_based":
            from emit_custom_shift import emit_custom_shift
            verilog = emit_custom_shift(schema)
        else:
            from emit_custom_counter import emit_custom_counter
            verilog = emit_custom_counter(schema)

        syntax_ok    = False
        syntax_error = ""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                vf = Path(tmpdir) / f"{schema['name']}.v"
                vf.write_text(verilog)
                cr = subprocess.run(
                    ["iverilog", "-tnull", str(vf)],
                    capture_output=True, text=True, cwd=str(tmpdir)
                )
                if cr.returncode == 0:
                    syntax_ok = True
                else:
                    syntax_error = cr.stderr.strip()
        except Exception:
            syntax_error = "iverilog not available for syntax check"
            syntax_ok    = True   

        if not syntax_ok:
            _tb.print_exc()
            return {
                "status": "error",
                "error": f"Generated Verilog has a syntax error: {syntax_error}"
            }

        return {
            "status":   "ok",
            "schema":   schema,
            "verilog":  verilog,
            "pattern":  detected_pattern,
        }

    except json.JSONDecodeError:
        return {"status": "error", "error": "AI returned malformed schema. Please try again."}
    except Exception:
        _tb.print_exc()
        return {"status": "error", "error": "Internal error generating custom block."}




@app.post('/custom_blocks')
@limiter.limit('30/minute')
async def save_custom_block(
    request: Request,
    payload: SaveCustomBlockRequest,
    current_user: str = Depends(_get_current_user)
):
    """Save a verified custom block to the user's library."""
    if _OFFLINE_MODE:
        import uuid, datetime
        db = _local_db_read()
        bid = str(uuid.uuid4())
        block = {"id": bid, "user_id": "local_user", "name": payload.name,
                 "description": payload.description, "schema": payload.block_schema,
                 "verilog": payload.verilog, "ports": payload.ports,
                 "block_type": payload.block_type,
                 "created_at": datetime.datetime.utcnow().isoformat()}
        db.setdefault("custom_blocks", {})[bid] = block
        _local_db_write(db)
        return {"status": "ok", "id": bid}
    try:
        sb  = _supabase()
        row = {
            'user_id':     current_user,
            'name':        payload.name,
            'description': payload.description,
            'schema':      payload.block_schema,
            'verilog':     payload.verilog,
            'ports':       payload.ports,
            'block_type':  payload.block_type,
        }
        res = sb.table('custom_blocks').insert(row).execute()
        if not res.data:
            return {'status': 'error', 'error': 'Failed to save block.'}
        return {'status': 'ok', 'id': res.data[0]['id']}
    except Exception:
        _tb.print_exc()
        return {'status': 'error', 'error': 'Internal error saving block.'}


@app.get('/custom_blocks')
@limiter.limit('60/minute')
async def get_custom_blocks(
    request: Request,
    current_user: str = Depends(_get_current_user)
):
    """Fetch all custom blocks for the current user."""
    if _OFFLINE_MODE:
        db = _local_db_read()
        blocks = list(db.get("custom_blocks", {}).values())
        blocks.sort(key=lambda b: b.get("created_at", ""), reverse=True)
        lite = [{"id": b["id"], "name": b["name"], "description": b.get("description",""),
                 "ports": b["ports"], "block_type": b["block_type"],
                 "created_at": b["created_at"]} for b in blocks]
        return {"status": "ok", "blocks": lite}
    try:
        sb  = _supabase()
        res = (sb.table('custom_blocks')
                 .select('id, name, description, ports, block_type, created_at')
                 .eq('user_id', current_user)
                 .order('created_at', desc=True)
                 .execute())
        return {'status': 'ok', 'blocks': res.data or []}
    except Exception:
        _tb.print_exc()
        return {'status': 'ok', 'blocks': []}


@app.delete('/custom_blocks/{block_id}')
@limiter.limit('30/minute')
async def delete_custom_block(
    request: Request,
    block_id: str,
    current_user: str = Depends(_get_current_user)
):
    """Delete a custom block (only if owned by current user)."""
    if _OFFLINE_MODE:
        db = _local_db_read()
        if block_id in db.get("custom_blocks", {}):
            del db["custom_blocks"][block_id]
            _local_db_write(db)
        return {"status": "ok"}
    try:
        sb = _supabase()
        (sb.table('custom_blocks')
           .delete()
           .eq('id', block_id)
           .eq('user_id', current_user)
           .execute())
        return {'status': 'ok'}
    except Exception:
        _tb.print_exc()
        return {'status': 'error', 'error': 'Failed to delete block.'}


@app.get('/custom_blocks/{block_id}/full')
@limiter.limit('60/minute')
async def get_custom_block_full(
    request: Request,
    block_id: str,
    current_user: str = Depends(_get_current_user)
):
    """Fetch a single custom block including its full verilog source."""
    if _OFFLINE_MODE:
        db = _local_db_read()
        block = db.get("custom_blocks", {}).get(block_id)
        if not block:
            return {"status": "error", "error": "Block not found."}
        return {"status": "ok", **block}
    try:
        sb  = _supabase()
        res = (sb.table('custom_blocks')
                 .select('id, name, description, ports, block_type, schema, verilog, created_at')
                 .eq('id', block_id)
                 .eq('user_id', current_user)
                 .single()
                 .execute())
        if not res.data:
            return {'status': 'error', 'error': 'Block not found.'}
        return {'status': 'ok', **res.data}
    except Exception:
        _tb.print_exc()
        return {'status': 'error', 'error': 'Failed to fetch block.'}
@app.post("/simulate")
async def simulate_design(payload: SimulateRequest):
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            p       = Path(tmpdir)
            tb_file = p / "testbench.v"
            vcd     = p / "simulation.vcd"

            with open(tb_file, "w") as f: f.write(payload.testbench)

            srcs = payload.verilog_files if payload.verilog_files else {"top.v": payload.verilog}
            dfiles = []
            for fname, code in srcs.items():
                fp = p / fname
                with open(fp, "w") as f: f.write(code)
                dfiles.append(str(fp))

            cr = subprocess.run(
                ["iverilog", "-o", str(p/"sim")] + dfiles + [str(tb_file)],
                capture_output=True, text=True, cwd=str(p)
            )
            if cr.returncode != 0:
                return {"status":"error","error":"Compilation failed","details":cr.stderr}

            sr = subprocess.run(["vvp", str(p/"sim")],
                                 capture_output=True, text=True, cwd=str(p), timeout=10)
            if sr.returncode != 0:
                return {"status":"error","error":"Simulation failed","details":sr.stderr}

            if not vcd.exists():
                return {"status":"error","error":"No VCD generated",
                        "details":"Testbench missing $dumpfile/$dumpvars"}

            vcd_txt = vcd.read_text()
            return {"status":"success","console_output":sr.stdout,
                    "waveform":_parse_vcd(vcd_txt),"vcd_raw":vcd_txt}

    except subprocess.TimeoutExpired:
        return {"status":"error","error":"Timeout (>10s)","details":"Possible infinite loop"}
    except Exception:
        return {"status":"error","error":"Unexpected error","details":_tb.format_exc()}


def _parse_vcd(vcd: str) -> dict:
    timescale, signals, cur_t, tvals = "1ns", {}, 0, {}
    for line in vcd.split("\n"):
        line = line.strip()
        if line.startswith("$timescale"):
            m = re.search(r'(\d+\s*[a-z]+)', line)
            if m: timescale = m.group(1).strip()
        elif line.startswith("$var"):
            p = line.split()
            if len(p) >= 5:
                signals[p[3]] = {"name":p[4],"type":p[1],"width":int(p[2]),"values":[]}
        elif line.startswith("#"):
            cur_t = int(line[1:]); tvals.setdefault(cur_t, {})
        elif line and not line.startswith("$"):
            if len(line) >= 2 and line[0] in "01xz":
                sym = line[1:]
                if sym in signals: tvals.setdefault(cur_t,{})[sym] = line[0]
            elif line.startswith("b"):
                p = line.split()
                if len(p) >= 2 and p[1] in signals:
                    tvals.setdefault(cur_t,{})[p[1]] = p[0][1:]
    cur = {s: None for s in signals}
    for t in sorted(tvals):
        cur.update(tvals[t])
        for sym, val in cur.items():
            if val is not None:
                signals[sym]["values"].append({"time":t,"value":val})
    return {"timescale": timescale, "signals": list(signals.values())}


_ALLOWED_EDIT_TYPES = {
    "change_node_width",     # change data.width of a node
    "change_config_value",   # change a config field in customSchema.config
    "change_edge_condition", # change FSM transition condition string
    "change_node_op",        # change comb op (add/sub/mul/and/or/xor etc.)
    "change_node_value",     # change const node value
}



def _run_simulation_internal(ir: dict, stimulus: dict, verilog_files: dict) -> dict:
    """
    Generates testbench deterministically via emit_testbench.py then simulates.
    Returns sim result dict with status, testbench, console_output, pass_count, fail_count.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", dir=str(CODEGEN_DIR),
        delete=False, encoding="utf-8"
    ) as tf:
        json.dump({"ir": ir, "stimulus": stimulus}, tf, indent=2)
        tb_path = tf.name

    try:
        tb_result = subprocess.run(
            ["python", str(TB_SCRIPT), tb_path],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(CODEGEN_DIR)
        )
    finally:
        Path(tb_path).unlink(missing_ok=True)

    if tb_result.returncode != 0 or not tb_result.stdout.strip():
        return {"status": "error", "error": "Testbench generation failed",
                "details": tb_result.stderr}

    testbench = tb_result.stdout

    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        (p / "testbench.v").write_text(testbench)
        for fname, code in verilog_files.items():
            (p / fname).write_text(code)
        dfiles = [str(p / fname) for fname in verilog_files]

        cr = subprocess.run(
            ["iverilog", "-o", str(p / "sim")] + dfiles + [str(p / "testbench.v")],
            capture_output=True, text=True, cwd=str(p)
        )
        if cr.returncode != 0:
            return {"status": "error", "error": "Compilation failed",
                    "details": cr.stderr, "testbench": testbench}

        sr = subprocess.run(["vvp", str(p / "sim")],
                            capture_output=True, text=True, cwd=str(p), timeout=30)

        console    = sr.stdout
        pass_count = 0
        fail_count = 0
        for line in console.split("\n"):
            m = re.search(r'===.*?(\d+)\s*PASS\s+(\d+)\s*FAIL', line)
            if m:
                pass_count = int(m.group(1))
                fail_count = int(m.group(2))
                break

        return {
            "status":         "ok",
            "testbench":      testbench,
            "console_output": console,
            "pass_count":     pass_count,
            "fail_count":     fail_count,
        }


def _analyze_failures(console_output: str) -> list:
    """Parses console output for FAIL lines into structured dicts."""
    failures = []
    for line in console_output.split("\n"):
        line = line.strip()
        if "[FAIL]" in line or "FAIL:" in line:
            entry = {"raw": line, "signal": "", "expected": "", "actual": ""}
            m = re.search(
                r'\[FAIL\]\s*(\w+)[:\s]+expected\s+(\S+)[,\s]+got\s+(\S+)',
                line, re.IGNORECASE
            )
            if not m:
                # Fallback: FAIL: signal expected X got Y
                m = re.search(
                    r'FAIL[:\s]+(\w+)[:\s]+expected\s+(\S+)[,\s]+got\s+(\S+)',
                    line, re.IGNORECASE
                )
            if m:
                entry["signal"]   = m.group(1)
                entry["expected"] = m.group(2)
                entry["actual"]   = m.group(3)
            failures.append(entry)
    return failures


def _build_ir_summary(ir: dict) -> dict:
    """Builds a concise IR summary -- block types, config, connections."""
    summary_nodes = []
    for n in ir.get("nodes", []):
        node_entry = {
            "id":    n.get("id", ""),
            "type":  n.get("type", ""),
            "name":  n.get("name", ""),
            "width": n.get("width", ""),
        }
        if n.get("type") == "custom_block":
            schema = n.get("customSchema", {})
            node_entry["pattern"] = schema.get("pattern", "")
            node_entry["config"]  = schema.get("config", {})
            node_entry["ports"]   = n.get("customPorts", [])
        if n.get("type") == "comb":
            node_entry["op"] = n.get("op", "")
        if n.get("type") == "const":
            node_entry["value"] = n.get("value", "0")
        summary_nodes.append(node_entry)

    return {
        "nodes": summary_nodes,
        "edges": [
            {"src": e.get("src",""), "src_port": e.get("src_port",""),
             "dst": e.get("dst",""), "dst_port": e.get("dst_port","")}
            for e in ir.get("edges", [])
        ],
        "ports": ir.get("ports", []),
    }


def _apply_ir_edits(ir: dict, edits: list) -> tuple[dict, list]:
    """Applies validated IR edits deterministically. Returns (updated_ir, log)."""
    import copy
    updated_ir  = copy.deepcopy(ir)
    applied_log = []
    node_map    = {n["id"]: n for n in updated_ir.get("nodes", [])}

    for edit in edits:
        edit_type = edit.get("type", "")
        node_id   = edit.get("node_id", "")
        field     = edit.get("field", "")
        new_value = edit.get("new_value", "")
        old_value = edit.get("old_value", "")

        if edit_type not in _ALLOWED_EDIT_TYPES:
            continue
        if node_id not in node_map:
            continue

        node = node_map[node_id]

        if edit_type == "change_node_width":
            try:
                w = int(new_value)
                assert 1 <= w <= 128
            except Exception:
                continue
            node["width"] = str(w)
            applied_log.append(f"Changed {node_id}.width: {old_value} -> {new_value}")

        elif edit_type == "change_config_value":
            if node.get("type") == "custom_block":
                config = node.get("customSchema", {}).get("config", {})
                if field in config:
                    config[field] = new_value
                    applied_log.append(f"Changed {node_id}.config.{field}: {old_value} -> {new_value}")

        elif edit_type == "change_edge_condition":
            for e in updated_ir.get("edges", []):
                if e.get("src") == node_id and e.get("condition") == old_value:
                    if re.match(r'^[\w\s=!<>&|^~()0-9\']+$', new_value):
                        e["condition"] = new_value
                        applied_log.append(f"Changed edge {node_id}->{e.get('dst')} condition: {old_value} -> {new_value}")

        elif edit_type == "change_node_op":
            valid_ops = {"add","sub","mul","and","or","xor","not","buf","eq","gt","lt"}
            if new_value in valid_ops and node.get("type") == "comb":
                node["op"] = new_value
                applied_log.append(f"Changed {node_id}.op: {old_value} -> {new_value}")

        elif edit_type == "change_node_value":
            try:
                int(new_value)
                node["value"] = new_value
                applied_log.append(f"Changed {node_id}.value: {old_value} -> {new_value}")
            except ValueError:
                continue

    return updated_ir, applied_log




@app.post("/ai_verify")
@limiter.limit("6/minute")
async def ai_verify(
    request: Request,
    payload: VerifyRequest,
    current_user: str = Depends(_get_current_user)
):
    """
    Verification agent -- deterministic flow:
    1. Generate testbench from user's stimulus (emit_testbench.py)
    2. Run simulation (iverilog + vvp)
    3. LLM analyzes: reads IR summary + RTL + testbench + failures
       -> produces plain English summary + constrained IR edits
    4. Apply edits -> regenerate RTL -> re-simulate (max 2 more times)
    """
    user_api_key, user_provider, user_model = _extract_user_api_key(request)
    byok = bool(user_api_key)
    _verify_llm, _verify_model = _get_llm_client(user_api_key, user_provider, user_model)


    ir             = payload.ir
    verilog_files  = payload.verilog_files
    stimulus       = payload.stimulus
    design_intent  = (payload.design_intent or "").strip()
    steps          = stimulus.get("steps", [])

    has_assertions = any(
        step.get("expected") and any(str(v).strip() for v in step["expected"].values())
        for step in steps
    )
    if not has_assertions:
        return {
            "status": "no_assertions",
            "summary": "No expected output values found. Fill in the green OK columns in the Stimulus tab with expected output values, then click Verify.",
            "verdict": "error",
            "pass_count": 0,
            "fail_count": 0,
            "iterations": [],
        }

    if not verilog_files:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", dir=str(CODEGEN_DIR),
            delete=False, encoding="utf-8"
        ) as tf:
            json.dump(ir, tf, indent=2)
            ir_path = tf.name
        try:
            vg = subprocess.run(
                ["python", str(EMIT_SCRIPT), ir_path],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=str(CODEGEN_DIR)
            )
        finally:
            Path(ir_path).unlink(missing_ok=True)

        print(f"[V2] iverilog stderr: {vg.stderr}", flush=True)
        if vg.returncode != 0:
            return {"status": "error", "error": "RTL generation failed", "details": vg.stderr}
        try:
            verilog_files = json.loads(vg.stdout)
        except Exception:
            verilog_files = {"top.v": vg.stdout}

    iterations    = []
    current_ir    = ir
    current_files = verilog_files
    final_verdict = "fail"
    final_pass    = 0
    final_fail    = 0
    MAX_ITER      = 2

    for iteration in range(MAX_ITER):

        sim = _run_simulation_internal(current_ir, stimulus, current_files)

        if sim["status"] == "error":
            iterations.append({
                "iteration": iteration + 1,
                "status":    "error",
                "error":     sim.get("error", ""),
                "details":   sim.get("details", ""),
            })
            break

        pass_count = sim["pass_count"]
        fail_count = sim["fail_count"]
        console    = sim["console_output"]
        testbench  = sim["testbench"]

        iter_log = {
            "iteration":       iteration + 1,
            "pass_count":      pass_count,
            "fail_count":      fail_count,
            "console":         console,
            "testbench":       testbench,
            "edits_applied":   [],
            "llm_summary":     "",
            "llm_diagnosis":   "",
        }

        final_pass = pass_count
        final_fail = fail_count

        if fail_count == 0 and pass_count > 0:
            final_verdict = "pass"
            iterations.append(iter_log)
            break

        failures   = _analyze_failures(console)
        ir_summary = _build_ir_summary(current_ir)

        rtl_str = "\n\n".join(
            f"// {fname}\n{code[:3000]}"
            for fname, code in current_files.items()
        )

        prev_summary = ""
        if iterations:
            prev_summary = "PREVIOUS ITERATIONS:\n"
            for prev in iterations:
                prev_summary += f"  Iteration {prev['iteration']}: {prev['pass_count']} pass, {prev['fail_count']} fail"
                if prev.get("edits_applied"):
                    prev_summary += f" -- edits applied: {prev['edits_applied']}"
                if prev.get("issue_type"):
                    prev_summary += f" -- classified as: {prev['issue_type']}"
                prev_summary += "\n"

        llm_input = f"""
DESIGN INTENT: {design_intent if design_intent else "(not provided)"}

IR SUMMARY:
{json.dumps(ir_summary, indent=2)}

GENERATED RTL (read only):
{rtl_str}

TESTBENCH (read only):
{testbench[:2000]}

CONSOLE OUTPUT:
{console[:1500]}

FAILURES:
{json.dumps(failures, indent=2)}

PASS COUNT: {pass_count}
FAIL COUNT: {fail_count}

{prev_summary}
"""

        try:
            completion = _verify_llm.chat.completions.create(
                model=_verify_model,
                messages=[
                    {"role": "system", "content": _VERIFY_SYSTEM_PROMPT},
                    {"role": "user",   "content": llm_input},
                ],
                temperature=0.0,
                max_tokens=1000,
                timeout=30,
            )
            raw = completion.choices[0].message.content.strip()

            json_str = None
            if "{" in raw:
                depth, start, end = 0, raw.find("{"), -1
                for ci, ch in enumerate(raw[start:], start):
                    if ch == "{": depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0: end = ci; break
                if end != -1:
                    json_str = raw[start:end+1]

            if json_str:
                llm_resp     = json.loads(json_str)
                issue_type   = llm_resp.get("issue_type", "circuit_bug")
                next_action  = llm_resp.get("next_action", "")
                targeted     = llm_resp.get("targeted_steps", [])
                iter_log["llm_summary"]    = llm_resp.get("summary", "")
                iter_log["llm_diagnosis"]  = llm_resp.get("diagnosis", "")
                iter_log["issue_type"]     = issue_type
                iter_log["next_action"]    = next_action
                iter_log["targeted_steps"] = targeted
                # Only apply edits for actual circuit bugs
                edits = llm_resp.get("edits", []) if issue_type == "circuit_bug" else []
            else:
                edits        = []
                issue_type   = "unknown"
                next_action  = ""
                targeted     = []

        except Exception:
            _tb.print_exc()
            edits       = []
            issue_type  = "unknown"
            next_action = ""
            targeted    = []

        iterations.append(iter_log)

        if len(iterations) >= 2:
            prev = iterations[-2]
            same_counts  = (prev["pass_count"] == pass_count and prev["fail_count"] == fail_count)
            no_prev_edits = not prev.get("edits_applied")
            if same_counts and no_prev_edits:
                break

        if iteration == MAX_ITER - 1 or not edits:
            break

        if targeted and isinstance(targeted, list):
            validated_targeted = []
            for ts in targeted[:3]:  # max 3 targeted steps
                if isinstance(ts, dict) and "values" in ts:
                    ts["_auto"] = True
                    ts.setdefault("label", f"targeted_{len(validated_targeted)}")
                    ts.setdefault("time", (len(steps) + len(validated_targeted)) * 100)
                    validated_targeted.append(ts)
            if validated_targeted:
                stimulus = dict(stimulus)
                stimulus["steps"] = steps + validated_targeted

        updated_ir, applied_log = _apply_ir_edits(current_ir, edits)
        iter_log["edits_applied"] = applied_log

        if not applied_log:
            break

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", dir=str(CODEGEN_DIR),
            delete=False, encoding="utf-8"
        ) as tf:
            json.dump(updated_ir, tf, indent=2)
            ir_path = tf.name
        try:
            vg = subprocess.run(
                ["python", str(EMIT_SCRIPT), ir_path],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=str(CODEGEN_DIR)
            )
        finally:
            Path(ir_path).unlink(missing_ok=True)

        print(f"[V2] iverilog stderr: {vg.stderr}", flush=True)
        if vg.returncode != 0:
            break

        try:
            current_files = json.loads(vg.stdout)
        except Exception:
            break

        current_ir = updated_ir

    last        = iterations[-1] if iterations else {}
    summary     = last.get("llm_summary", "")
    diagnosis   = last.get("llm_diagnosis", "")
    issue_type  = last.get("issue_type", "")
    next_action = last.get("next_action", "")
    all_edits   = [e for it in iterations for e in it.get("edits_applied", [])]

    if not summary:
        if final_verdict == "pass":
            summary = f"All {final_pass} assertion(s) passed."
        else:
            summary = f"{final_fail} assertion(s) failed after {len(iterations)} iteration(s)."
        if diagnosis:
            summary += f" {diagnosis}"

    return {
        "status":        "ok",
        "verdict":       final_verdict,
        "pass_count":    final_pass,
        "fail_count":    final_fail,
        "summary":       summary,
        "issue_type":    issue_type,
        "next_action":   next_action,
        "iterations":    iterations,
        "edits_applied": all_edits,
        "final_verilog": current_files,
    }


def _llm_understand_circuit(ir: dict, llm=None, model=None) -> dict:
    """
    LLM Call 1 -- reads IR, understands the circuit, suggests test cases.
    Returns structured understanding dict.
    """
    if llm is None:
        if _llm_client is None:
            raise HTTPException(status_code=403, detail={"code": "byok_required", "message": "No API key set. Please enter your API key in Settings."})
        llm = _llm_client
    if model is None: model = _LLM_MODEL
    ir_summary = _build_ir_summary(ir)
    ports      = ir.get("ports", [])

    llm_input = f"""
CIRCUIT IR SUMMARY:
{json.dumps(ir_summary, indent=2)}

TOP-LEVEL PORTS:
{json.dumps(ports, indent=2)}
"""

    try:
        completion = llm.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _AUTO_VERIFY_UNDERSTAND_PROMPT},
                {"role": "user",   "content": llm_input},
            ],
            temperature=0.0,
            max_tokens=1500,
            timeout=30,
        )
        raw = completion.choices[0].message.content.strip()
        if "```" in raw:
            s = raw.find("{")
            e = raw.rfind("}") + 1
            raw = raw[s:e]
        return json.loads(raw)
    except Exception:
        _tb.print_exc()
        return {}


def _llm_interpret_results(
    understanding: dict,
    test_plan: dict,
    console: str,
    failures: list,
    pass_count: int,
    fail_count: int,
    iteration_history: list,
) -> dict:
    """
    LLM Call 2 -- interprets simulation results given circuit understanding.
    Returns verdict, findings, follow-up tests.
    """
    prev_summary = ""
    if iteration_history:
        prev_summary = "PREVIOUS ITERATIONS:\n"
        for prev in iteration_history:
            prev_summary += (
                f"  Iter {prev['iteration']}: "
                f"{prev['pass_count']} pass, {prev['fail_count']} fail"
                f" -- verdict: {prev.get('verdict', 'unknown')}\n"
            )

    llm_input = f"""
CIRCUIT UNDERSTANDING:
{json.dumps(understanding, indent=2)}

TEST PLAN EXECUTED:
  Strategy:    {test_plan.get('strategy', 'unknown')}
  Description: {test_plan.get('description', '')}
  Total tests: {test_plan.get('test_count', 0)}
  With assertions: {test_plan.get('assert_count', 0)}

SIMULATION RESULTS:
  PASS: {pass_count}
  FAIL: {fail_count}

CONSOLE OUTPUT:
{console[:2000]}

FAILURES:
{json.dumps(failures, indent=2)}

{prev_summary}
"""

    try:
        completion = _auto_verify_llm.chat.completions.create(
            model=_auto_verify_model,
            messages=[
                {"role": "system", "content": _AUTO_VERIFY_INTERPRET_PROMPT},
                {"role": "user",   "content": llm_input},
            ],
            temperature=0.0,
            max_tokens=1200,
            timeout=30,
        )
        raw = completion.choices[0].message.content.strip()
        if "```" in raw:
            s = raw.find("{")
            e = raw.rfind("}") + 1
            raw = raw[s:e]
        return json.loads(raw)
    except Exception:
        _tb.print_exc()
        return {
            "verdict":    "inconclusive",
            "confidence": "low",
            "summary":    "Could not interpret results.",
            "findings":   [],
            "follow_up_tests": [],
        }


@app.post("/ai_auto_verify")
@limiter.limit("4/minute")
async def ai_auto_verify(
    request: Request,
    payload: AutoVerifyRequest,
    current_user: str = Depends(_get_current_user)
):
    """
    Autonomous verification agent -- completely separate from user's
    stimulus/testbench flow.

    The agent:
    1. Reads the IR and understands the circuit (LLM Call 1)
    2. Generates its own test plan via the semantic library
    3. Runs simulation using the deterministic testbench generator
    4. Interprets results (LLM Call 2)
    5. If failures found, generates targeted follow-up tests and loops
       (max 3 iterations total)
    6. Returns a comprehensive verdict with findings
    """
    user_api_key, user_provider, user_model = _extract_user_api_key(request)
    byok = bool(user_api_key)
    _auto_verify_llm, _auto_verify_model = _get_llm_client(user_api_key, user_provider, user_model)


    ir            = payload.ir
    verilog_files = payload.verilog_files

    if not verilog_files:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", dir=str(CODEGEN_DIR),
            delete=False, encoding="utf-8"
        ) as tf:
            json.dump(ir, tf, indent=2)
            ir_path = tf.name
        try:
            vg = subprocess.run(
                ["python", str(EMIT_SCRIPT), ir_path],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=str(CODEGEN_DIR)
            )
        finally:
            Path(ir_path).unlink(missing_ok=True)

        print(f"[V2] iverilog stderr: {vg.stderr}", flush=True)
        if vg.returncode != 0:
            return {"status": "error",
                    "error": "RTL generation failed", "details": vg.stderr}
        try:
            verilog_files = json.loads(vg.stdout)
        except Exception:
            verilog_files = {"top.v": vg.stdout}

    understanding = _llm_understand_circuit(ir)

    test_plan = generate_test_plan(ir, llm_understanding=understanding)

    if test_plan["test_count"] == 0:
        return {
            "status":  "error",
            "error":   "Could not generate test cases for this circuit.",
            "details": "The circuit may be too complex or have unrecognised block types.",
        }

    iterations    = []
    current_files = verilog_files
    current_steps = test_plan["steps"]
    final_verdict = "inconclusive"
    MAX_ITER      = 3

    for iteration in range(MAX_ITER):

        stimulus = {
            "steps":          current_steps,
            "reset_type":     test_plan["reset_type"],
            "reset_active":   test_plan["reset_active"],
            "use_corner_cases": False,
            "use_random":     False,
            "sim_duration_ns": max(2000, len(current_steps) * 50),
        }

        sim = _run_simulation_internal(ir, stimulus, current_files)

        if sim["status"] == "error":
            iterations.append({
                "iteration":  iteration + 1,
                "status":     "error",
                "error":      sim.get("error", ""),
                "details":    sim.get("details", ""),
            })
            break

        pass_count = sim["pass_count"]
        fail_count = sim["fail_count"]
        console    = sim["console_output"]
        testbench  = sim["testbench"]
        failures   = _analyze_failures(console)

        # Interpret results
        interpretation = _llm_interpret_results(
            understanding, test_plan, console,
            failures, pass_count, fail_count, iterations
        )

        verdict    = interpretation.get("verdict", "inconclusive")
        confidence = interpretation.get("confidence", "low")
        summary    = interpretation.get("summary", "")
        findings   = interpretation.get("findings", [])
        follow_ups = interpretation.get("follow_up_tests", [])

        iter_log = {
            "iteration":      iteration + 1,
            "pass_count":     pass_count,
            "fail_count":     fail_count,
            "console":        console,
            "testbench":      testbench,
            "verdict":        verdict,
            "confidence":     confidence,
            "summary":        summary,
            "findings":       findings,
            "tests_run":      len(current_steps),
            "asserted":       sum(1 for s in current_steps if s.get("expected")),
        }
        iterations.append(iter_log)

        if verdict == "correct":
            final_verdict = "correct"
            break

        if not follow_ups or iteration == MAX_ITER - 1:
            final_verdict = verdict
            break


        if len(iterations) >= 2:
            prev = iterations[-2]
            if (prev["pass_count"] == pass_count and
                    prev["fail_count"] == fail_count):
                final_verdict = verdict
                break

        validated_followups = []
        for fu in follow_ups[:3]:
            if isinstance(fu, dict) and "inputs" in fu:
                validated_followups.append({
                    "label":    fu.get("label", f"followup_{len(validated_followups)}"),
                    "time":     len(current_steps) * 10 + len(validated_followups) * 10,
                    "values":   {k: str(v) for k, v in fu["inputs"].items()},
                    "expected": {k: str(v) for k, v in fu.get("expected_outputs", {}).items()},
                })
        if validated_followups:
            current_steps = current_steps + validated_followups
            test_plan = dict(test_plan)
            test_plan["test_count"] = len(current_steps)
        else:
            final_verdict = verdict
            break


    last = iterations[-1] if iterations else {}

    return {
        "status":          "ok",
        "verdict":         final_verdict,
        "confidence":      last.get("confidence", "low"),
        "summary":         last.get("summary", ""),
        "findings":        last.get("findings", []),
        "root_cause":      last.get("root_cause", ""),
        "suggested_fix":   last.get("suggested_fix", ""),
        "circuit_type":    understanding.get("circuit_type", ""),
        "circuit_description": understanding.get("description", ""),
        "test_plan":       {
            "strategy":    test_plan.get("strategy"),
            "description": test_plan.get("description"),
            "test_count":  len(current_steps),
            "assert_count": sum(1 for s in current_steps if s.get("expected")),
        },
        "iterations":      iterations,
        "coverage":        understanding.get("complexity", ""),
        "coverage_assessment": last.get("coverage_assessment", ""),
    }
    



import math as _math

@app.post("/ai_assist_followup")
@limiter.limit("10/minute")
async def ai_assist_followup(
    request:      Request,
    payload:      FollowUpRequest,
    current_user: str = Depends(_get_current_user),
):
    """
    Multi-turn design conversation.
    Reads current canvas state, applies targeted edits based on user feedback.

    Examples:
    - "the baud counter enable is unconnected, fix it"
    - "change the FIFO depth to 32"
    - "the FSM is missing the stop bit state"
    """
    print(f"\n[FOLLOWUP] prompt: {payload.prompt}", flush=True)
    print(f"[FOLLOWUP] canvas: {len(payload.current_nodes)} nodes, "
          f"{len(payload.current_edges)} edges", flush=True)

    user_api_key, user_provider, user_model = _extract_user_api_key(request)
    byok = bool(user_api_key)
    _followup_llm, _followup_model = _get_llm_client(user_api_key, user_provider, user_model)


    node_summary = [
        {"id": n.get("id"), "type": n.get("type"), "name": n.get("data", {}).get("name")}
        for n in payload.current_nodes[:40]
    ]
    edge_summary = [
        {"src": e.get("source"), "sh": e.get("sourceHandle"),
         "tgt": e.get("target"), "th": e.get("targetHandle")}
        for e in payload.current_edges[:60]
    ]

    system_msg = (
        "You are an RTL design assistant. The user has a circuit on their canvas "
        "and wants to make a targeted change or fix.\n\n"
        "You will receive:\n"
        "1. The user's feedback/request\n"
        "2. A summary of the current canvas nodes and edges\n\n"
        "You must output ONLY a JSON object with targeted edits:\n"
        "{\n"
        '  "explanation": "what you changed and why",\n'
        '  "add_nodes": [...new canvas nodes to add...],\n'
        '  "remove_node_ids": [...ids of nodes to remove...],\n'
        '  "add_edges": [...new edges to add...],\n'
        '  "remove_edge_ids": [...ids of edges to remove...],\n'
        '  "update_nodes": [...{id, data_updates} for nodes to modify...]\n'
        "}\n\n"
        "Rules:\n"
        "- Only use valid node types: input, output, const, comb, reg, mux, splitter, "
        "concatenator, fsm_state, macro_counter, macro_shiftreg, macro_sync, "
        "macro_cfgcounter, macro_fifo, macro_penc, macro_dpram, macro_edgedet\n"
        "- Keep changes minimal and targeted\n"
        "- If the user asks to change a parameter, use update_nodes\n"
        "- If the user asks to add a connection, use add_edges\n"
        "- Output ONLY valid JSON, no markdown\n"
    )

    user_msg = (
        f"User request: {payload.prompt}\n\n"
        f"Current canvas nodes:\n{json.dumps(node_summary, indent=2)}\n\n"
        f"Current canvas edges:\n{json.dumps(edge_summary, indent=2)}\n\n"
        "Output the JSON edits now:"
    )

    try:
        resp = _followup_llm.chat.completions.create(
            model=_followup_model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=2000,
        )
        raw = resp.choices[0].message.content.strip()

        json_str = None
        if "```json" in raw:
            s = raw.find("```json") + 7
            e = raw.find("```", s)
            json_str = raw[s:e].strip()
        elif "{" in raw:
            depth, start, end = 0, raw.find("{"), -1
            for ci, ch in enumerate(raw[start:], start):
                if ch == "{": depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0: end = ci; break
            if end != -1:
                json_str = raw[start:end+1]

        if not json_str:
            return {"explanation": "Could not parse edits.", "add_nodes": [],
                    "remove_node_ids": [], "add_edges": [], "remove_edge_ids": [],
                    "update_nodes": []}

        edits = json.loads(json_str)
        print(f"[FOLLOWUP] edits: +{len(edits.get('add_nodes',[]))} nodes, "
              f"+{len(edits.get('add_edges',[]))} edges, "
              f"-{len(edits.get('remove_node_ids',[]))} nodes", flush=True)

        return edits

    except json.JSONDecodeError as e:
        return {"explanation": f"JSON error: {e}", "add_nodes": [], "remove_node_ids": [],
                "add_edges": [], "remove_edge_ids": [], "update_nodes": []}
    except Exception:
        _tb.print_exc()
        return {"explanation": "Internal error in follow-up.", "add_nodes": [],
                "remove_node_ids": [], "add_edges": [], "remove_edge_ids": [],
                "update_nodes": []}