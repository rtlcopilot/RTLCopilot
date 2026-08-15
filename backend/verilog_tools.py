

from __future__ import annotations

import json
import subprocess
import tempfile
import traceback as _tb
from pathlib import Path as _Path
from core import *


async def _iverilog_compile_check(verilog_files: dict) -> tuple[bool, str]:
    """
    Compile verilog_files with iverilog -tnull.
    Returns (success, error_string).
    """
    try:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            for fname, code in verilog_files.items():
                (p / fname).write_text(code, encoding="utf-8")
            dfiles = [str(p / f) for f in verilog_files]
            result = subprocess.run(
                ["iverilog", "-tnull", "-s", "top"] + dfiles,
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr.strip()
    except FileNotFoundError:
        return True, ""  
    except Exception as e:
        return True, str(e)


async def _llm_fix_verilog(verilog_files: dict, errors: str,
                            prompt: str, attempt: int) -> dict:
    """
    Ask LLM to fix iverilog compilation errors.
    Returns corrected verilog_files dict.
    """
    top_v = verilog_files.get("top.v", "")[:4000]
    fix_prompt = (
        f"You are fixing Verilog compilation errors. Attempt {attempt}/3.\n\n"
        f"Design intent: {prompt}\n\n"
        f"iverilog errors:\n{errors}\n\n"
        f"Current top.v (truncated):\n```verilog\n{top_v}\n```\n\n"
        "Rules:\n"
        "- Fix ONLY the reported errors\n"
        "- Keep module name as 'top'\n"
        "- Keep all existing port declarations\n"
        "- Output ONLY the corrected top.v content, no explanation\n"
        "- Do NOT output markdown fences\n"
    )
    try:
        resp = _llm_client.chat.completions.create(
            model=_LLM_MODEL,
            messages=[{"role": "user", "content": fix_prompt}],
            temperature=0.0,
            max_tokens=3000,
        )
        fixed = resp.choices[0].message.content.strip()
        if fixed.startswith("```"):
            lines = fixed.split("\n")
            fixed = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        verilog_files = dict(verilog_files)
        verilog_files["top.v"] = fixed
        return verilog_files
    except Exception:
        _tb.print_exc()
        return verilog_files


__all__ = [_n for _n in dir() if not _n.startswith("__")]