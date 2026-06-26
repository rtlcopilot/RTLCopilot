import React from "react";
import { getBezierPath, BaseEdge, EdgeLabelRenderer } from "reactflow";
import { T } from "../../constants";

const FsmEdge = ({
  id, sourceX, sourceY, targetX, targetY,
  sourcePosition, targetPosition,
  data, markerEnd, style,
}) => {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX, sourceY, sourcePosition,
    targetX, targetY, targetPosition,
  });
  const condition = data?.condition ?? "1";
  const isEditing = data?.isEditing ?? false;

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={style} />
      <EdgeLabelRenderer>
        <div
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: "all",
            zIndex: 10,
          }}
          className="nodrag nopan"
          onDoubleClick={(e) => {
            e.stopPropagation();
            window.dispatchEvent(new CustomEvent("fsm-edge-edit", { detail: id }));
          }}
        >
          {isEditing ? (
            <input
              autoFocus
              defaultValue={condition}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === "Escape") e.target.blur();
              }}
              onBlur={(e) => {
                const val = e.target.value.trim() || "1";
                window.dispatchEvent(new CustomEvent("fsm-edge-done", { detail: { id, val } }));
              }}
              style={{
                background: "#0b1220",
                border: `1.5px solid ${T.purple}`,
                borderRadius: "5px",
                padding: "3px 10px",
                fontFamily: T.fontMono,
                fontSize: "11px",
                color: T.textPrimary,
                outline: "none",
                minWidth: "110px",
                maxWidth: "200px",
                textAlign: "center",
                boxShadow: `0 0 0 3px ${T.purple}22, 0 4px 16px rgba(0,0,0,0.7)`,
              }}
            />
          ) : (
            <div
              style={{
                background: `${T.bg2}ee`,
                border: `1px solid ${T.purple}55`,
                borderRadius: "4px",
                padding: "2px 8px",
                fontSize: "10px",
                fontFamily: T.fontMono,
                color: T.textPrimary,
                cursor: "default",
                userSelect: "none",
                whiteSpace: "nowrap",
              }}
            >
              {condition}
            </div>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
};

export default FsmEdge;
