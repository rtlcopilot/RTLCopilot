import React from "react";
import { CustomBlockNode } from "./CustomBlockNode.jsx";
import { Handle, Position } from "reactflow";
import { T, nodeBox, mathBox, stateCircle, deleteBtnStyle } from "../../constants";
import EditableLabel from "../shared/EditableLabel";
import NodeWrapper from "../shared/NodeWrapper";
import { formatValue } from "../../utils";

// ─────────────────────────────────────────────────────────────────────────────
// InputNode
// ─────────────────────────────────────────────────────────────────────────────
export const InputNode = ({ id, data }) => {
  const [base, setBase] = React.useState("dec");

  const handleInputChange = (e) => {
    let raw = e.target.value;
    let parsed = parseInt(raw, base === "hex" ? 16 : base === "bin" ? 2 : 10);
    if (data.onChangeValue) {
      data.onChangeValue(id, isNaN(parsed) ? 0 : parsed);
    }
  };

  return (
    <NodeWrapper data={data} id={id}>
      <EditableLabel value={data.name} onChange={data.rename} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
        <span style={{ fontSize: "10px", fontWeight: "bold", color: T.textSecondary }}>
          VALUE ({base.toUpperCase()})
        </span>
        <select
          value={base}
          onChange={(e) => setBase(e.target.value)}
          style={{ fontSize: "9px", border: `1px solid ${T.border2}`, borderRadius: T.r4, background: T.bg2, color: T.textPrimary, cursor: "pointer" }}
        >
          <option value="dec">DEC</option>
          <option value="hex">HEX</option>
          <option value="bin">BIN</option>
        </select>
      </div>
      <input
        type="text"
        value={formatValue(data.value, base, data.width)}
        onChange={handleInputChange}
        style={{ width: "100%", padding: "6px", background: T.bg2, color: T.blue, border: `1px solid ${T.border2}`, borderRadius: T.r4, fontSize: "13px", fontFamily: T.fontMono, textAlign: "center" }}
      />
      <Handle type="source" position={Position.Right} id="out" />
    </NodeWrapper>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// OutputNode
// ─────────────────────────────────────────────────────────────────────────────
export const OutputNode = ({ id, data }) => (
  <NodeWrapper data={data} id={id}>
    <EditableLabel value={data.name} onChange={data.rename} />
    <div>OUTPUT</div>
    <Handle type="target" position={Position.Left} id="in" />
  </NodeWrapper>
);

// ─────────────────────────────────────────────────────────────────────────────
// ConstNode
// ─────────────────────────────────────────────────────────────────────────────
export const ConstNode = ({ id, data }) => {
  const handleChange = (e) => {
    const raw = e.target.value;
    if (raw === "" || raw === "-") { data.onChangeValue?.(id, raw); return; }
    const parsed = parseInt(raw, 10);
    if (!isNaN(parsed)) data.onChangeValue?.(id, parsed);
  };

  return (
    <NodeWrapper data={data} id={id} showWidth={false} customStyle={{ ...nodeBox, minWidth: "120px", maxWidth: "140px" }}>
      <div style={{ fontSize: "9px", color: T.textSecondary, letterSpacing: "1px", marginBottom: "4px" }}>CONSTANT</div>
      <EditableLabel value={data.name} onChange={data.rename} />
      <input
        type="text"
        value={data.value ?? "0"}
        onChange={handleChange}
        style={{ width: "80px", padding: "4px 6px", background: T.bg2, color: T.blue, border: `1px solid ${T.border2}`, borderRadius: T.r4, fontSize: "13px", fontFamily: T.fontMono, textAlign: "center", marginTop: "4px", display: "block" }}
      />
      <div style={{ marginTop: "6px", borderTop: `1px solid ${T.border1}`, paddingTop: "5px", fontSize: "10px", color: T.textSecondary }}>
        Width:{" "}
        <input
          type="text"
          value={data.width ?? "8"}
          onChange={(e) => data.setWidth?.(e.target.value)}
          style={{ width: "36px", textAlign: "center", background: T.bg2, border: `1px solid ${T.border2}`, color: T.blue, borderRadius: T.r4 }}
        />
      </div>
      <Handle type="target" position={Position.Left} id="in" />
      <Handle type="source" position={Position.Right} id="out" />
    </NodeWrapper>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// CounterNode
// ─────────────────────────────────────────────────────────────────────────────
export const CounterNode = ({ id, data }) => (
  <NodeWrapper data={data} id={id} customStyle={{ ...nodeBox, minWidth: "155px" }}>
    <div style={{ color: T.amber, fontWeight: "bold", fontSize: "12px" }}>
      <EditableLabel value={data.name} onChange={data.rename} />
    </div>
    <div style={{ fontSize: "9px", color: T.textSecondary, letterSpacing: "1px", marginBottom: "8px" }}>COUNTER</div>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {[{ id: "en", label: "EN", color: T.blue }, { id: "res", label: "RES", color: T.red }].map((p) => (
          <div key={p.id} style={{ position: "relative", paddingLeft: "14px", display: "flex", alignItems: "center" }}>
            <Handle type="target" position={Position.Left} id={p.id} style={{ background: p.color, width: "7px", height: "7px" }} />
            <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>{p.label}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        <div style={{ position: "relative", paddingRight: "14px", display: "flex", alignItems: "center", justifyContent: "flex-end" }}>
          <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>OUT</span>
          <Handle type="source" position={Position.Right} id="out" style={{ background: T.sigOutput, width: "7px", height: "7px" }} />
        </div>
      </div>
    </div>
    <div style={{ marginTop: "8px", display: "flex", alignItems: "center", gap: "6px" }}>
      <span style={{ fontSize: "9px", color: T.textMuted }}>Width:</span>
      <input type="text" value={data.width ?? "8"} onChange={(e) => data.setWidth?.(e.target.value)}
        style={{ width: "36px", textAlign: "center", background: T.bg3, border: `1px solid ${T.border2}`, color: T.blue, borderRadius: T.r4, fontSize: "10px" }} />
    </div>
  </NodeWrapper>
);

// ─────────────────────────────────────────────────────────────────────────────
// ShiftRegNode
// ─────────────────────────────────────────────────────────────────────────────
export const ShiftRegNode = ({ id, data }) => {
  const mode = data.srMode || "PISO";
  const dir  = data.shiftDir || "right";

  const hasDin  = mode === "PISO" || mode === "PIPO";
  const hasSin  = mode === "SISO" || mode === "SIPO";
  const hasLoad = mode === "PISO" || mode === "PIPO";
  const hasSout = mode === "SISO" || mode === "PISO";
  const hasOut  = mode === "SIPO" || mode === "PIPO";

  const MODES = ["SISO", "PISO", "SIPO", "PIPO"];
  const DIRS  = ["right", "left"];

  const btnBase = {
    padding: "2px 7px", border: "none", cursor: "pointer",
    fontSize: "9px", fontFamily: "monospace", borderRadius: "3px",
    fontWeight: "600", transition: "all 0.1s",
  };

  return (
    <NodeWrapper data={data} id={id} customStyle={{ ...nodeBox, minWidth: "175px" }}>
      <div style={{ color: "#a78bfa", fontWeight: "bold", fontSize: "12px" }}>
        <EditableLabel value={data.name} onChange={data.rename} />
      </div>
      <div style={{ fontSize: "9px", color: T.textSecondary, letterSpacing: "1px", marginBottom: "6px" }}>SHIFT REG</div>

      {/* Mode selector */}
      <div style={{ display: "flex", gap: "2px", marginBottom: "4px", flexWrap: "wrap" }}>
        {MODES.map((m) => (
          <button key={m}
            onClick={() => data.setSrMode?.(m)}
            style={{ ...btnBase,
              background: mode === m ? "#a78bfa33" : T.bg3,
              color: mode === m ? "#a78bfa" : T.textMuted,
              border: `1px solid ${mode === m ? "#a78bfa55" : T.border2}`,
            }}>
            {m}
          </button>
        ))}
      </div>

      {/* Direction selector — hidden for PIPO */}
      {mode !== "PIPO" && (
        <div style={{ display: "flex", gap: "2px", marginBottom: "6px" }}>
          {DIRS.map((d) => (
            <button key={d}
              onClick={() => data.setShiftDir?.(d)}
              style={{ ...btnBase,
                background: dir === d ? `${T.blue}33` : T.bg3,
                color: dir === d ? T.blue : T.textMuted,
                border: `1px solid ${dir === d ? T.blue + "55" : T.border2}`,
              }}>
              {d === "right" ? ">> RIGHT" : "<< LEFT"}
            </button>
          ))}
        </div>
      )}

      {/* Pins */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        {/* Inputs */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {hasDin && (
            <div style={{ position: "relative", paddingLeft: "14px", display: "flex", alignItems: "center" }}>
              <Handle type="target" position={Position.Left} id="din" style={{ background: T.blue, width: "7px", height: "7px" }} />
              <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>DIN</span>
            </div>
          )}
          {hasSin && (
            <div style={{ position: "relative", paddingLeft: "14px", display: "flex", alignItems: "center" }}>
              <Handle type="target" position={Position.Left} id="sin" style={{ background: T.blue, width: "7px", height: "7px" }} />
              <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>SIN</span>
            </div>
          )}
          {hasLoad && (
            <div style={{ position: "relative", paddingLeft: "14px", display: "flex", alignItems: "center" }}>
              <Handle type="target" position={Position.Left} id="load" style={{ background: T.amber, width: "7px", height: "7px" }} />
              <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>LOAD</span>
            </div>
          )}
          <div style={{ position: "relative", paddingLeft: "14px", display: "flex", alignItems: "center" }}>
            <Handle type="target" position={Position.Left} id="en" style={{ background: T.blue, width: "7px", height: "7px" }} />
            <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>EN</span>
          </div>
        </div>

        {/* Outputs */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {hasSout && (
            <div style={{ position: "relative", paddingRight: "14px", display: "flex", alignItems: "center", justifyContent: "flex-end" }}>
              <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>SOUT</span>
              <Handle type="source" position={Position.Right} id="sout" style={{ background: T.sigOutput, width: "7px", height: "7px" }} />
            </div>
          )}
          {hasOut && (
            <div style={{ position: "relative", paddingRight: "14px", display: "flex", alignItems: "center", justifyContent: "flex-end" }}>
              <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>OUT</span>
              <Handle type="source" position={Position.Right} id="out" style={{ background: T.sigOutput, width: "7px", height: "7px" }} />
            </div>
          )}
        </div>
      </div>

      {/* Width */}
      <div style={{ marginTop: "8px", display: "flex", alignItems: "center", gap: "6px" }}>
        <span style={{ fontSize: "9px", color: T.textMuted }}>Width:</span>
        <input type="text" value={data.width ?? "8"} onChange={(e) => data.setWidth?.(e.target.value)}
          style={{ width: "36px", textAlign: "center", background: T.bg3, border: `1px solid ${T.border2}`, color: T.blue, borderRadius: T.r4, fontSize: "10px" }} />
      </div>
    </NodeWrapper>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// SyncNode
// ─────────────────────────────────────────────────────────────────────────────
export const SyncNode = ({ id, data }) => (
  <NodeWrapper data={data} id={id} customStyle={nodeBox}>
    <div style={{ color: T.blue }}><EditableLabel value={data.name} onChange={data.rename} /></div>
    <div style={{ fontSize: "9px", opacity: 0.6, color: T.textSecondary }}>CDC SYNC (2-FF)</div>
    <div style={{ display: "flex", justifyContent: "space-between", marginTop: "10px" }}>
      <div style={{ position: "relative", paddingLeft: "10px" }}>
        <Handle type="target" position={Position.Left} id="d" style={{ background: T.sigInput }} />
        <span style={{ fontSize: "9px", color: T.textSecondary }}>ASYNC</span>
      </div>
      <div style={{ position: "relative", paddingRight: "10px" }}>
        <Handle type="source" position={Position.Right} id="q" style={{ background: T.sigOutput }} />
        <span style={{ fontSize: "9px", color: T.textSecondary }}>SYNC</span>
      </div>
    </div>
  </NodeWrapper>
);

// ─────────────────────────────────────────────────────────────────────────────
// RegisterNode
// ─────────────────────────────────────────────────────────────────────────────
export const RegisterNode = ({ id, data }) => (
  <NodeWrapper data={data} id={id}>
    <EditableLabel value={data.name} onChange={data.rename} />
    <div>D-FF / REG</div>
    <Handle type="target" position={Position.Left} id="d" />
    <Handle type="source" position={Position.Right} id="q" />
  </NodeWrapper>
);

// ─────────────────────────────────────────────────────────────────────────────
// MemoryNode
// ─────────────────────────────────────────────────────────────────────────────
export const MemoryNode = ({ id, data }) => (
  <NodeWrapper data={data} id={id} customStyle={nodeBox}>
    <div style={{ color: T.blue, fontWeight: "bold" }}><EditableLabel value={data.name} onChange={data.rename} /></div>
    <div style={{ fontSize: "10px", color: "#94a3b8" }}>ROM STORAGE</div>
    <div style={{ display: "flex", justifyContent: "space-between", marginTop: "15px", minHeight: "30px" }}>
      <div style={{ position: "relative", textAlign: "left", paddingLeft: "12px" }}>
        <Handle type="target" position={Position.Left} id="addr" style={{ background: "#38bdf8" }} />
        <span style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "bold" }}>ADDR</span>
      </div>
      <div style={{ position: "relative", textAlign: "right", paddingRight: "12px" }}>
        <Handle type="source" position={Position.Right} id="data" style={{ background: "#10b981" }} />
        <span style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "bold" }}>DATA</span>
      </div>
    </div>
    <div style={{ fontSize: "8px", marginTop: "8px", opacity: 0.5, color: T.textSecondary }}>256 x {data.width || 8} bits</div>
  </NodeWrapper>
);

// ─────────────────────────────────────────────────────────────────────────────
// EncoderNode
// ─────────────────────────────────────────────────────────────────────────────
export const EncoderNode = ({ id, data }) => (
  <NodeWrapper data={data} id={id} customStyle={nodeBox}>
    <div style={{ color: T.blue }}><EditableLabel value={data.name} onChange={data.rename} /></div>
    <div style={{ fontSize: "9px", color: "#94a3b8" }}>ENCODER</div>
    <div style={{ display: "flex", justifyContent: "space-between", marginTop: "15px" }}>
      <div style={{ position: "relative" }}>
        <Handle type="target" position={Position.Left} id="in0" style={{ background: "#38bdf8" }} />
        <span style={{ fontSize: "10px", marginLeft: "10px", color: T.textSecondary }}>BIN</span>
      </div>
      <div style={{ position: "relative" }}>
        <Handle type="source" position={Position.Right} id="out" style={{ background: "#10b981" }} />
        <span style={{ fontSize: "10px", marginRight: "10px", color: T.textSecondary }}>OUT</span>
      </div>
    </div>
  </NodeWrapper>
);

// ─────────────────────────────────────────────────────────────────────────────
// DecoderNode
// ─────────────────────────────────────────────────────────────────────────────
export const DecoderNode = ({ id, data }) => (
  <NodeWrapper data={data} id={id} customStyle={nodeBox}>
    <div style={{ color: T.blue, fontWeight: "bold" }}><EditableLabel value={data.name} onChange={data.rename} /></div>
    <div style={{ fontSize: "9px", color: "#94a3b8" }}>DECODER (1-to-N)</div>
    <div style={{ display: "flex", justifyContent: "space-between", marginTop: "15px" }}>
      <div style={{ position: "relative", textAlign: "left" }}>
        <Handle type="target" position={Position.Left} id="in0" style={{ background: "#38bdf8" }} />
        <span style={{ fontSize: "10px", marginLeft: "10px", color: "#94a3b8" }}>IN</span>
      </div>
      <div style={{ position: "relative", textAlign: "right" }}>
        <Handle type="source" position={Position.Right} id="out" style={{ background: "#10b981" }} />
        <span style={{ fontSize: "10px", marginRight: "10px", color: "#94a3b8" }}>BIN</span>
      </div>
    </div>
  </NodeWrapper>
);

// ─────────────────────────────────────────────────────────────────────────────
// ProbeNode
// ─────────────────────────────────────────────────────────────────────────────
export const ProbeNode = ({ id, data }) => {
  const [displayBase, setDisplayBase] = React.useState("hex");
  return (
    <NodeWrapper data={data} id={id} customStyle={nodeBox}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
        <span style={{ fontSize: "10px", fontWeight: "bold", color: T.textSecondary }}>PROBE</span>
        <select value={displayBase} onChange={(e) => setDisplayBase(e.target.value)}
          style={{ fontSize: "9px", border: "none", background: T.bg2, color: T.blue, cursor: "pointer", borderRadius: T.r4, padding: "2px" }}>
          <option value="bin">BIN</option>
          <option value="hex">HEX</option>
          <option value="dec">DEC</option>
        </select>
      </div>
      <div style={{ padding: "10px", background: T.bg2, border: `1px solid ${T.border2}`, textAlign: "center", fontSize: "16px", fontWeight: "bold", fontFamily: T.fontMono, color: T.green, borderRadius: T.r4, boxShadow: "inset 0 2px 4px rgba(0,0,0,0.5)" }}>
        {formatValue(data.value, displayBase, data.width)}
      </div>
      <Handle type="target" position={Position.Left} id="in" style={{ background: T.sigInput }} />
    </NodeWrapper>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// MuxNode
// ─────────────────────────────────────────────────────────────────────────────
export const MuxNode = ({ id, data }) => {
  const numInputs = Math.max(2, parseInt(data.muxSize) || 2);
  const numSelBits = Math.max(1, Math.ceil(Math.log2(numInputs)));
  return (
    <NodeWrapper data={data} id={id} customStyle={{ ...nodeBox, minWidth: "150px" }}>
      <EditableLabel value={data.name} onChange={data.rename} />
      <div style={{ fontWeight: "bold", color: T.blue, fontSize: "11px" }}>MULTIPLEXER</div>
      <div style={{ margin: "8px 0", fontSize: "10px", color: T.textSecondary }}>
        N:{" "}
        <input type="text" value={data.muxSize ?? "2"} onChange={(e) => data.setMuxSize?.(e.target.value)}
          style={{ width: "40px", textAlign: "center", background: T.bg2, border: `1px solid ${T.border2}`, color: T.blue, borderRadius: T.r4 }} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "10px" }}>
        {Array.from({ length: numInputs }).map((_, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", height: "14px", position: "relative", paddingLeft: "15px" }}>
            <Handle type="target" position={Position.Left} id={`in${i}`} style={{ background: "#38bdf8" }} />
            <span style={{ fontSize: "10px", color: T.textSecondary }}>in{i}</span>
          </div>
        ))}
        {Array.from({ length: numSelBits }).map((_, i) => (
          <div key={`sel${i}`} style={{ display: "flex", alignItems: "center", height: "14px", position: "relative", paddingLeft: "15px", color: "#10b981" }}>
            <Handle type="target" position={Position.Left} id={`sel${i}`} style={{ background: "#10b981" }} />
            <span style={{ fontSize: "10px", fontWeight: "bold" }}>SEL{i}</span>
          </div>
        ))}
      </div>
      <Handle type="source" position={Position.Right} id="out" style={{ top: "35px", background: "#10b981" }} />
    </NodeWrapper>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// FifoNode
// ─────────────────────────────────────────────────────────────────────────────
export const FifoNode = ({ id, data }) => {
  const depth = parseInt(data.fifoDepth) || 16;
  const fillLevel = Math.min(parseInt(data.value) || 0, depth);
  const fillPct = (fillLevel / depth) * 100;
  return (
    <NodeWrapper data={data} id={id} customStyle={{ ...nodeBox, minWidth: "160px" }}>
      <div style={{ color: T.blue, fontWeight: "bold", fontSize: "12px" }}>
        <EditableLabel value={data.name} onChange={data.rename} />
      </div>
      <div style={{ fontSize: "9px", color: T.textSecondary, letterSpacing: "1px", marginBottom: "8px" }}>SYNC FIFO</div>
      <div style={{ background: T.bg2, border: `1px solid ${T.border2}`, borderRadius: T.r6, padding: "6px 8px", marginBottom: "8px", fontSize: "10px", color: T.textSecondary }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
          <span>Depth</span>
          <input type="text" value={data.fifoDepth ?? "16"} onChange={(e) => data.setFifoDepth?.(e.target.value)}
            style={{ width: "40px", textAlign: "center", background: T.bg3, border: `1px solid ${T.border2}`, color: T.blue, borderRadius: T.r4, fontSize: "10px" }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
          <span>Width</span>
          <input type="text" value={data.width ?? "8"} onChange={(e) => data.setWidth?.(e.target.value)}
            style={{ width: "40px", textAlign: "center", background: T.bg3, border: `1px solid ${T.border2}`, color: T.blue, borderRadius: T.r4, fontSize: "10px" }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>AE Thresh</span>
          <input type="text" value={data.aeThresh ?? "4"} onChange={(e) => data.setAeThresh?.(e.target.value)}
            style={{ width: "40px", textAlign: "center", background: T.bg3, border: `1px solid ${T.border2}`, color: T.amber, borderRadius: T.r4, fontSize: "10px" }} />
        </div>
      </div>
      <div style={{ marginBottom: "8px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "9px", color: T.textMuted, marginBottom: "3px" }}>
          <span>FILL</span>
          <span style={{ color: fillPct > 80 ? "#f87171" : "#10b981" }}>{fillLevel}/{depth}</span>
        </div>
        <div style={{ background: T.bg2, borderRadius: "3px", height: "6px", border: `1px solid ${T.border2}`, overflow: "hidden" }}>
          <div style={{ width: `${fillPct}%`, height: "100%", borderRadius: "3px", background: fillPct > 80 ? "#ef4444" : fillPct > 50 ? "#fbbf24" : "#10b981", transition: "width 0.3s ease" }} />
        </div>
      </div>
      <div style={{ display: "flex", gap: "4px", marginBottom: "10px", justifyContent: "center" }}>
        {[
          { label: "FULL",  active: fillPct >= 100, color: T.red },
          { label: "EMPTY", active: fillPct === 0,  color: T.textSecondary },
          { label: "AE",    active: fillLevel <= (parseInt(data.aeThresh) || 4), color: T.amber },
        ].map(({ label, active, color }) => (
          <div key={label} style={{ padding: "2px 6px", borderRadius: "4px", fontSize: "8px", fontWeight: "bold", background: active ? `${color}22` : T.bg4, border: `1px solid ${active ? color : T.border1}`, color: active ? color : "#475569", letterSpacing: "0.5px" }}>
            {label}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {[{ id: "wr_en", label: "WR_EN", color: T.blue }, { id: "din", label: "DIN", color: T.blue }, { id: "rd_en", label: "RD_EN", color: T.blue }].map((p) => (
            <div key={p.id} style={{ position: "relative", paddingLeft: "14px", display: "flex", alignItems: "center" }}>
              <Handle type="target" position={Position.Left} id={p.id} style={{ background: p.color, width: "7px", height: "7px" }} />
              <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>{p.label}</span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {[{ id: "dout", label: "DOUT", color: T.green }, { id: "full", label: "FULL", color: T.red }, { id: "empty", label: "EMPTY", color: T.textSecondary }, { id: "ae", label: "A_EMPTY", color: T.amber }].map((p) => (
            <div key={p.id} style={{ position: "relative", paddingRight: "14px", display: "flex", alignItems: "center", justifyContent: "flex-end" }}>
              <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>{p.label}</span>
              <Handle type="source" position={Position.Right} id={p.id} style={{ background: p.color, width: "7px", height: "7px" }} />
            </div>
          ))}
        </div>
      </div>
    </NodeWrapper>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// SplitterNode
// ─────────────────────────────────────────────────────────────────────────────
export const SplitterNode = ({ id, data }) => {
  const rawRange = (data.bitIndex ?? "0").toString().trim();
  const isRange = rawRange.includes(":");
  const [hiStr, loStr] = isRange ? rawRange.split(":") : [rawRange, rawRange];
  const hi = parseInt(hiStr) || 0;
  const lo = parseInt(loStr) || 0;
  const outW = Math.abs(hi - lo) + 1;

  return (
    <NodeWrapper data={data} id={id} customStyle={nodeBox}>
      <div style={{ color: T.cyan, fontWeight: "700", fontSize: "11px", fontFamily: T.fontUI }}>
        <EditableLabel value={data.name} onChange={data.rename} />
      </div>
      <div style={{ marginTop: "10px", display: "flex", alignItems: "center", gap: "5px" }}>
        <span style={{ fontSize: "9px", color: T.textMuted, fontFamily: T.fontUI, flexShrink: 0 }}>bits</span>
        <input type="text" value={rawRange} onChange={(e) => data.setBitIndex?.(e.target.value)}
          placeholder="7:0 or 3"
          style={{ width: "60px", textAlign: "center", background: T.bg2, border: `1px solid ${T.border2}`, color: T.cyan, borderRadius: T.r4, fontFamily: T.fontMono, fontSize: "11px", padding: "3px 5px", outline: "none" }} />
      </div>
      <div style={{ marginTop: "6px", padding: "2px 8px", background: `${T.cyan}12`, border: `1px solid ${T.cyan}28`, borderRadius: T.r4, fontSize: "9px", color: T.cyan, fontFamily: T.fontMono, textAlign: "center", letterSpacing: "0.5px" }}>
        [{hi}:{lo}] → {outW}b
      </div>
      <Handle type="target" position={Position.Left} id="in" style={{ background: T.sigInput, border: `2px solid ${T.bg2}`, width: "9px", height: "9px" }} />
      <Handle type="source" position={Position.Right} id="out" style={{ background: T.cyan, border: `2px solid ${T.bg2}`, width: "9px", height: "9px" }} />
    </NodeWrapper>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// ConcatenatorNode
// ─────────────────────────────────────────────────────────────────────────────
export const ConcatenatorNode = ({ id, data }) => {
  const numInputs = Math.max(2, parseInt(data.joinerSize) || 2);
  return (
    <NodeWrapper data={data} id={id} customStyle={{ ...nodeBox, minWidth: "150px" }}>
      <div style={{ color: T.blue, fontWeight: "bold" }}><EditableLabel value={data.name} onChange={data.rename} /></div>
      <div style={{ margin: "8px 0", fontSize: "10px", color: T.textSecondary }}>
        Inputs:{" "}
        <input type="text" value={data.joinerSize ?? "2"} onChange={(e) => data.setJoinerSize?.(e.target.value)}
          style={{ width: "40px", textAlign: "center", background: T.bg2, border: `1px solid ${T.border2}`, color: T.blue, borderRadius: T.r4 }} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "10px" }}>
        {Array.from({ length: numInputs }).map((_, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", height: "14px", position: "relative", paddingLeft: "15px" }}>
            <Handle type="target" position={Position.Left} id={`in${i}`} style={{ background: "#38bdf8" }} />
            <span style={{ fontSize: "10px", color: T.textSecondary }}>in{i}</span>
          </div>
        ))}
      </div>
      <Handle type="source" position={Position.Right} id="out" style={{ top: "35px", background: "#10b981" }} />
    </NodeWrapper>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// CombNode
// ─────────────────────────────────────────────────────────────────────────────
export const CombNode = ({ id, data }) => {
  const isSingleInput = data.op === "buf" || data.op === "not";
  return (
    <NodeWrapper data={data} id={id}>
      <EditableLabel value={data.name} onChange={data.rename} />
      <div style={{ fontWeight: "bold", color: "#555" }}>{data.op?.toUpperCase()}</div>
      <Handle type="target" position={Position.Left} id="in0" style={{ top: isSingleInput ? 50 : 40 }} />
      {!isSingleInput && <Handle type="target" position={Position.Left} id="in1" style={{ top: 60 }} />}
      <Handle type="source" position={Position.Right} id="out" style={{ top: 50 }} />
    </NodeWrapper>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// MathNode
// ─────────────────────────────────────────────────────────────────────────────
export const MathNode = ({ id, data }) => {
  const getPorts = (op) => {
    switch (op) {
      case "sine_cos":  return { in: ["theta"], out: ["sin", "cos"] };
      case "div":       return { in: ["num", "den"], out: ["quot"] };
      case "arctan":    return { in: ["y", "x"], out: ["theta"] };
      case "sinh_cosh": return { in: ["theta"], out: ["sinh", "cosh"] };
      case "tanh":      return { in: ["theta"], out: ["tanh"] };
      case "exp":       return { in: ["x"], out: ["e^x"] };
      case "ln":        return { in: ["x"], out: ["ln"] };
      case "sqrt":      return { in: ["x"], out: ["sqrt"] };
      default:          return { in: ["in"], out: ["out"] };
    }
  };
  const ports = getPorts(data.op);
  return (
    <NodeWrapper data={data} id={id} customStyle={mathBox}>
      <div style={{ color: "#007bff", fontWeight: "bold", fontSize: "11px" }}>CORDIC CORE</div>
      <div style={{ fontWeight: "bold", marginBottom: "10px" }}>{data.label}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: "15px" }}>
        {ports.in.map((p) => (
          <div key={p} style={{ position: "relative", textAlign: "left", paddingLeft: "10px" }}>
            <Handle type="target" position={Position.Left} id={p} style={{ background: "#007bff" }} />
            <span style={{ fontSize: "10px" }}>{p}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "15px", position: "absolute", right: 0, top: "40px", width: "100%" }}>
        {ports.out.map((p) => (
          <div key={p} style={{ position: "relative", textAlign: "right", paddingRight: "10px" }}>
            <Handle type="source" position={Position.Right} id={p} style={{ background: "#007bff" }} />
            <span style={{ fontSize: "10px" }}>{p}</span>
          </div>
        ))}
      </div>
    </NodeWrapper>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// FsmStateNode
// ─────────────────────────────────────────────────────────────────────────────
export const FsmStateNode = ({ id, data }) => {
  const outputs = data.fsmOutputs || [];
  const CIRCLE = 110;

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", position: "relative" }}>
      <div style={{ ...stateCircle, width: `${CIRCLE}px`, height: `${CIRCLE}px`, position: "relative", cursor: "default", flexShrink: 0 }}>
        <button style={{ ...deleteBtnStyle, top: "-6px", right: "-6px" }}
          onClick={(e) => { e.stopPropagation(); if (data.onDelete) data.onDelete(id); }}>×</button>
        <div style={{ fontSize: "8px", fontWeight: "700", letterSpacing: "2px", color: T.purple, textTransform: "uppercase", fontFamily: T.fontUI, marginBottom: "2px", opacity: 0.85 }}>STATE</div>
        <div style={{ color: T.textPrimary, fontWeight: "700", fontSize: "13px", fontFamily: T.fontUI, textAlign: "center", lineHeight: 1.2, maxWidth: "86px", wordBreak: "break-word" }}>
          <EditableLabel value={data.name} onChange={data.rename} />
        </div>
        <Handle type="target" position={Position.Left} id="in"
          style={{ background: T.purple, border: `2px solid ${T.bg2}`, width: "10px", height: "10px", left: "-5px", top: "50%", transform: "translateY(-50%)" }} />
        <Handle type="source" position={Position.Right} id="out"
          style={{ background: T.purple, border: `2px solid ${T.bg2}`, width: "10px", height: "10px", right: "-5px", top: "50%", transform: "translateY(-50%)" }} />
      </div>

      {outputs.length > 0 && <div style={{ width: "1px", height: "10px", background: `${T.purple}44`, flexShrink: 0 }} />}

      {outputs.length > 0 && (
        <div style={{ background: T.bg2, border: `1px solid ${T.purple}33`, borderRadius: T.r8, padding: "8px 10px 6px", minWidth: `${CIRCLE + 40}px`, maxWidth: "220px", boxShadow: "0 4px 16px rgba(0,0,0,0.4)", position: "relative" }}>
          <div style={{ fontSize: "8px", fontWeight: "700", letterSpacing: "1.5px", color: T.textMuted, textTransform: "uppercase", textAlign: "center", marginBottom: "6px", fontFamily: T.fontUI }}>Outputs</div>
          {outputs.map((row, i) => (
            <div key={i} style={{ display: "flex", gap: "4px", marginBottom: "5px", alignItems: "center", position: "relative" }}>
              <input value={row.signal} placeholder="signal"
                onChange={(e) => { const u = [...outputs]; u[i] = { ...u[i], signal: e.target.value }; data.setFsmOutputs?.(u); }}
                style={{ flex: 2, padding: "3px 6px", fontSize: "10px", fontFamily: T.fontMono, background: T.bg3, border: `1px solid ${T.border2}`, color: T.blue, borderRadius: T.r4, minWidth: 0, outline: "none" }} />
              <span style={{ color: T.textMuted, fontSize: "11px", flexShrink: 0 }}>=</span>
              <input value={row.value} placeholder="val"
                onChange={(e) => { const u = [...outputs]; u[i] = { ...u[i], value: e.target.value }; data.setFsmOutputs?.(u); }}
                style={{ flex: 1, padding: "3px 6px", fontSize: "10px", fontFamily: T.fontMono, background: T.bg3, border: `1px solid ${T.border2}`, color: T.green, borderRadius: T.r4, minWidth: 0, outline: "none", maxWidth: "48px" }} />
              <button onClick={() => data.setFsmOutputs?.(outputs.filter((_, j) => j !== i))}
                style={{ background: "none", border: "none", color: `${T.red}88`, cursor: "pointer", fontSize: "13px", lineHeight: 1, padding: "0 2px", flexShrink: 0 }}>×</button>
              <Handle type="source" position={Position.Right} id={row.signal || `out_${i}`}
                style={{ background: T.sigOutput, border: `2px solid ${T.bg2}`, width: "9px", height: "9px", right: "-5px", top: "50%", transform: "translateY(-50%)" }} />
            </div>
          ))}
          <button onClick={() => data.setFsmOutputs?.([...outputs, { signal: "", value: "0" }])}
            style={{ width: "100%", marginTop: "2px", padding: "4px", background: "transparent", border: `1px dashed ${T.border1}`, borderRadius: T.r4, color: T.textMuted, fontSize: "10px", cursor: "pointer", textAlign: "center", fontFamily: T.fontUI }}>
            + output
          </button>
        </div>
      )}

      {outputs.length === 0 && (
        <button onClick={() => data.setFsmOutputs?.([{ signal: "", value: "0" }])}
          style={{ marginTop: "6px", padding: "3px 10px", background: "transparent", border: `1px dashed ${T.purple}33`, borderRadius: T.r4, color: `${T.purple}88`, fontSize: "9px", cursor: "pointer", fontFamily: T.fontUI }}>
          + output
        </button>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// PriorityEncoderNode
// ─────────────────────────────────────────────────────────────────────────────
export const PriorityEncoderNode = ({ id, data }) => (
  <NodeWrapper data={data} id={id} customStyle={{ ...nodeBox, minWidth: "165px" }}>
    <div style={{ color: "#a78bfa", fontWeight: "bold", fontSize: "12px" }}>
      <EditableLabel value={data.name} onChange={data.rename} />
    </div>
    <div style={{ fontSize: "9px", color: T.textSecondary, letterSpacing: "1px", marginBottom: "8px" }}>PRIORITY ENCODER</div>
    <div style={{ background: T.bg2, border: `1px solid ${T.border2}`, borderRadius: T.r6, padding: "6px 8px", marginBottom: "10px", fontSize: "10px", color: T.textSecondary }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
        <span>Width</span>
        <input type="text" value={data.width ?? "8"} onChange={(e) => data.setWidth?.(e.target.value)}
          style={{ width: "40px", textAlign: "center", background: T.bg3, border: `1px solid ${T.border2}`, color: T.blue, borderRadius: T.r4, fontSize: "10px" }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>Priority</span>
        <div style={{ display: "flex", borderRadius: T.r4, overflow: "hidden", border: `1px solid ${T.border2}` }}>
          {["MSB", "LSB"].map((lbl, i) => (
            <button key={lbl} onClick={() => data.setLsbPriority?.(i)}
              style={{ padding: "3px 8px", fontSize: "9px", fontWeight: "bold", border: "none", cursor: "pointer", letterSpacing: "0.5px", background: data.lsbPriority === i ? T.purple : T.bg4, color: data.lsbPriority === i ? "#fff" : T.textMuted }}>
              {lbl}
            </button>
          ))}
        </div>
      </div>
    </div>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        <div style={{ position: "relative", paddingLeft: "14px", display: "flex", alignItems: "center" }}>
          <Handle type="target" position={Position.Left} id="data_in" style={{ background: "#a78bfa", width: "7px", height: "7px" }} />
          <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>DATA_IN</span>
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {[{ id: "index", label: "INDEX", color: T.sigOutput }, { id: "valid", label: "VALID", color: T.amber }].map((p) => (
          <div key={p.id} style={{ position: "relative", paddingRight: "14px", display: "flex", alignItems: "center", justifyContent: "flex-end" }}>
            <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>{p.label}</span>
            <Handle type="source" position={Position.Right} id={p.id} style={{ background: p.color, width: "7px", height: "7px" }} />
          </div>
        ))}
      </div>
    </div>
  </NodeWrapper>
);

// ─────────────────────────────────────────────────────────────────────────────
// EdgeDetectorNode
// ─────────────────────────────────────────────────────────────────────────────
export const EdgeDetectorNode = ({ id, data }) => {
  const edgeType = parseInt(data.edgeType ?? 0);
  const labels = ["RISING", "FALLING", "BOTH"];
  const colors = [T.green, T.red, T.cyan];
  return (
    <NodeWrapper data={data} id={id} customStyle={{ ...nodeBox, minWidth: "150px" }}>
      <div style={{ color: T.cyan, fontWeight: "bold", fontSize: "12px", marginBottom: "2px" }}>
        <EditableLabel value={data.name} onChange={data.rename} />
      </div>
      <div style={{ fontSize: "9px", color: T.textSecondary, letterSpacing: "1px", marginBottom: "8px" }}>EDGE DETECTOR</div>
      <div style={{ background: T.bg2, border: `1px solid ${T.border2}`, borderRadius: T.r6, padding: "6px 8px", marginBottom: "10px" }}>
        <div style={{ fontSize: "9px", color: T.textMuted, marginBottom: "4px" }}>EDGE TYPE</div>
        <div style={{ display: "flex", gap: "4px" }}>
          {labels.map((lbl, i) => (
            <button key={i} onClick={() => data.setEdgeType?.(i)}
              style={{ flex: 1, padding: "3px 0", fontSize: "8px", fontWeight: "700", borderRadius: T.r4, cursor: "pointer", letterSpacing: "0.5px", background: edgeType === i ? `${colors[i]}22` : T.bg3, border: `1px solid ${edgeType === i ? colors[i] : T.border1}`, color: edgeType === i ? colors[i] : T.textMuted }}>
              {lbl}
            </button>
          ))}
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <div style={{ paddingLeft: "14px", position: "relative", display: "flex", alignItems: "center" }}>
          <Handle type="target" position={Position.Left} id="signal_in" style={{ background: T.cyan, width: "7px", height: "7px" }} />
          <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>SIG_IN</span>
        </div>
        <div style={{ paddingRight: "14px", position: "relative", display: "flex", alignItems: "center" }}>
          <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>PULSE</span>
          <Handle type="source" position={Position.Right} id="pulse_out" style={{ background: T.green, width: "7px", height: "7px" }} />
        </div>
      </div>
    </NodeWrapper>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// DualPortRamNode
// ─────────────────────────────────────────────────────────────────────────────
export const DualPortRamNode = ({ id, data }) => {
  const dw = data.width || "32";
  const aw = data.addrWidth || "6";
  return (
    <NodeWrapper data={data} id={id} customStyle={{ ...nodeBox, minWidth: "180px" }}>
      <div style={{ color: "#fb923c", fontWeight: "bold", fontSize: "12px", marginBottom: "2px" }}>
        <EditableLabel value={data.name} onChange={data.rename} />
      </div>
      <div style={{ fontSize: "9px", color: T.textSecondary, letterSpacing: "1px", marginBottom: "8px" }}>DUAL-PORT RAM</div>
      <div style={{ background: T.bg2, border: `1px solid ${T.border2}`, borderRadius: T.r6, padding: "6px 8px", marginBottom: "8px", fontSize: "10px", color: T.textSecondary }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
          <span>Data Width</span>
          <input type="text" value={dw} onChange={(e) => data.setWidth?.(e.target.value)}
            style={{ width: "40px", textAlign: "center", background: T.bg3, border: `1px solid ${T.border2}`, color: T.blue, borderRadius: T.r4, fontSize: "10px" }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>Addr Width</span>
          <input type="text" value={aw} onChange={(e) => data.setAddrWidth?.(e.target.value)}
            style={{ width: "40px", textAlign: "center", background: T.bg3, border: `1px solid ${T.border2}`, color: T.amber, borderRadius: T.r4, fontSize: "10px" }} />
        </div>
        <div style={{ fontSize: "9px", color: T.textMuted, marginTop: "4px", textAlign: "center" }}>
          depth = 2^{aw} = {Math.pow(2, parseInt(aw) || 6)}
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {[{ id: "we_a", label: "WE_A", color: T.blue }, { id: "addr_a", label: "ADDR_A", color: T.blue }, { id: "din_a", label: "DIN_A", color: T.blue }, { id: "we_b", label: "WE_B", color: T.purple }, { id: "addr_b", label: "ADDR_B", color: T.purple }, { id: "din_b", label: "DIN_B", color: T.purple }].map((p) => (
            <div key={p.id} style={{ position: "relative", paddingLeft: "14px", display: "flex", alignItems: "center" }}>
              <Handle type="target" position={Position.Left} id={p.id} style={{ background: p.color, width: "7px", height: "7px" }} />
              <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>{p.label}</span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {[{ id: "dout_a", label: "DOUT_A", color: T.green }, { id: "dout_b", label: "DOUT_B", color: T.green }].map((p) => (
            <div key={p.id} style={{ position: "relative", paddingRight: "14px", display: "flex", alignItems: "center", justifyContent: "flex-end" }}>
              <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>{p.label}</span>
              <Handle type="source" position={Position.Right} id={p.id} style={{ background: p.color, width: "7px", height: "7px" }} />
            </div>
          ))}
        </div>
      </div>
    </NodeWrapper>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// CfgCounterNode
// ─────────────────────────────────────────────────────────────────────────────
export const CfgCounterNode = ({ id, data }) => {
  const dir = parseInt(data.countDir ?? 1);
  return (
    <NodeWrapper data={data} id={id} customStyle={{ ...nodeBox, minWidth: "160px" }}>
      <div style={{ color: T.amber, fontWeight: "bold", fontSize: "12px", marginBottom: "2px" }}>
        <EditableLabel value={data.name} onChange={data.rename} />
      </div>
      <div style={{ fontSize: "9px", color: T.textSecondary, letterSpacing: "1px", marginBottom: "8px" }}>CFG COUNTER</div>
      <div style={{ background: T.bg2, border: `1px solid ${T.border2}`, borderRadius: T.r6, padding: "6px 8px", marginBottom: "8px", fontSize: "10px", color: T.textSecondary }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
          <span>Width</span>
          <input type="text" value={data.width ?? "8"} onChange={(e) => data.setWidth?.(e.target.value)}
            style={{ width: "40px", textAlign: "center", background: T.bg3, border: `1px solid ${T.border2}`, color: T.blue, borderRadius: T.r4, fontSize: "10px" }} />
        </div>
        <div style={{ fontSize: "9px", color: T.textMuted, marginBottom: "4px" }}>DIRECTION</div>
        <div style={{ display: "flex", gap: "4px" }}>
          {["DOWN", "UP"].map((lbl, i) => (
            <button key={i} onClick={() => data.setCountDir?.(i)}
              style={{ flex: 1, padding: "3px 0", fontSize: "9px", fontWeight: "700", borderRadius: T.r4, cursor: "pointer", background: dir === i ? `${T.amber}22` : T.bg3, border: `1px solid ${dir === i ? T.amber : T.border1}`, color: dir === i ? T.amber : T.textMuted }}>
              {lbl}
            </button>
          ))}
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {[{ id: "enable", label: "EN", color: T.blue }, { id: "load", label: "LOAD", color: T.blue }, { id: "load_value", label: "LOAD_VAL", color: T.blue }].map((p) => (
            <div key={p.id} style={{ position: "relative", paddingLeft: "14px", display: "flex", alignItems: "center" }}>
              <Handle type="target" position={Position.Left} id={p.id} style={{ background: p.color, width: "7px", height: "7px" }} />
              <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>{p.label}</span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {[{ id: "count", label: "COUNT", color: T.green }, { id: "tc", label: "TC", color: T.amber }].map((p) => (
            <div key={p.id} style={{ position: "relative", paddingRight: "14px", display: "flex", alignItems: "center", justifyContent: "flex-end" }}>
              <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>{p.label}</span>
              <Handle type="source" position={Position.Right} id={p.id} style={{ background: p.color, width: "7px", height: "7px" }} />
            </div>
          ))}
        </div>
      </div>
    </NodeWrapper>
  );
};
export { CustomBlockNode };