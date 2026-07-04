import React, { useState } from "react";
import { T } from "../../constants";

const EditableLabel = ({ value, onChange }) => {
  const [edit, setEdit] = useState(false);
  const [text, setText] = useState(value);

  return edit ? (
    <input
      value={text}
      autoFocus
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
        setEdit(false);
        if (onChange) onChange(text);
      }}
      onKeyDown={(e) => e.key === "Enter" && e.target.blur()}
      style={{
        width: "90%",
        background: T.bg2,
        color: T.textPrimary,
        border: `1px solid ${T.border2}`,
        borderRadius: "4px",
        padding: "2px 6px",
        fontSize: "inherit",
        fontFamily: T.fontUI,
        outline: "none",
      }}
    />
  ) : (
    <strong onDoubleClick={() => setEdit(true)} style={{ cursor: "text" }}>
      {value}
    </strong>
  );
};

export default EditableLabel;