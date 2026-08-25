

from __future__ import annotations

import os
import json
import sqlite3
from pathlib import Path
from fastapi import HTTPException, Request, Depends
from openai import OpenAI
from dotenv import load_dotenv
import traceback as _tb

# Moved from api.py: core's db helpers depend on these, so they must be
# defined here rather than in the module that imports core.
load_dotenv(Path(__file__).parent/".env")
_OFFLINE_MODE  = os.environ.get("OFFLINE_MODE",   "false").lower() == "true"
_LOCAL_DB_PATH = Path(__file__).parent / "local_db.json"


BACKEND_DIR = Path(__file__).parent
CODEGEN_DIR = BACKEND_DIR / "rtl_codegen"
EMIT_SCRIPT = CODEGEN_DIR / "emit_verilog.py"
TB_SCRIPT   = CODEGEN_DIR / "emit_testbench.py"
TOP_VERILOG = CODEGEN_DIR / "top.v"
TB_VERILOG  = CODEGEN_DIR / "top_tb.v"


_PROVIDER_URLS = {
    "openai": "https://api.openai.com/v1",
    "groq":   "https://api.groq.com/openai/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "local":  "http://localhost:1234/v1",
}
_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "groq":   "openai/gpt-oss-120b",
    "nvidia": "meta/llama-3.3-70b-instruct",
    "local":  "qwen2.5-coder-7b-instruct",
}

_LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai")
_LLM_API_KEY  = os.environ.get("LLM_API_KEY",  "")
_LLM_MODEL    = os.environ.get("LLM_MODEL",    _DEFAULT_MODELS.get(_LLM_PROVIDER, "gpt-4o-mini"))
_LLM_BASE_URL = _PROVIDER_URLS.get(_LLM_PROVIDER, _PROVIDER_URLS["openai"])

# ── LLM client timeouts ─────────────────────────────────────────────────────
# The OpenAI SDK defaults to a 600-second timeout with 2 automatic retries, so a
# provider that stalls can block for up to 30 minutes. Because these calls are
# synchronous inside async handlers, that blocks the whole event loop — the
# backend stops serving every request and Ctrl+C cannot interrupt it, since the
# signal is only handled once Python returns from the socket read.
#
# This matters more for self-hosted and on-demand endpoints (NVIDIA NIM, Ollama,
# vLLM) than for OpenAI: those load models on demand, so a cold start can take
# tens of seconds and a gateway timeout in front of a not-yet-ready model is
# normal rather than exceptional.
#
# max_retries=0 hands retry control to the pipeline's own retry logic, which
# re-prompts with the error fed back. Leaving the SDK's retries on would stack
# two independent retry mechanisms and multiply the worst-case wait.
_LLM_TIMEOUT_S  = float(os.environ.get("LLM_TIMEOUT_SECONDS", "90"))
_LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "0"))


def _make_llm_client(base_url: str, api_key: str) -> OpenAI:
    """Construct an OpenAI-compatible client with sane timeout behaviour.

    Every client in the process is built here so timeout policy is set once
    rather than per call site.
    """
    return OpenAI(base_url=base_url, api_key=api_key,
                  timeout=_LLM_TIMEOUT_S, max_retries=_LLM_MAX_RETRIES)


_llm_client = _make_llm_client(_LLM_BASE_URL, _LLM_API_KEY) if _LLM_API_KEY else None

def _get_llm_client(user_api_key=None, user_provider=None, user_model=None):
    """Return (client, model) for BYOK or server defaults."""
    if user_api_key and user_api_key.strip():
        key      = user_api_key.strip()
        provider = (user_provider or "openai").strip().lower()
        if provider not in _PROVIDER_URLS:
            raise HTTPException(status_code=400,
                detail=f"Unknown provider '{provider}'. Supported: {list(_PROVIDER_URLS.keys())}")
        base_url = _PROVIDER_URLS[provider]
        model    = (user_model or _DEFAULT_MODELS.get(provider, _LLM_MODEL)).strip()
        return _make_llm_client(base_url, key), model
    if _llm_client is None:
        raise HTTPException(status_code=403, detail={"code": "byok_required", "message": "No API key set. Please enter your API key in Settings (click the key icon in the toolbar)."})
    return _llm_client, _LLM_MODEL

def _extract_user_api_key(request):
    """Extract BYOK key, provider, model from headers. Returns (key, provider, model)."""
    key      = request.headers.get("X-User-Api-Key") or None
    provider = request.headers.get("X-User-Api-Provider") or "openai"
    model    = request.headers.get("X-User-Model") or None
    return key, provider, model


_VALID_TYPES = {
    "input", "output", "const",
    "comb", "encoder", "decoder",
    "splitter", "concatenator", "mux",
    "reg", "macro_counter", "macro_shiftreg", "macro_sync", "macro_cfgcounter",
    "macro_penc",
    "macro_fifo", "macro_dpram",
    "macro_edgedet",
    "fsm_state",
}

_DEFAULT_SRC = {
    "reg":              "q",
    "macro_sync":       "q",
    "macro_fifo":       "dout",
    "macro_penc":       "index",
    "macro_dpram":      "dout_a",
    "macro_cfgcounter": "count",
    "fsm_state":        "out",
}
def _src_handle(ntype):
    return _DEFAULT_SRC.get(ntype, "out")

def _tgt_handle(ttype, tdata, count):
    if ttype == "output":                      return "in"
    if ttype in ("reg", "macro_sync"):         return "d"
    if ttype == "macro_counter":               return "en" if count == 0 else "res"
    if ttype == "macro_shiftreg":              return {0:"din",1:"sin",2:"en",3:"load"}.get(count,"din")
    if ttype == "macro_fifo":                  return {0:"wr_en",1:"din",2:"rd_en"}.get(count,"wr_en")
    if ttype == "macro_penc":                  return "data_in"
    if ttype == "macro_edgedet":               return "signal_in"
    if ttype == "macro_dpram":
        return {0:"we_a",1:"addr_a",2:"din_a",3:"we_b",4:"addr_b",5:"din_b"}.get(count,"we_a")
    if ttype == "macro_cfgcounter":
        return {0:"enable",1:"load",2:"load_value"}.get(count,"enable")
    if ttype == "mux":
        mux_n = int(tdata.get("muxSize","2") or "2")
        return f"in{count}" if count < mux_n else f"sel{count-mux_n}"
    if ttype == "comb":
        op = tdata.get("op","add")
        return "in0" if (op in ("not","buf") or count == 0) else "in1"
    if ttype == "concatenator":                return f"in{count}"
    if ttype in ("splitter","encoder","decoder"): return "in0"
    return "in"


def _supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Supabase not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY."
        )
    try:
        from supabase import create_client
        return create_client(url, key)
    except ImportError:
        raise RuntimeError("supabase-py not installed.")




def _local_db_read() -> dict:
    if _LOCAL_DB_PATH.exists():
        with open(_LOCAL_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"projects": {}, "custom_blocks": {}}


def _local_db_write(db: dict):
    with open(_LOCAL_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2)
async def _get_current_user(request: Request) -> str:
    if _OFFLINE_MODE:
        return "local_user"
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.split(" ", 1)[1]
    try:
        sb = _supabase()
        response = sb.auth.get_user(token)
        if not response or not response.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return response.user.id
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        raise HTTPException(status_code=401, detail="Token verification failed")

# Re-export every top-level name, including the underscore-prefixed ones.
# `from x import *` skips leading-underscore names by default, and this file
# was split out of api.py where those names shared one namespace — so an
# explicit __all__ is what preserves resolution exactly as it was.
__all__ = [_n for _n in dir() if not _n.startswith("__")]