import React, { useState } from "react";
import { T } from "../constants";

const BLOCK_TYPES = [
  {
    id: "combinational",
    label: "Combinational",
    icon: "⚡",
    desc: "Pure logic — outputs depend only on current inputs. No clock needed.",
    examples: "Comparator, adder, multiplexer, threshold detector",
  },
  {
    id: "counter_based",
    label: "Counter",
    icon: "🔢",
    desc: "Internal counter that increments/decrements each clock cycle.",
    examples: "PWM generator, timeout timer, baud rate divider",
  },
  {
    id: "register_based",
    label: "Register",
    icon: "📦",
    desc: "Stores a value and updates it each clock cycle based on a rule.",
    examples: "Accumulator, peak detector, sample-and-hold, pipeline stage",
  },
  {
    id: "shift_based",
    label: "Shift Register",
    icon: "➡️",
    desc: "Shifts data through a chain of stages each clock cycle.",
    examples: "Serial-to-parallel, LFSR, delay line, CRC generator",
  },
];

const COMB_OPS = [
  { value: "add",         label: "Add  (a + b)" },
  { value: "sub",         label: "Subtract  (a - b)" },
  { value: "mul",         label: "Multiply  (a × b)" },
  { value: "and",         label: "Bitwise AND  (a & b)" },
  { value: "or",          label: "Bitwise OR  (a | b)" },
  { value: "xor",         label: "Bitwise XOR  (a ^ b)" },
  { value: "not",         label: "Bitwise NOT  (~a)" },
  { value: "eq",          label: "Equal  (a == b)" },
  { value: "neq",         label: "Not Equal  (a != b)" },
  { value: "lt",          label: "Less Than  (a < b)" },
  { value: "lte",         label: "Less or Equal  (a <= b)" },
  { value: "gt",          label: "Greater Than  (a > b)" },
  { value: "gte",         label: "Greater or Equal  (a >= b)" },
  { value: "mux",         label: "Multiplexer  (sel ? b : a)" },
  { value: "shl",         label: "Shift Left  (a << b)" },
  { value: "shr",         label: "Shift Right  (a >> b)" },
  { value: "concat",      label: "Concatenate  ({a, b})" },
  { value: "sat_add",     label: "Saturating Add" },
  { value: "sat_sub",     label: "Saturating Subtract" },
  { value: "passthrough", label: "Passthrough  (out = a)" },
];

const COUNTER_OUTPUT_MODES = [
  { value: "terminal",    label: "Terminal count pulse (fires when counter hits limit)" },
  { value: "passthrough", label: "Raw counter value" },
  { value: "lt",          label: "Counter < threshold" },
  { value: "lte",         label: "Counter <= threshold" },
  { value: "gt",          label: "Counter > threshold" },
  { value: "gte",         label: "Counter >= threshold" },
  { value: "eq",          label: "Counter == value" },
];

const REGISTER_OUTPUT_MODES = [
  { value: "passthrough", label: "Register value" },
  { value: "eq",          label: "Register == value" },
  { value: "gt",          label: "Register > value" },
  { value: "lt",          label: "Register < value" },
  { value: "gte",         label: "Register >= value" },
  { value: "lte",         label: "Register <= value" },
];

const SHIFT_OUTPUT_MODES = [
  { value: "last_stage",  label: "Last stage output" },
  { value: "full_reg",    label: "Full shift register contents" },
  { value: "stage",       label: "Specific stage index" },
  { value: "xor_all",     label: "XOR of all stages (parity)" },
];


const inputStyle = {
  width: "100%", padding: "8px 10px",
  background: T.bg0, border: `1px solid ${T.border2}`,
  borderRadius: T.r6, color: T.textPrimary,
  fontSize: "13px", fontFamily: T.fontUI,
  outline: "none", boxSizing: "border-box",
};

const labelStyle = {
  display: "block", fontSize: "11px",
  color: T.textMuted, fontFamily: T.fontUI,
  marginBottom: "5px", fontWeight: "600",
  textTransform: "uppercase", letterSpacing: "0.05em",
};

const sectionStyle = {
  background: T.bg2, border: `1px solid ${T.border0}`,
  borderRadius: T.r6, padding: "14px", marginBottom: "12px",
};


