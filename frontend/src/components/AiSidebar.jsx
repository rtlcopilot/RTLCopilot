import React from "react";
import { T } from "../constants";
import { API_BASE } from "../config";

const AiSidebar = ({
  isOpen, onClose,
  chatHistory, setChatHistory,
  promptValue, setPromptValue,
  aiLoading, setAiLoading,
  aiMode, setAiMode,
  nodes, edges,
  hydrateNode, setNodes, setEdges,
  byokKey,
  _authHeaders,
  setVerilogFiles, setActiveRtlFile, setRtlReady, setCanonicalIR,
}) => {
  if (!isOpen) return null;

  const hasDesign = nodes.length > 0;

  const handleNewCircuit = () => {
    setNodes([]);
    setEdges([]);
    setChatHistory([]);
    setCanonicalIR(null);
    setVerilogFiles({});
    setRtlReady(false);
  };

  const handleSend = async () => {
    if (!promptValue.trim()) return;
    const currentPrompt = promptValue;
    setAiLoading(true);
    setChatHistory((p) => [...p, { role: "user", text: currentPrompt }]);
    setPromptValue("");
    try {
      const headers = await _authHeaders();
      if (aiMode === "ask") {
        const res = await fetch(`${API_BASE}/ai_chat`, {
          method: "POST", headers,
          body: JSON.stringify({
            prompt: currentPrompt,
            history: chatHistory.slice(-6).map((m) => ({ role: m.role, content: m.text })),
            current_nodes: nodes.slice(0, 20).map((n) => ({ id: n.id, type: n.type, name: n.data?.name })),
          }),
        });
        const d = await res.json();
        setChatHistory((p) => [...p, { role: "assistant", text: d.reply || d.explanation || "I couldn't answer that." }]);
      } else {
        const endpoint = hasDesign ? "ai_assist_followup" : "ai_assist";
        const body = { prompt: currentPrompt, current_nodes: nodes, current_edges: edges };

        const res = await fetch(`${API_BASE}/${endpoint}`, {
          method: "POST", headers,
          body: JSON.stringify(body),
        });
        const d = await res.json();

        if (hasDesign && d.add_nodes !== undefined) {
          const removeIds    = new Set(d.remove_node_ids || []);
          const removeEdgeIds = new Set(d.remove_edge_ids || []);
          const updates      = Object.fromEntries((d.update_nodes || []).map((u) => [u.id, u.data_updates]));

          setNodes((prev) => {
            let updated = prev.filter((n) => !removeIds.has(n.id));
            updated = updated.map((n) => updates[n.id] ? { ...n, data: { ...n.data, ...updates[n.id] } } : n);
            const newNodes = (d.add_nodes || []).map((n) => hydrateNode(n));
            return [...updated, ...newNodes];
          });
          setEdges((prev) => {
            let updated = prev.filter((e) => !removeEdgeIds.has(e.id));
            const newEdges = (d.add_edges || []).map((e) => ({
              ...e, type: e.data?.isFsm ? "fsm" : "smoothstep", animated: false,
            }));
            return [...updated, ...newEdges];
          });
          setChatHistory((p) => [...p, { role: "assistant", text: d.explanation || "Canvas updated." }]);
        } else if (d.nodes && d.nodes.length > 0) {
          const hydratedNodes = d.nodes.map((n) => hydrateNode(n));
          const hydratedEdges = d.edges.map((e) => ({
            ...e, type: e.data?.isFsm ? "fsm" : "smoothstep", animated: false,
          }));
          setNodes(hydratedNodes);
          setTimeout(() => setEdges(hydratedEdges), 100);

          if (d.verilog_files && Object.keys(d.verilog_files).length > 0) {
            setVerilogFiles(d.verilog_files);
            setActiveRtlFile("top.v");
            setRtlReady(true);
          }
          if (d.compile_ir) {
            setCanonicalIR(d.compile_ir);
          }

          const issueText = d.ir_issues && d.ir_issues.length > 0
            ? `\n\n⚠️ IR issues detected:\n${d.ir_issues.map((i) => `• ${i}`).join("\n")}`
            : "";
          setChatHistory((p) => [...p, { role: "assistant", text: (d.explanation || "Circuit built.") + issueText }]);
        } else {
          setChatHistory((p) => [...p, { role: "assistant", text: d.explanation || "Could not generate a valid circuit." }]);
        }
      }
    } catch (e) {
      console.error(e);
      setChatHistory((p) => [...p, { role: "assistant", text: "Connection to AI backend failed." }]);
    }
    setAiLoading(false);
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(5,8,15,0.78)", backdropFilter: "blur(8px)", zIndex: 1000, display: "flex", justifyContent: "center", alignItems: "center" }}>
      <div style={{ background: T.bg3, border: `1px solid ${T.border1}`, borderRadius: T.r12, width: "480px", boxShadow: `0 24px 60px rgba(0,0,0,0.6), 0 0 0 1px ${T.border2}`, display: "flex", flexDirection: "column", overflow: "hidden" }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", background: T.bg2, borderBottom: `1px solid ${T.border0}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{ fontSize: "19px" }}>✦</span>
            <span style={{ fontSize: "18px", fontWeight: "600", color: T.textPrimary }}>AI Design Copilot</span>
            <div style={{ display: "flex", borderRadius: T.r4, overflow: "hidden", border: `1px solid ${T.border2}`, marginLeft: "4px" }}>
              {[["build", "✦ Build"], ["ask", "💬 Ask"]].map(([mode, label]) => (
                <button key={mode} onClick={() => setAiMode(mode)}
                  style={{ padding: "3px 10px", border: "none", cursor: "pointer", fontSize: "11px", fontFamily: T.fontUI, background: aiMode === mode ? (mode === "build" ? `${T.violet}33` : `${T.blue}22`) : T.bg3, color: aiMode === mode ? (mode === "build" ? "#c4b5fd" : T.blue) : T.textMuted, fontWeight: aiMode === mode ? "600" : "400" }}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {/* New Circuit button — clears canvas and chat for a fresh start */}
            {hasDesign && aiMode === "build" && (
              <button
                onClick={handleNewCircuit}
                title="Clear canvas and start a new circuit"
                style={{ height: "26px", padding: "0 10px", background: `${T.amber}18`, border: `1px solid ${T.amber}44`, borderRadius: T.r4, color: T.amber, fontSize: "11px", fontWeight: "600", cursor: "pointer", fontFamily: T.fontUI, whiteSpace: "nowrap" }}>
                ✕ New Circuit
              </button>
            )}
            <button onClick={onClose}
              style={{ background: "none", border: "none", cursor: "pointer", color: T.textMuted, fontSize: "22px", lineHeight: 1, padding: "0 2px", transition: "color 0.12s" }}
              onMouseEnter={(e) => (e.currentTarget.style.color = T.red)}
              onMouseLeave={(e) => (e.currentTarget.style.color = T.textMuted)}>✕</button>
          </div>
        </div>

        {aiMode === "ask" && (
          <div style={{ padding: "5px 18px", background: `${T.blue}0f`, borderBottom: `1px solid ${T.blue}22`, fontSize: "11px", color: T.blue, fontFamily: T.fontUI }}>
            💬 Ask mode — no AI credits used
          </div>
        )}

        {hasDesign && aiMode === "build" && (
          <div style={{ padding: "5px 18px", background: `${T.violet}0f`, borderBottom: `1px solid ${T.violet}22`, fontSize: "11px", color: "#c4b5fd", fontFamily: T.fontUI }}>
            ✦ Follow-up mode — describe changes, or click <strong>✕ New Circuit</strong> to start fresh
          </div>
        )}

        {/* Chat history */}
        <div style={{ height: "220px", overflowY: "auto", padding: "16px 18px", display: "flex", flexDirection: "column", gap: "10px", background: T.bg1 }}>
          {chatHistory.map((m, i) => (
            <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
              <span style={{ display: "inline-block", background: m.role === "user" ? `${T.blue}22` : T.bg4, border: `1px solid ${m.role === "user" ? T.blue + "33" : T.border1}`, color: m.role === "user" ? T.blue : T.textPrimary, padding: "8px 12px", borderRadius: T.r8, maxWidth: "82%", fontSize: "13px", lineHeight: "1.55", fontFamily: T.fontUI, whiteSpace: "pre-wrap" }}>
                {m.text}
              </span>
            </div>
          ))}
          {chatHistory.length === 0 && (
            <div style={{ color: T.textMuted, fontSize: "18px", textAlign: "center", marginTop: "60px", fontFamily: T.fontUI }}>
              {aiMode === "build" ? "Describe a circuit to build..." : "Ask anything about RTL design..."}
            </div>
          )}
        </div>

        {/* Input */}
        <div style={{ padding: "14px 18px", background: T.bg2, borderTop: `1px solid ${T.border0}` }}>
          <textarea
            value={promptValue}
            onChange={(e) => setPromptValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder={
              aiMode === "build"
                ? hasDesign
                  ? "e.g. connect the baud counter enable, change FIFO depth to 32..."
                  : "e.g. 4-bit counter with enable and sync reset"
                : "e.g. Why use a register here? What is CDC?"
            }
            style={{ width: "100%", height: "64px", padding: "10px 12px", background: T.bg0, border: `1px solid ${T.border2}`, borderRadius: T.r6, color: T.textPrimary, fontSize: "13px", fontFamily: T.fontUI, lineHeight: "1.5", resize: "none", outline: "none", transition: "border-color 0.12s" }}
            onFocus={(e) => (e.target.style.borderColor = aiMode === "build" ? `${T.violet}55` : `${T.blue}55`)}
            onBlur={(e) => (e.target.style.borderColor = T.border2)}
          />
          <button
            disabled={aiLoading}
            onClick={handleSend}
            style={{ marginTop: "10px", width: "100%", height: "36px", background: aiLoading ? T.bg5 : aiMode === "build" ? `linear-gradient(135deg, ${T.violet}33, ${T.blue}22)` : `${T.blue}18`, border: `1px solid ${aiLoading ? T.border2 : aiMode === "build" ? T.violet + "55" : T.blue + "44"}`, borderRadius: T.r6, color: aiLoading ? T.textMuted : aiMode === "build" ? "#c4b5fd" : T.blue, fontSize: "13px", fontWeight: "600", cursor: aiLoading ? "not-allowed" : "pointer", fontFamily: T.fontUI, transition: "all 0.15s" }}>
            {aiLoading ? "Thinking..." : aiMode === "build" ? (hasDesign ? "✦ Apply Changes" : "✦ Apply to Canvas") : "💬 Ask"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default AiSidebar;