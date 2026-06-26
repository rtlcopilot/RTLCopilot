import {
  InputNode, OutputNode, ConstNode, CombNode, MuxNode, RegisterNode,
  SplitterNode, ConcatenatorNode, FsmStateNode, MathNode, MemoryNode,
  CounterNode, ShiftRegNode, SyncNode, FifoNode, EncoderNode, DecoderNode,
  ProbeNode, PriorityEncoderNode, EdgeDetectorNode, DualPortRamNode, CfgCounterNode,
} from "./components/nodes/index.jsx";
import { CustomBlockNode } from "./components/nodes/CustomBlockNode.jsx";
import FsmEdge from "./components/edges/FsmEdge.jsx";

export const nodeTypes = {
  input:            InputNode,
  output:           OutputNode,
  const:            ConstNode,
  comb:             CombNode,
  mux:              MuxNode,
  reg:              RegisterNode,
  splitter:         SplitterNode,
  concatenator:     ConcatenatorNode,
  fsm_state:        FsmStateNode,
  math:             MathNode,
  macro_rom:        MemoryNode,
  macro_counter:    CounterNode,
  macro_shiftreg:   ShiftRegNode,
  macro_sync:       SyncNode,
  macro_fifo:       FifoNode,
  encoder:          EncoderNode,
  decoder:          DecoderNode,
  probe:            ProbeNode,
  macro_penc:       PriorityEncoderNode,
  macro_edgedet:    EdgeDetectorNode,
  macro_dpram:      DualPortRamNode,
  macro_cfgcounter: CfgCounterNode,
  custom_block:     CustomBlockNode,
};

export const edgeTypes = { fsm: FsmEdge };