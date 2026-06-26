import { T } from "./constants";

export const COMPONENT_CATEGORIES = [
  {
    label: "I / O",
    color: T.blue,
    items: [
      { label: "Input",  type: "input" },
      { label: "Output", type: "output" },
      { label: "Const",  type: "const" },
      { label: "Probe",  type: "probe", op: "probe" },
    ],
  },
  {
    label: "Combinational",
    color: "#a78bfa",
    items: [
      { label: "Buffer",     type: "comb", op: "buf" },
      { label: "Add",        type: "comb", op: "add" },
      { label: "Sub",        type: "comb", op: "sub" },
      { label: "Multiplier", type: "comb", op: "mul" },
      { label: "AND",        type: "comb", op: "and" },
      { label: "OR",         type: "comb", op: "or"  },
      { label: "XOR",        type: "comb", op: "xor" },
      { label: "NOT",        type: "comb", op: "not" },
      { label: "Equal",      type: "comb", op: "eq"  },
      { label: "Greater",    type: "comb", op: "gt"  },
      { label: "Less",       type: "comb", op: "lt"  },
    ],
  },
  {
    label: "Routing",
    color: "#34d399",
    items: [
      { label: "Bus Splitter", type: "splitter" },
      { label: "Bus Joiner",   type: "concatenator" },
      { label: "Mux",          type: "mux" },
    ],
  },
  {
    label: "Sequential",
    color: T.amber,
    items: [
      { label: "Register",            type: "reg" },
      { label: "FSM State",           type: "fsm_state" },
      { label: "Counter",             type: "macro_counter",  abstraction: "L1" },
      { label: "Shift Register",      type: "macro_shiftreg", abstraction: "L1" },
      { label: "Synchronizer (2-FF)", type: "macro_sync",     abstraction: "L1" },
    ],
  },
  {
    label: "Arithmetic",
    color: T.red,
    items: [
      { label: "Encoder",          type: "encoder",     op: "enc" },
      { label: "Decoder",          type: "decoder",     op: "dec" },
      { label: "Priority Encoder", type: "macro_penc",  abstraction: "L1" },
    ],
  },
  {
    label: "Memory",
    color: "#fb923c",
    items: [
      { label: "Sync FIFO",     type: "macro_fifo",  abstraction: "L1" },
      { label: "Dual-Port RAM", type: "macro_dpram", abstraction: "L1" },
    ],
  },
  {
    label: "Utility",
    color: T.cyan,
    items: [
      { label: "Edge Detector", type: "macro_edgedet",    abstraction: "L1" },
      { label: "Cfg Counter",   type: "macro_cfgcounter",  abstraction: "L1" },
    ],
  },
];

export const COMPONENTS = COMPONENT_CATEGORIES.flatMap((c) => c.items);
