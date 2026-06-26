import React from "react";
import { Handle, Position } from "reactflow";
import { T, nodeBox } from "../../constants";
import EditableLabel from "../shared/EditableLabel";
import NodeWrapper from "../shared/NodeWrapper";

// ─────────────────────────────────────────────────────────────────────────────
// CustomBlockNode
// Renders user-created custom blocks from the My Blocks library.
// Ports are driven dynamically from data.customPorts.
// ─────────────────────────────────────────────────────────────────────────────
export const CustomBlockNode = ({ id, data }) => {
  const ports       = data.customPorts || [];
  const inputPorts  = ports.filter(p => p.dir === "input");
  const outputPorts = ports.filter(p => p.dir === "output");

  const portColor = (p) => String(p.width) === "1" ? T.amber : T.green;

  return (
    <NodeWrapper data={data} id={id} customStyle={{ ...nodeBox, minWidth: "160px" }}>
      <div style={{ color: "#a78bfa", fontWeight: "bold", fontSize: "12px", marginBottom: "2px" }}>
        <EditableLabel value={data.name} onChange={data.rename} />
      </div>
      <div style={{ fontSize: "9px", color: T.textSecondary, letterSpacing: "1px", marginBottom: "8px", textTransform: "uppercase" }}>
        CUSTOM BLOCK
      </div>
      {data.description && (
        <div style={{ fontSize: "9px", color: T.textMuted, fontFamily: T.fontUI, marginBottom: "8px", lineHeight: "1.4", maxWidth: "140px", wordBreak: "break-word" }}>
          {data.description.length > 60 ? data.description.slice(0, 60) + "\u2026" : data.description}
        </div>
      )}
      <div style={{ background: T.bg2, border: `1px solid ${T.border2}`, borderRadius: T.r6, padding: "4px 8px", marginBottom: "8px", display: "flex", justifyContent: "space-between", fontSize: "9px", color: T.textMuted, fontFamily: T.fontMono }}>
        <span>{inputPorts.length} in</span>
        <span style={{ color: T.border2 }}>·</span>
        <span>{outputPorts.length} out</span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {inputPorts.map((p) => (
            <div key={p.name} style={{ position: "relative", paddingLeft: "14px", display: "flex", alignItems: "center" }}>
              <Handle type="target" position={Position.Left} id={p.name} style={{ background: portColor(p), width: "7px", height: "7px" }} />
              <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>
                {p.name.toUpperCase()}{String(p.width) !== "1" && <span style={{ color: T.textMuted }}> [{p.width}]</span>}
              </span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {outputPorts.map((p) => (
            <div key={p.name} style={{ position: "relative", paddingRight: "14px", display: "flex", alignItems: "center", justifyContent: "flex-end" }}>
              <span style={{ fontSize: "9px", color: T.textSecondary, fontFamily: T.fontMono }}>
                {p.name.toUpperCase()}{String(p.width) !== "1" && <span style={{ color: T.textMuted }}> [{p.width}]</span>}
              </span>
              <Handle type="source" position={Position.Right} id={p.name} style={{ background: portColor(p), width: "7px", height: "7px" }} />
            </div>
          ))}
        </div>
      </div>
    </NodeWrapper>
  );
};

export default CustomBlockNode;