function PortRow({ port, onChange, onRemove, showDesc = true }) {
  return (
    <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "6px" }}>
      <input
        placeholder="port_name"
        value={port.name}
        onChange={e => onChange({ ...port, name: e.target.value.replace(/\s/g, "_").toLowerCase() })}
        style={{ ...inputStyle, flex: 2 }}
      />
      <input
        placeholder="width"
        value={port.width}
        onChange={e => onChange({ ...port, width: e.target.value })}
        style={{ ...inputStyle, flex: 1 }}
        title="Bit width (e.g. 1, 8, 16)"
      />
      {showDesc && (
        <input
          placeholder="description (optional)"
          value={port.description || ""}
          onChange={e => onChange({ ...port, description: e.target.value })}
          style={{ ...inputStyle, flex: 3 }}
        />
      )}
      <button onClick={onRemove} style={{
        background: "none", border: "none", cursor: "pointer",
        color: T.textMuted, fontSize: "16px", padding: "0 4px", flexShrink: 0,
      }}>✕</button>
    </div>
  );
}


function OutputConfigRow({ config, outputPorts, inputPorts, modes, onChange, onRemove }) {
  const needsOperandA = config.mode !== "terminal" && config.mode !== "passthrough" && config.mode !== "xor_all" && config.mode !== "full_reg" && config.mode !== "last_stage";
  const needsOperandB = ["add","sub","mul","and","or","xor","shl","shr","concat","eq","neq","lt","lte","gt","gte","sat_add","sat_sub","mux"].includes(config.mode);
  const needsStageIdx = config.mode === "stage";

  return (
    <div style={{ ...sectionStyle, display: "flex", flexDirection: "column", gap: "6px" }}>
      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Output Port</label>
          <select value={config.port} onChange={e => onChange({ ...config, port: e.target.value })}
            style={{ ...inputStyle }}>
            <option value="">Select output...</option>
            {outputPorts.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
        </div>
        <div style={{ flex: 2 }}>
          <label style={labelStyle}>Operation</label>
          <select value={config.mode} onChange={e => onChange({ ...config, mode: e.target.value })}
            style={{ ...inputStyle }}>
            {modes.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </div>
        <button onClick={onRemove} style={{
          background: "none", border: "none", cursor: "pointer",
          color: T.textMuted, fontSize: "16px", padding: "0 4px", marginTop: "18px", flexShrink: 0,
        }}>✕</button>
      </div>
      {needsOperandA && (
        <div style={{ display: "flex", gap: "8px" }}>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>Operand A (port or literal)</label>
            <input value={config.operand_a || config.operand || ""} placeholder="e.g. data_in or 255"
              onChange={e => onChange({ ...config, operand_a: e.target.value, operand: e.target.value })}
              style={inputStyle} />
          </div>
          {needsOperandB && (
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Operand B (port or literal)</label>
              <input value={config.operand_b || ""} placeholder="e.g. threshold or 128"
                onChange={e => onChange({ ...config, operand_b: e.target.value })}
                style={inputStyle} />
            </div>
          )}
        </div>
      )}
      {needsStageIdx && (
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Stage Index</label>
          <input type="number" min="0" value={config.stage_index || 0}
            onChange={e => onChange({ ...config, stage_index: parseInt(e.target.value) || 0 })}
            style={{ ...inputStyle, width: "100px" }} />
        </div>
      )}
    </div>
  );
}


export default function CustomBlockModal({ isOpen, onClose, onBlockSaved, _authHeaders, API_BASE }) {
  const [step, setStep]           = useState(0);
  const [generating, setGenerating] = useState(false);
  const [error, setError]         = useState("");
  const [result, setResult]       = useState(null);
  const [saving, setSaving]       = useState(false);

  const [blockName, setBlockName]       = useState("");
  const [description, setDescription]  = useState("");
  const [blockType, setBlockType]       = useState("");

  const [inputs, setInputs]     = useState([{ name: "", width: "8", description: "" }]);
  const [outputs, setOutputs]   = useState([{ name: "", width: "1", description: "" }]);
  const [internals, setInternals] = useState([]);

  const [outputConfigs, setOutputConfigs] = useState([]);

  const [countDir, setCountDir]           = useState("up");
  const [resetCondition, setResetCondition] = useState("input_port");
  const [resetPort, setResetPort]         = useState("");
  const [resetValue, setResetValue]       = useState("256");

  const [hasEnable, setHasEnable]       = useState(false);
  const [enablePort, setEnablePort]     = useState("");
  const [regResetVal, setRegResetVal]   = useState("0");
  const [feedbackMode, setFeedbackMode] = useState("none");
  const [feedbackPort, setFeedbackPort] = useState("");

  const [shiftDepth, setShiftDepth]       = useState("8");
  const [shiftWidth, setShiftWidth]       = useState("1");
  const [shiftDir, setShiftDir]           = useState("left");
  const [shiftHasEnable, setShiftHasEnable] = useState(true);
  const [shiftEnablePort, setShiftEnablePort] = useState("");
  const [shiftFeedback, setShiftFeedback] = useState("none");
  const [shiftHasLoad, setShiftHasLoad]   = useState(false);
  const [shiftLoadPort, setShiftLoadPort] = useState("");
  const [shiftLoadEnPort, setShiftLoadEnPort] = useState("");

  if (!isOpen) return null;

  const STEPS = ["Identity", "Ports", "Behavior", "Generate"];
  const validPorts = (arr) => arr.filter(p => p.name.trim());

  const addPort = (setter) => setter(prev => [...prev, { name: "", width: "8", description: "" }]);
  const updatePort = (setter, idx, val) => setter(prev => prev.map((p, i) => i === idx ? val : p));
  const removePort = (setter, idx) => setter(prev => prev.filter((_, i) => i !== idx));

  const addOutputConfig = () => {
    const firstOut = validPorts(outputs)[0]?.name || "";
    const defaultMode = blockType === "combinational" ? "passthrough"
      : blockType === "counter_based" ? "terminal"
      : blockType === "shift_based" ? "last_stage" : "passthrough";
    setOutputConfigs(prev => [...prev, { port: firstOut, mode: defaultMode, operand_a: "", operand_b: "", operand: "" }]);
  };

  const buildBehaviourText = () => {
    if (blockType === "combinational") {
      return outputConfigs.map(c => `${c.port} = ${c.operand_a || "a"} ${c.mode} ${c.operand_b || "b"}`).join("; ") || description;
    }
    if (blockType === "counter_based") return `${countDir} counter, reset: ${resetCondition}. ${description}`;
    if (blockType === "register_based") return `register with feedback=${feedbackMode}. ${description}`;
    if (blockType === "shift_based") return `shift register depth=${shiftDepth} dir=${shiftDir}. ${description}`;
    return description;
  };

  const buildConfig = () => {
    if (blockType === "combinational") return { outputs: outputConfigs };
    if (blockType === "counter_based") return {
      count_dir: countDir, reset_condition: resetCondition,
      reset_port: resetPort, reset_value: parseInt(resetValue) || 0,
      outputs: outputConfigs,
    };
    if (blockType === "register_based") return {
      has_enable: hasEnable, enable_port: enablePort,
      reset_value: regResetVal, feedback_mode: feedbackMode,
      feedback_port: feedbackPort, outputs: outputConfigs,
    };
    if (blockType === "shift_based") return {
      shift_width: parseInt(shiftWidth) || 1,
      depth: parseInt(shiftDepth) || 8,
      shift_dir: shiftDir,
      has_enable: shiftHasEnable, enable_port: shiftEnablePort,
      feedback_mode: shiftFeedback,
      has_load: shiftHasLoad, load_port: shiftLoadPort,
      load_en_port: shiftLoadEnPort, outputs: outputConfigs,
    };
    return {};
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setError("");
    setResult(null);
    try {
      const headers = await _authHeaders();
      const body = {
        name:             blockName.trim().replace(/\s+/g, "_"),
        description,
        inputs:           validPorts(inputs),
        outputs:          validPorts(outputs),
        internal_signals: validPorts(internals),
        behaviour:        buildBehaviourText(),
        config:           buildConfig(),
      };
      const res = await fetch(`${API_BASE}/generate_custom_block`, {
        method: "POST", headers, body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.status !== "ok") {
        setError(data.error || "Generation failed.");
      } else {
        setResult(data);
        setStep(3);
      }
    } catch (e) {
      setError("Network error. Please try again.");
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async () => {
    if (!result) return;
    setSaving(true);
    setError("");
    try {
      const headers = await _authHeaders();
      const saveRes = await fetch(`${API_BASE}/custom_blocks`, {
        method: "POST", headers,
        body: JSON.stringify({
          name:        result.schema.name,
          description,
          block_schema: result.schema,
          verilog:     result.verilog,
          ports:       [...validPorts(inputs).map(p => ({ ...p, dir: "input" })),
                        ...validPorts(outputs).map(p => ({ ...p, dir: "output" }))],
          block_type:  blockType,
        }),
      });
      const saveData = await saveRes.json();
      if (saveData.status !== "ok") {
        setError(saveData.error || "Failed to save.");
        return;
      }
      onBlockSaved({
        id:          saveData.id,
        name:        result.schema.name,
        description,
        ports:       [...validPorts(inputs).map(p => ({ ...p, dir: "input" })),
                      ...validPorts(outputs).map(p => ({ ...p, dir: "output" }))],
        block_type:  blockType,
        schema:      result.schema,
        verilog:     result.verilog,
      });
      handleClose();
    } catch (e) {
      setError("Network error while saving.");
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => {
    setStep(0); setError(""); setResult(null); setGenerating(false); setSaving(false);
    setBlockName(""); setDescription(""); setBlockType("");
    setInputs([{ name: "", width: "8", description: "" }]);
    setOutputs([{ name: "", width: "1", description: "" }]);
    setInternals([]); setOutputConfigs([]);
    onClose();
  };

  const canProceed = () => {
    if (step === 0) return blockName.trim().length > 0 && blockType;
    if (step === 1) return validPorts(inputs).length > 0 && validPorts(outputs).length > 0;
    if (step === 2) return outputConfigs.length > 0 && outputConfigs.every(c => c.port);
    return true;
  };

  const getModes = () => {
    if (blockType === "combinational") return COMB_OPS;
    if (blockType === "counter_based") return COUNTER_OUTPUT_MODES;
    if (blockType === "shift_based") return SHIFT_OUTPUT_MODES;
    return REGISTER_OUTPUT_MODES;
  };

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(5,8,15,0.85)",
      backdropFilter: "blur(8px)", zIndex: 2000,
      display: "flex", justifyContent: "center", alignItems: "center",
    }}>
      <div style={{
        background: T.bg3, border: `1px solid ${T.border1}`,
        borderRadius: T.r12, width: "600px", maxHeight: "88vh",
        boxShadow: "0 24px 60px rgba(0,0,0,0.6)",
        display: "flex", flexDirection: "column", overflow: "hidden",
      }}>

        {/* Header */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "16px 20px", background: T.bg2,
          borderBottom: `1px solid ${T.border0}`, flexShrink: 0,
        }}>
          <div>
            <div style={{ fontSize: "15px", fontWeight: "700", color: T.textPrimary, fontFamily: T.fontUI }}>
              Create Custom Block
            </div>
            <div style={{ fontSize: "12px", color: T.textMuted, fontFamily: T.fontUI, marginTop: "2px" }}>
              Step {step + 1} of 4 — {STEPS[step]}
            </div>
          </div>
          <button onClick={handleClose} style={{
            background: "none", border: "none", cursor: "pointer",
            color: T.textMuted, fontSize: "20px",
          }}>✕</button>
        </div>

        {/* Step indicators */}
        <div style={{
          display: "flex", padding: "12px 20px", gap: "6px",
          background: T.bg2, borderBottom: `1px solid ${T.border0}`, flexShrink: 0,
        }}>
          {STEPS.map((s, i) => (
            <div key={s} style={{ flex: 1, display: "flex", alignItems: "center", gap: "6px" }}>
              <div style={{
                width: "22px", height: "22px", borderRadius: "50%",
                background: i < step ? T.green : i === step ? T.blue : T.border2,
                color: i <= step ? "#fff" : T.textMuted,
                fontSize: "11px", fontWeight: "700", fontFamily: T.fontUI,
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0,
              }}>
                {i < step ? "✓" : i + 1}
              </div>
              <span style={{
                fontSize: "11px", fontFamily: T.fontUI,
                color: i === step ? T.textPrimary : T.textMuted,
                fontWeight: i === step ? "600" : "400",
              }}>{s}</span>
              {i < STEPS.length - 1 && (
                <div style={{ flex: 1, height: "1px", background: i < step ? T.green : T.border1 }} />
              )}
            </div>
          ))}
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "20px" }}>

          {/* ── Step 0: Identity ── */}
          {step === 0 && (
            <div>
              <div style={{ marginBottom: "16px" }}>
                <label style={labelStyle}>Block Name</label>
                <input value={blockName} onChange={e => setBlockName(e.target.value)}
                  placeholder="e.g. saturating_adder" style={inputStyle} />
                <div style={{ fontSize: "11px", color: T.textMuted, fontFamily: T.fontUI, marginTop: "4px" }}>
                  Snake_case, no spaces. This becomes the Verilog module name.
                </div>
              </div>
              <div style={{ marginBottom: "20px" }}>
                <label style={labelStyle}>Description</label>
                <textarea value={description} onChange={e => setDescription(e.target.value)}
                  placeholder="One or two sentences describing what this block does."
                  rows={2}
                  style={{ ...inputStyle, resize: "vertical", lineHeight: "1.5" }} />
              </div>
              <div>
                <label style={labelStyle}>Block Type</label>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                  {BLOCK_TYPES.map(bt => (
                    <button key={bt.id} onClick={() => setBlockType(bt.id)} style={{
                      textAlign: "left", padding: "12px",
                      background: blockType === bt.id ? `${T.blue}18` : T.bg2,
                      border: `1px solid ${blockType === bt.id ? T.blue + "66" : T.border1}`,
                      borderRadius: T.r6, cursor: "pointer",
                      transition: "all 0.15s",
                    }}>
                      <div style={{ fontSize: "18px", marginBottom: "4px" }}>{bt.icon}</div>
                      <div style={{
                        fontSize: "13px", fontWeight: "600", fontFamily: T.fontUI,
                        color: blockType === bt.id ? T.blue : T.textPrimary,
                        marginBottom: "3px",
                      }}>{bt.label}</div>
                      <div style={{ fontSize: "11px", color: T.textMuted, fontFamily: T.fontUI, lineHeight: "1.4" }}>
                        {bt.desc}
                      </div>
                      <div style={{ fontSize: "10px", color: T.textMuted, fontFamily: T.fontMono, marginTop: "4px" }}>
                        {bt.examples}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── Step 1: Ports ── */}
          {step === 1 && (
            <div>
              <div style={{ marginBottom: "20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                  <label style={{ ...labelStyle, margin: 0 }}>Input Ports</label>
                  <button onClick={() => addPort(setInputs)} style={{
                    fontSize: "12px", color: T.blue, background: "none",
                    border: "none", cursor: "pointer", fontFamily: T.fontUI,
                  }}>+ Add Input</button>
                </div>
                <div style={{ fontSize: "11px", color: T.textMuted, fontFamily: T.fontUI, marginBottom: "8px" }}>
                  clk and rst are implicit — don't add them here.
                </div>
                {inputs.map((p, i) => (
                  <PortRow key={i} port={p}
                    onChange={val => updatePort(setInputs, i, val)}
                    onRemove={() => removePort(setInputs, i)} />
                ))}
              </div>

              <div style={{ marginBottom: "20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                  <label style={{ ...labelStyle, margin: 0 }}>Output Ports</label>
                  <button onClick={() => addPort(setOutputs)} style={{
                    fontSize: "12px", color: T.blue, background: "none",
                    border: "none", cursor: "pointer", fontFamily: T.fontUI,
                  }}>+ Add Output</button>
                </div>
                {outputs.map((p, i) => (
                  <PortRow key={i} port={p}
                    onChange={val => updatePort(setOutputs, i, val)}
                    onRemove={() => removePort(setOutputs, i)} />
                ))}
              </div>

              {(blockType === "counter_based" || blockType === "register_based" || blockType === "shift_based") && (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                    <label style={{ ...labelStyle, margin: 0 }}>Internal Signals (optional)</label>
                    <button onClick={() => addPort(setInternals)} style={{
                      fontSize: "12px", color: T.blue, background: "none",
                      border: "none", cursor: "pointer", fontFamily: T.fontUI,
                    }}>+ Add</button>
                  </div>
                  <div style={{ fontSize: "11px", color: T.textMuted, fontFamily: T.fontUI, marginBottom: "8px" }}>
                    Internal registers or signals (e.g. the counter register). Helps determine bit widths.
                  </div>
                  {internals.map((p, i) => (
                    <PortRow key={i} port={p}
                      onChange={val => updatePort(setInternals, i, val)}
                      onRemove={() => removePort(setInternals, i)} />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Step 2: Behavior ── */}
          {step === 2 && (
            <div>
              {/* Counter config */}
              {blockType === "counter_based" && (
                <div style={sectionStyle}>
                  <label style={labelStyle}>Counter Settings</label>
                  <div style={{ display: "flex", gap: "12px", marginBottom: "10px" }}>
                    <div style={{ flex: 1 }}>
                      <label style={labelStyle}>Count Direction</label>
                      <select value={countDir} onChange={e => setCountDir(e.target.value)} style={inputStyle}>
                        <option value="up">Up (increments)</option>
                        <option value="down">Down (decrements)</option>
                      </select>
                    </div>
                    <div style={{ flex: 1 }}>
                      <label style={labelStyle}>Reset Condition</label>
                      <select value={resetCondition} onChange={e => setResetCondition(e.target.value)} style={inputStyle}>
                        <option value="input_port">Input port sets the limit</option>
                        <option value="fixed_value">Fixed value</option>
                        <option value="free_running">Free running (no reset)</option>
                      </select>
                    </div>
                  </div>
                  {resetCondition === "input_port" && (
                    <div>
                      <label style={labelStyle}>Limit Input Port Name</label>
                      <select value={resetPort} onChange={e => setResetPort(e.target.value)} style={inputStyle}>
                        <option value="">Select input...</option>
                        {validPorts(inputs).map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
                      </select>
                    </div>
                  )}
                  {resetCondition === "fixed_value" && (
                    <div>
                      <label style={labelStyle}>Terminal Count Value</label>
                      <input value={resetValue} onChange={e => setResetValue(e.target.value)}
                        placeholder="e.g. 256" style={{ ...inputStyle, width: "150px" }} />
                    </div>
                  )}
                </div>
              )}

              {/* Register config */}
              {blockType === "register_based" && (
                <div style={sectionStyle}>
                  <label style={labelStyle}>Register Settings</label>
                  <div style={{ display: "flex", gap: "12px", marginBottom: "10px" }}>
                    <div style={{ flex: 1 }}>
                      <label style={labelStyle}>Feedback Mode</label>
                      <select value={feedbackMode} onChange={e => setFeedbackMode(e.target.value)} style={inputStyle}>
                        <option value="none">None (plain register)</option>
                        <option value="add">Accumulate (reg = reg + input)</option>
                        <option value="sub">Subtract (reg = reg - input)</option>
                        <option value="max">Peak max (reg = max(reg, input))</option>
                        <option value="min">Running min (reg = min(reg, input))</option>
                      </select>
                    </div>
                    <div style={{ flex: 1 }}>
                      <label style={labelStyle}>Reset Value</label>
                      <input value={regResetVal} onChange={e => setRegResetVal(e.target.value)}
                        placeholder="0" style={inputStyle} />
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "12px" }}>
                    <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", fontSize: "13px", color: T.textSecondary, fontFamily: T.fontUI }}>
                      <input type="checkbox" checked={hasEnable} onChange={e => setHasEnable(e.target.checked)} />
                      Has clock enable
                    </label>
                  </div>
                  {hasEnable && (
                    <div style={{ marginTop: "8px" }}>
                      <label style={labelStyle}>Enable Port</label>
                      <select value={enablePort} onChange={e => setEnablePort(e.target.value)} style={inputStyle}>
                        <option value="">Select input...</option>
                        {validPorts(inputs).map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
                      </select>
                    </div>
                  )}
                  {feedbackMode !== "none" && (
                    <div style={{ marginTop: "8px" }}>
                      <label style={labelStyle}>Feedback Input Port</label>
                      <select value={feedbackPort} onChange={e => setFeedbackPort(e.target.value)} style={inputStyle}>
                        <option value="">Select input...</option>
                        {validPorts(inputs).map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
                      </select>
                    </div>
                  )}
                </div>
              )}

              {/* Shift config */}
              {blockType === "shift_based" && (
                <div style={sectionStyle}>
                  <label style={labelStyle}>Shift Register Settings</label>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px", marginBottom: "10px" }}>
                    <div>
                      <label style={labelStyle}>Stages (depth)</label>
                      <input type="number" min="1" value={shiftDepth} onChange={e => setShiftDepth(e.target.value)} style={inputStyle} />
                    </div>
                    <div>
                      <label style={labelStyle}>Stage Width (bits)</label>
                      <input type="number" min="1" value={shiftWidth} onChange={e => setShiftWidth(e.target.value)} style={inputStyle} />
                    </div>
                    <div>
                      <label style={labelStyle}>Shift Direction</label>
                      <select value={shiftDir} onChange={e => setShiftDir(e.target.value)} style={inputStyle}>
                        <option value="left">Left (MSB first)</option>
                        <option value="right">Right (LSB first)</option>
                      </select>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "16px", marginBottom: "10px" }}>
                    <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", fontSize: "13px", color: T.textSecondary, fontFamily: T.fontUI }}>
                      <input type="checkbox" checked={shiftHasEnable} onChange={e => setShiftHasEnable(e.target.checked)} />
                      Has shift enable
                    </label>
                    <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", fontSize: "13px", color: T.textSecondary, fontFamily: T.fontUI }}>
                      <input type="checkbox" checked={shiftHasLoad} onChange={e => setShiftHasLoad(e.target.checked)} />
                      Has parallel load
                    </label>
                  </div>
                  <div style={{ display: "flex", gap: "10px" }}>
                    {shiftHasEnable && (
                      <div style={{ flex: 1 }}>
                        <label style={labelStyle}>Enable Port</label>
                        <select value={shiftEnablePort} onChange={e => setShiftEnablePort(e.target.value)} style={inputStyle}>
                          <option value="">Select...</option>
                          {validPorts(inputs).map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
                        </select>
                      </div>
                    )}
                    <div style={{ flex: 1 }}>
                      <label style={labelStyle}>Feedback Mode</label>
                      <select value={shiftFeedback} onChange={e => setShiftFeedback(e.target.value)} style={inputStyle}>
                        <option value="none">None</option>
                        <option value="xor">XOR feedback (LFSR)</option>
                      </select>
                    </div>
                  </div>
                  {shiftHasLoad && (
                    <div style={{ display: "flex", gap: "10px", marginTop: "8px" }}>
                      <div style={{ flex: 1 }}>
                        <label style={labelStyle}>Load Data Port</label>
                        <select value={shiftLoadPort} onChange={e => setShiftLoadPort(e.target.value)} style={inputStyle}>
                          <option value="">Select...</option>
                          {validPorts(inputs).map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
                        </select>
                      </div>
                      <div style={{ flex: 1 }}>
                        <label style={labelStyle}>Load Enable Port</label>
                        <select value={shiftLoadEnPort} onChange={e => setShiftLoadEnPort(e.target.value)} style={inputStyle}>
                          <option value="">Select...</option>
                          {validPorts(inputs).map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
                        </select>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Output logic — all types */}
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                  <div>
                    <label style={{ ...labelStyle, margin: 0 }}>Output Logic</label>
                    <div style={{ fontSize: "11px", color: T.textMuted, fontFamily: T.fontUI, marginTop: "2px" }}>
                      Define how each output port is driven.
                    </div>
                  </div>
                  <button onClick={addOutputConfig} style={{
                    fontSize: "12px", color: T.blue, background: "none",
                    border: "none", cursor: "pointer", fontFamily: T.fontUI,
                  }}>+ Add Output Rule</button>
                </div>
                {outputConfigs.length === 0 && (
                  <div style={{ textAlign: "center", padding: "20px", color: T.textMuted, fontSize: "13px", fontFamily: T.fontUI }}>
                    Click "+ Add Output Rule" to define each output port's behavior.
                  </div>
                )}
                {outputConfigs.map((cfg, i) => (
                  <OutputConfigRow
                    key={i} config={cfg}
                    outputPorts={validPorts(outputs)}
                    inputPorts={validPorts(inputs)}
                    modes={getModes()}
                    onChange={val => setOutputConfigs(prev => prev.map((c, j) => j === i ? val : c))}
                    onRemove={() => setOutputConfigs(prev => prev.filter((_, j) => j !== i))}
                  />
                ))}
              </div>
            </div>
          )}

          {/* ── Step 3: Result ── */}
          {step === 3 && result && (
            <div>
              <div style={{
                background: `${T.green}18`, border: `1px solid ${T.green}44`,
                borderRadius: T.r6, padding: "12px 14px", marginBottom: "16px",
                display: "flex", alignItems: "center", gap: "10px",
              }}>
                <span style={{ fontSize: "18px" }}>✅</span>
                <div>
                  <div style={{ fontSize: "13px", fontWeight: "600", color: T.green, fontFamily: T.fontUI }}>
                    Block generated and verified
                  </div>
                  <div style={{ fontSize: "11px", color: T.textMuted, fontFamily: T.fontUI }}>
                    iverilog syntax check passed. Ready to save.
                  </div>
                </div>
              </div>
              <div style={{ marginBottom: "12px" }}>
                <label style={labelStyle}>Generated Verilog</label>
                <pre style={{
                  background: T.bg0, border: `1px solid ${T.border1}`,
                  borderRadius: T.r6, padding: "12px", fontSize: "11px",
                  fontFamily: T.fontMono, color: T.textSecondary,
                  overflowX: "auto", maxHeight: "260px", overflowY: "auto",
                  whiteSpace: "pre", margin: 0,
                }}>
                  {result.verilog}
                </pre>
              </div>
              <div style={{ marginBottom: "12px" }}>
                <label style={labelStyle}>Ports</label>
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                  {result.schema?.ports?.map((p, i) => (
                    <span key={i} style={{
                      fontSize: "11px", fontFamily: T.fontMono,
                      background: p.dir === "input" ? `${T.blue}18` : `${T.green}18`,
                      border: `1px solid ${p.dir === "input" ? T.blue + "33" : T.green + "33"}`,
                      borderRadius: "4px", padding: "3px 8px",
                      color: p.dir === "input" ? T.blue : T.green,
                    }}>
                      {p.dir === "input" ? "→" : "←"} {p.name} [{p.width}]
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {error && (
            <div style={{
              background: `${T.red}18`, border: `1px solid ${T.red}44`,
              borderRadius: T.r6, padding: "10px 12px", marginTop: "12px",
              fontSize: "12px", color: T.red, fontFamily: T.fontUI,
            }}>
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "14px 20px", background: T.bg2,
          borderTop: `1px solid ${T.border0}`, flexShrink: 0,
        }}>
          <button
            onClick={() => step > 0 && step < 3 ? setStep(s => s - 1) : handleClose()}
            style={{
              height: "34px", padding: "0 16px",
              background: "none", border: `1px solid ${T.border2}`,
              borderRadius: T.r6, color: T.textMuted,
              fontSize: "13px", cursor: "pointer", fontFamily: T.fontUI,
            }}>
            {step === 0 ? "Cancel" : step === 3 ? "Close" : "Back"}
          </button>

          <div style={{ display: "flex", gap: "8px" }}>
            {step < 2 && (
              <button
                onClick={() => setStep(s => s + 1)}
                disabled={!canProceed()}
                style={{
                  height: "34px", padding: "0 20px",
                  background: canProceed() ? `${T.blue}22` : T.border2,
                  border: `1px solid ${canProceed() ? T.blue + "55" : T.border2}`,
                  borderRadius: T.r6,
                  color: canProceed() ? T.blue : T.textMuted,
                  fontSize: "13px", fontWeight: "600", cursor: canProceed() ? "pointer" : "not-allowed",
                  fontFamily: T.fontUI,
                }}>
                Next →
              </button>
            )}
            {step === 2 && (
              <button
                onClick={handleGenerate}
                disabled={!canProceed() || generating}
                style={{
                  height: "34px", padding: "0 20px",
                  background: canProceed() ? `${T.blue}22` : T.border2,
                  border: `1px solid ${canProceed() ? T.blue + "55" : T.border2}`,
                  borderRadius: T.r6,
                  color: canProceed() ? T.blue : T.textMuted,
                  fontSize: "13px", fontWeight: "600", cursor: canProceed() ? "pointer" : "not-allowed",
                  fontFamily: T.fontUI,
                }}>
                {generating ? "Generating..." : "Generate Block ⚡"}
              </button>
            )}
            {step === 3 && result && (
              <button
                onClick={handleSave}
                disabled={saving}
                style={{
                  height: "34px", padding: "0 20px",
                  background: `${T.green}22`,
                  border: `1px solid ${T.green}55`,
                  borderRadius: T.r6, color: T.green,
                  fontSize: "13px", fontWeight: "600",
                  cursor: saving ? "not-allowed" : "pointer",
                  fontFamily: T.fontUI,
                }}>
                {saving ? "Saving..." : "Save to My Blocks ✓"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}