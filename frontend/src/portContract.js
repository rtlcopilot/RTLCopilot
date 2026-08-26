/**
 * portContract.js — client for the backend port width contract.
 *
 * The canvas DRC used to carry its own resolveOutWidth / expectedPinWidth
 * tables, which drifted from the backend's (macro_cfgcounter's enable vs en,
 * macro_edgedet's out vs pulse_out, bitwise comb ops forced to 1 bit). This
 * module fetches backend/port_contract.py's serialised contract and resolves
 * widths with the same rules, so the panel reports what the emitter will
 * actually build.
 *
 * A bundled fallback keeps DRC working before the fetch resolves and in
 * offline mode. Keep it in sync with port_contract.PATTERN_PORTS — the
 * backend lint (backend/tests/test_port_contract.py) is the source of truth.
 */

import { API_BASE } from "./config";

const ONE = "1";
const DATA = "data";
const ADDR = "addr";
const ACC  = "acc";
const CLOG2_DATA = "clog2(data)";
const TWICE_DATA = "2*data";
const SERIAL = "serial";
const FREE = "free";

const FALLBACK = {
  version: 0,
  patterns: {
    comb:         { inputs: { "in*": DATA },                        outputs: { out: DATA } },
    mux:          { inputs: { "in*": DATA, "sel*": ONE },           outputs: { out: DATA } },
    const:        { inputs: { in: DATA },                           outputs: { out: DATA } },
    input:        { inputs: {},                                     outputs: { out: DATA } },
    output:       { inputs: { in: DATA },                           outputs: {} },
    probe:        { inputs: { in: FREE },                           outputs: { out: FREE } },
    splitter:     { inputs: { in: FREE },                           outputs: { out: FREE } },
    concatenator: { inputs: { "in*": FREE },                        outputs: { out: FREE } },
    custom_block: { inputs: {},                                     outputs: {} },
    reg:          { inputs: { d: DATA, en: ONE },                   outputs: { q: DATA } },
    macro_sync:   { inputs: { d: ONE },                             outputs: { q: ONE } },
    macro_counter:    { inputs: { en: ONE, res: ONE },              outputs: { count: DATA, tc: ONE } },
    macro_cfgcounter: { inputs: { en: ONE, load: ONE, load_val: DATA }, outputs: { count: DATA, tc: ONE } },
    macro_shiftreg:   { inputs: { din: DATA, sin: SERIAL, en: ONE, load: ONE }, outputs: { q: DATA, sout: SERIAL } },
    macro_fifo:   { inputs: { wr_en: ONE, rd_en: ONE, din: DATA },  outputs: { dout: DATA, full: ONE, empty: ONE, ae: ONE } },
    macro_penc:   { inputs: { data_in: DATA },                      outputs: { index: CLOG2_DATA, valid: ONE } },
    macro_edgedet:{ inputs: { signal_in: ONE },                     outputs: { out: ONE } },
    macro_dpram:  { inputs: { we_a: ONE, addr_a: ADDR, din_a: DATA, we_b: ONE, addr_b: ADDR, din_b: DATA },
                    outputs: { dout_a: DATA, dout_b: DATA } },
    macro_mac:    { inputs: { a: DATA, b: DATA, en: ONE, clear: ONE },
                    outputs: { result: ACC, overflow: ONE } },
    macro_rom:    { inputs: { addr: ADDR },                         outputs: { dout: DATA } },
    encoder:      { inputs: { data_in: DATA },                      outputs: { out: CLOG2_DATA } },
    decoder:      { inputs: { data_in: CLOG2_DATA },                outputs: { out: DATA } },
    fsm:          { inputs: { "*": ONE },                           outputs: { "*": ONE } },
    fsm_state:    { inputs: { "*": ONE },                           outputs: { "*": ONE } },
  },
  aliases: {
    enable: "en", load_value: "load_val", reset: "res",
    pulse_out: "out", a_empty: "ae", almost_empty: "ae",
  },
  pattern_aliases: {
    "macro_shiftreg.out": "q", "macro_counter.out": "count",
    "macro_sync.out": "q", "reg.out": "q",
  },
  comb_predicate_ops: ["eq", "ge", "gte", "le", "lt", "lte", "ne", "neq", "gt"],
  comb_widening_ops: { mul: TWICE_DATA },
  required_inputs: {
    reg: ["d"], macro_sync: ["d"], macro_counter: ["en"],
    macro_cfgcounter: ["en"], macro_fifo: ["din", "wr_en", "rd_en"],
    macro_penc: ["data_in"], macro_edgedet: ["signal_in"],
    macro_dpram: ["addr_a", "addr_b"], macro_rom: ["addr"],
    macro_mac: ["a", "b", "en"],
    encoder: ["data_in"], decoder: ["data_in"], output: ["in"],
  },
  shiftreg_serial_out: ["PISO", "SISO"],
  shiftreg_serial_in: ["SIPO", "SISO"],
};

const COMB_UNARY_OPS = ["not", "buf"];

let contract = FALLBACK;
let loaded = false;

