# Contributing to RTLCopilot

RTLCopilot was created by [Suchit Tilak](https://github.com/rtlcopilot). Contributions from the community are very welcome — especially to RTL Brain, the AI pipeline, and the PD flow.

---

## Quick setup for contributors (Offline mode)

If you just want to test RTL Brain, fix a bug, or explore the codebase — use offline mode. It bypasses Supabase and Google OAuth entirely.

**Backend `.env`:**
```
OFFLINE_MODE=true
ALLOWED_ORIGINS=http://localhost:5173
```

**Frontend `.env`:**
```
VITE_OFFLINE_MODE=true
VITE_API_URL=http://localhost:8080
```

Then:
```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
uvicorn api:app --reload --port 8080

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

App loads at `http://localhost:5173`. You're auto-logged in as "Local User". Projects and custom blocks save to `backend/local_db.json` on your machine. No Supabase account needed.

---

## Getting started

1. Fork the repo and clone locally
2. Follow the setup steps in [README.md](README.md)
3. Pick an issue from the [issue tracker](https://github.com/rtlcopilot/rtlcopilot/issues) or check [KNOWN_ISSUES.md](KNOWN_ISSUES.md)
4. Open a PR with a clear description of what you changed and why

---

## Architecture overview

### Backend — `backend/api.py`

The main FastAPI application (~7400 lines). Contains:

- **Routes** — `/ai_assist`, `/generate_verilog`, `/simulate`, `/ai_verify`, `/custom_blocks`, `/projects`
- **RTL Brain pipeline** — `_rtl_brain_stage0/1/2/3`, `_run_rtl_brain`, `_rtl_brain_assemble`
- **V2 emitter bridge** — `_v2_build_*`, `_run_hierarchical_v2_from_hierarchy`
- **IR utilities** — `_ir_annotate_and_validate`, `_iverilog_compile_check`

Runs on your machine at port 8080.

---

### RTL Brain pipeline

The most complex and highest-impact area for contributions.

```
User prompt
    ↓
Stage 0 (_rtl_brain_stage0)
    Decomposes prompt into generic blocks
    (fifo, counter, comparator, state_machine)

Stage 1 (_rtl_brain_stage1)
    Wires blocks, assigns parameters and I/O
    NOTE: Control handles (wr_en, rd_en, en, load)
    are hidden from Stage 1 when an FSM is present

Python Assembler (_rtl_brain_assemble)
    Converts Stage 1 JSON into a hierarchy dict
    Normalises handle names, strips implicit ports

Stage 2 (_rtl_brain_stage2)
    Extracts signal_list and output_logic

Stage 3 (_rtl_brain_stage3_fsm)
    Generates FSM transition tables
    Must use exact signal names from
    _extract_control_requirements

V2 Emitter (_run_hierarchical_v2_from_hierarchy)
    Converts hierarchy dict → canvas nodes/edges + Verilog
```

---

### Block mapper — `backend/block_mapper.py`

Maps generic block names to primitives. The handle name contract defined here is the **single source of truth** for the entire pipeline. Never rename handles without updating all downstream consumers.

---

### Verilog emitter — `backend/rtl_codegen/emit_verilog.py`

Takes an IR dict, emits Verilog. Deterministic — same IR always produces same output. Sub-module files (FIFO, counter, shiftreg) are emitted separately alongside `top.v`.

---

### PD pipeline — `pd/api.py`

Runs **inside Docker** at port 7070. Separate from the main backend. Handles:

- Yosys synthesis — netlist generation
- OpenROAD floorplan, placement, CTS, routing
- DRC check
- GDS export

Uses Sky130 PDK (pinned to `0fe599b2afb6708d281543108caf8310912f54af`). Run outputs go to `pd/work/{run_id}/`.

If you want to contribute to the PD pipeline, you need Docker Desktop with 8GB+ RAM.

---

### Frontend — `frontend/src/`

- `App.jsx` — canvas state, node management, `compileIR()`, `generateVerilog()`
- `components/nodes/index.jsx` — all canvas block renderers
- `components/AiSidebar.jsx` — AI chat interface
- `components/CustomBlockModal.jsx` — 4-step custom block creator
- `componentCategories.js` — block palette categories and items

---

## Good first contributions

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for the full list. High priority:

### RTL Brain
- Stage 1 wires `clock_enable → reg[clk]` instead of `reg[en]`
- Stage 0 omits MUX for saturating accumulator clamp logic
- Stage 3 occasionally uses short signal names
- Width model inconsistency (RC3) for multi-bit comb nodes

### Known circuits
Adding more known circuits to `backend/known_circuits.py` is one of the highest-impact contributions — fully deterministic, no LLM involved, always correct.

### PD pipeline
- Additional PDK support (IHP SG13G2, GF180MCU)
- Timing constraint automation
- Better DRC reporting

---

## Adding a new primitive block

1. Add generic name to `GENERIC_VOCABULARY` in `block_mapper.py`
2. Add primitive mapping to `_GENERIC_TO_PRIMITIVE`
3. Add emitter in `backend/rtl_codegen/` following existing patterns
4. Add instantiation case in `emit_verilog.py`
5. Add node renderer in `frontend/src/components/nodes/index.jsx`
6. Register in `frontend/src/nodeTypes.js`
7. Add to `frontend/src/componentCategories.js`

---

## Adding a known circuit

Known circuits live in `backend/known_circuits.py`. Each entry needs:
- A hierarchy dict (see existing examples)
- A list of circuit keywords for routing
- An FSM transition table if the circuit has state

---

## Pull request guidelines

- One PR per fix or feature
- Describe the problem and your approach
- If you change handle names or IR structure, note all affected files
- Test with `python -c "import api"` before submitting
- For RTL Brain fixes, include the prompt you tested with and the generated Verilog

---

## Questions

Open a GitHub issue with the `question` label.

---

*RTLCopilot was created by Suchit Tilak. All contributions are made under the AGPL-3.0 license.*