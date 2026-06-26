import React, { useState } from "react";

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
      style={{ width: "90%" }}
    />
  ) : (
    <strong onDoubleClick={() => setEdit(true)} style={{ cursor: "text" }}>
      {value}
    </strong>
  );
};

export default EditableLabel;