/** Fetch the contract once. Safe to call repeatedly; failures keep the fallback. */
export async function loadPortContract() {
  if (loaded) return contract;
  try {
    const res = await fetch(`${API_BASE}/handle_contract`);
    if (res.ok) {
      const data = await res.json();
      if (data && data.patterns) {
        contract = data;
        loaded = true;
      }
    }
  } catch {
    /* offline or backend down — the bundled fallback is still correct enough
       to run DRC, it just won't pick up contract changes. */
  }
  return contract;
}

export function contractVersion() {
  return contract.version ?? 0;
}

/** Map an accepted handle spelling to its canonical name. */
export function canonical(handle, pattern) {
  if (!handle) return handle;
  const h = String(handle).trim();
  const scoped = contract.pattern_aliases?.[`${pattern}.${h}`];
  if (scoped) return scoped;
  return contract.aliases?.[h] ?? h;
}

function intOr(v, dflt) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) && n > 0 ? n : dflt;
}

function lookupSpec(pattern, handle, direction) {
  const ports = contract.patterns?.[pattern];
  if (!ports) return { found: false, spec: FREE };
  const table = ports[direction] || {};
  if (Object.prototype.hasOwnProperty.call(table, handle)) {
    return { found: true, spec: table[handle] };
  }
  for (const [key, spec] of Object.entries(table)) {
    if (key.endsWith("*") && handle.startsWith(key.slice(0, -1))) {
      return { found: true, spec };
    }
  }
  return { found: false, spec: FREE };
}

/**
 * Resolve one handle to a concrete bit width.
 * Returns a number, or null when the handle is deliberately unconstrained
 * (splitter/concat/probe/custom_block) — callers must skip the width check
 * rather than defaulting to 1.
 * Returns undefined when the pattern declares no such handle.
 */
/**
 * Stage-0 stand-in handles like <condition_signals>, replaced by Stage 3 with
 * real signal names. Not ports, so they have no width and must be skipped by
 * every check — the fsm pattern's "*" wildcard would otherwise resolve them to
 * 1 bit and report conflicts against a handle that does not exist yet.
 */
export function isPlaceholder(handle) {
  const h = String(handle || "").trim();
  return h.startsWith("<") && h.endsWith(">");
}

export function resolveWidth(pattern, handle, direction, nodeData = {}) {
  const pat = String(pattern || "").trim();
  if (isPlaceholder(handle)) return null;   // unconstrained
  const h = canonical(handle, pat);
  const dw = intOr(nodeData.width, 8);
  const aw = intOr(nodeData.addrWidth, 6);
  const op = String(nodeData.op || "").toLowerCase().trim();

  const { found, spec } = lookupSpec(pat, h, direction);
  if (!found) return undefined;

  let s = spec;

  if (pat === "comb" && direction === "outputs") {
    if ((contract.comb_predicate_ops || []).includes(op)) return 1;
    const widening = contract.comb_widening_ops?.[op];
    if (widening) s = widening;
  }

  if (s === FREE || s === null) return null;
  if (s === ONE || s === SERIAL) return 1;
  if (s === DATA) return dw;
  if (s === ADDR) return aw;
  if (s === ACC)  return intOr(nodeData.accWidth, 32);
  if (s === CLOG2_DATA) return Math.max(1, Math.ceil(Math.log2(Math.max(dw, 2))));
  if (s === TWICE_DATA) return 2 * dw;
  const lit = parseInt(s, 10);
  return Number.isFinite(lit) ? Math.max(1, lit) : dw;
}

/** Input handles that must be driven, given the node's own configuration. */
export function requiredInputs(pattern, nodeData = {}) {
  const pat = String(pattern || "").trim();
  const op = String(nodeData.op || "").toLowerCase().trim();

  if (pat === "comb") {
    return COMB_UNARY_OPS.includes(op) ? ["in0"] : ["in0", "in1"];
  }
  if (pat === "mux") {
    const n = Math.max(2, intOr(nodeData.muxSize, 2));
    const selBits = Math.max(1, Math.ceil(Math.log2(n)));
    return [
      ...Array.from({ length: n }, (_, i) => `in${i}`),
      ...Array.from({ length: selBits }, (_, i) => `sel${i}`),
    ];
  }
  if (pat === "macro_shiftreg") {
    const mode = String(nodeData.srMode || "PISO").toUpperCase().trim();
    const serialIn = (contract.shiftreg_serial_in || []).includes(mode);
    return [serialIn ? "sin" : "din", "en"];
  }
  return contract.required_inputs?.[pat] ?? [];
}

/** Human-readable list of valid handles, for error messages. */
export function validHandles(pattern, direction, nodeData = {}) {
  const ports = contract.patterns?.[String(pattern || "").trim()];
  if (!ports) return [];
  const table = ports[direction] || {};
  const out = [];
  const n = Math.max(2, intOr(nodeData.muxSize, 2));
  const selBits = Math.max(1, Math.ceil(Math.log2(n)));
  for (const key of Object.keys(table)) {
    if (key === "*") continue;
    if (key === "in*" && pattern === "mux") {
      for (let i = 0; i < n; i++) out.push(`in${i}`);
    } else if (key === "sel*") {
      for (let i = 0; i < selBits; i++) out.push(`sel${i}`);
    } else if (key === "in*") {
      out.push("in0", "in1");
    } else if (!key.endsWith("*")) {
      out.push(key);
    }
  }
  return out;
}