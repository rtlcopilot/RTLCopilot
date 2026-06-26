import React from "react";
import { T, nodeBox, deleteBtnStyle } from "../../constants";

const NodeWrapper = ({
  children,
  data,
  id,
  showWidth = true,
  customStyle = nodeBox,
}) => {
  const needsIterations = [
    "sine_cos",
    "arctan",
    "sinh_cosh",
    "tanh",
    "exp",
    "ln",
    "sqrt",
  ].includes(data.op);

  return (
    <div style={{ ...customStyle, position: "relative" }}>
      <button
        style={deleteBtnStyle}
        onClick={(e) => {
          e.stopPropagation();
          if (data.onDelete) data.onDelete(id);
        }}
      >
        ×
      </button>
      {children}

      {showWidth && (
        <div
          style={{
            marginTop: "8px",
            borderTop: `1px solid ${T.border1}`,
            paddingTop: "5px",
            fontSize: "10px",
            color: T.textSecondary,
          }}
        >
          Width:{" "}
          <input
            type="text"
            value={data.width ?? ""}
            onChange={(e) => data.setWidth?.(e.target.value)}
            style={{
              width: "45px",
              textAlign: "center",
              background: T.bg2,
              border: `1px solid ${T.border2}`,
              color: T.blue,
              borderRadius: T.r4,
            }}
          />
          {needsIterations && (
            <div style={{ marginTop: "4px" }}>
              Iter:{" "}
              <input
                type="text"
                value={data.iterations}
                onChange={(e) => data.setIterations?.(e.target.value)}
                style={{
                  width: "30px",
                  textAlign: "center",
                  background: T.bg2,
                  border: `1px solid ${T.border2}`,
                  color: T.blue,
                  borderRadius: T.r4,
                }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default NodeWrapper;
