# Known Issues

This file documents known limitations and bugs in RTLCopilot, particularly in the RTL Brain AI pipeline. Community contributions to fix these are very welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## RTL Brain pipeline — LLM quality issues

These are **prompt engineering problems**, not structural pipeline bugs. The pipeline infrastructure is correct. The LLM occasionally makes wrong semantic decisions.

### L1 — Wrong register handle
**Description:** Stage 1 sometimes wires `clock_enable → reg[clk]` instead of `reg[en]`. `clk` is an implicit port and should never be a wiring target.

**Affected prompt types:** Circuits with clock-gated registers (accumulators, sample-and-hold).

**Fix location:** `_RTL_BRAIN_STAGE1_SYSTEM` prompt in `api.py` + assembler guard.

---

### L2 — Missing MUX for clamp logic
**Description:** Stage 0 doesn't include a MUX when decomposing saturating accumulators. A saturating adder needs: adder + comparator + **mux** (select clamped vs unclamped) + register. Stage 0 omits the mux.

**Affected prompt types:** Saturating adder, saturating accumulator, clamping circuits.

**Fix location:** `_RTL_BRAIN_STAGE0_SYSTEM` prompt in `api.py`.

---

### L3 — Stage 3 uses short signal names
**Description:** Stage 3 occasionally invents generic FSM output names (`count_enable`, `fifo_write_en`) instead of using the exact names suggested by `_extract_control_requirements` (`burst_counter_count_enable`, `write_buffer_fifo_fifo_write_en`). This breaks the autowiring step.

**Affected prompt types:** Circuits with multiple datapath blocks needing FSM control.

**Fix location:** Stage 3 user prompt construction in `_rtl_brain_stage3_fsm` — the locked output list needs stronger enforcement.

---

### L4 — Wrong FIFO output wired to FSM
**Description:** Stage 1 occasionally wires `fifo[dout]` (data output) to the FSM input when it should wire `fifo[full]` or `fifo[empty]` (status signals).

**Affected prompt types:** Circuits where the FSM needs to react to FIFO fill level.

**Fix location:** `_RTL_BRAIN_STAGE1_SYSTEM` prompt — needs clearer guidance on which FIFO outputs carry status vs data.

---

## RC3 — Width model inconsistency

**Description:** The width declared in the IR for combinational nodes doesn't always match the width the emitter uses. For multi-bit comb nodes, this produces `WIDTH MISMATCH` warnings in IR validation but doesn't always cause iverilog errors.

**Impact:** Semantically wrong wire widths in generated Verilog for some circuits.

**Fix location:** `net_ir.py` width inference + assembler width stamping.

---

## Two-FSM circuits — untested

**Description:** The pipeline handles one FSM correctly. Circuits requiring two independent FSMs have not been tested. `_FSM_TRANSITION_TABLES` is a global dict and `_autowire_control_outputs` only handles one FSM at a time.

**Status:** Unknown — may work, may not.

**Fix location:** `_run_rtl_brain` FSM loop + `_autowire_control_outputs` in `api.py`.

---

## Pure datapath circuits — partially tested

**Description:** Circuits with no FSM (pure adder + register + comparator chains) work in the no-FSM path. Width assignments and handle wiring for complex multi-stage datapaths need more test coverage.

**Status:** Basic cases work. Complex multi-stage datapaths may have width issues (RC3).

---

## Shift register `din` width

**Description:** For deserializer (SIPO) blocks, `din` should be 1-bit (serial input) but the emitter defaults to `DATA_WIDTH`. This produces a width mismatch warning.

**Fix location:** `block_mapper.py` notes field + Stage 1 width constraint.

---

## Stage 3 FSM transitions — semantic errors

**Description:** Stage 3 sometimes uses the wrong condition signal for FSM transitions. Example: uses `threshold_detector` output instead of `counter_tc` for a frame-done transition. The Verilog compiles but the circuit logic is wrong.

**Impact:** Functionally incorrect FSM behaviour for some prompt types.

**Fix location:** Stage 3 system prompt — conditions need stronger grounding to the available condition wires.

---

## Reporting new issues

Please open a GitHub issue with:
1. The prompt you used
2. The generated Verilog (copy from the RTL tab)
3. Backend logs if available
4. What you expected vs what you got
