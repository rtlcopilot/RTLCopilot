import React from "react";
import { T } from "../constants";

const BottomPanel = ({
  showBottomPanel, setShowBottomPanel,
  bottomPanelHeight, setBottomPanelHeight,
  activeTab, setActiveTab,
  verilogFiles, activeRtlFile, setActiveRtlFile,
  testbenchCode,
  tbSteps, setTbSteps,
  tbConfig, updateTbConfig,
  tbConfigDirty,
  nodes,

  drcLogs,
  verifyHistory, verifyLoading, verifyAutoLoading,
  verifyExpanded, setVerifyExpanded,
  verifyRandomWarning, setVerifyRandomWarning,
  verifyIntent, setVerifyIntent,
  runVerification, runAutoVerification,
  setCurrentPage,
}) => {
  if (!showBottomPanel) return null;

  return (
    <div style={{ height: `${bottomPanelHeight}px`, flexShrink: 0, display: "flex", flexDirection: "column", borderTop: `1px solid ${T.border1}`, background: T.bg1, boxShadow: "0 -8px 32px rgba(0,0,0,0.4)", position: "relative" }}>
      {/* Drag-to-resize handle */}
      <div
        onMouseDown={(e) => {
          e.preventDefault();
          const startY = e.clientY;
          const startH = bottomPanelHeight;
          const onMove = (ev) => setBottomPanelHeight(Math.max(160, Math.min(600, startH - (ev.clientY - startY))));
          const onUp   = () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
          window.addEventListener("mousemove", onMove);
          window.addEventListener("mouseup", onUp);
        }}
        style={{ position: "absolute", top: 0, left: 0, right: 0, height: "5px", cursor: "ns-resize", zIndex: 10, background: "transparent" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(59,158,255,0.2)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      />

      {/* Tab bar */}
      <div style={{ display: "flex", alignItems: "center", background: T.bg2, borderBottom: `1px solid ${T.border0}`, padding: "0 14px", flexShrink: 0 }}>
        {[
          { id: "stimulus", label: "Stimulus" },
          { id: "rtl",      label: "RTL" },
          { id: "tb",       label: "Testbench" },
          { id: "drc",      label: drcLogs.some((l) => l.type === "error") ? "⚡ DRC ●" : "DRC" },
          { id: "verify",   label: "✦ Verify" },
          { id: "pd",       label: "⬡ Physical Design" },
        ].map((tab) => (
          <button key={tab.id}
            className={`panel-tab${activeTab === tab.id ? " active" : ""}`}
            onClick={() => tab.id === "pd" ? setCurrentPage("pd") : setActiveTab(tab.id)}>
            {tab.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button onClick={() => setShowBottomPanel(false)}
          style={{ background: "transparent", border: "none", color: T.textMuted, fontSize: "20px", cursor: "pointer", padding: "0 4px", lineHeight: 1, transition: "color 0.12s" }}
          onMouseEnter={(e) => (e.currentTarget.style.color = T.red)}
          onMouseLeave={(e) => (e.currentTarget.style.color = T.textMuted)}>×</button>
      </div>

      {/* Panel content */}
      <div style={{ flex: 1, overflow: "hidden", display: "flex" }}>

        {/* ── STIMULUS TAB ── */}
        {activeTab === "stimulus" && (
          <div style={{ flex: 1, overflowY: "auto", padding: "10px 14px" }}>
            {/* TB Config strip */}
            <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "14px", padding: "8px 12px", marginBottom: "10px", background: T.bg3, border: `1px solid ${T.border1}`, borderRadius: T.r8, fontSize: "12px", fontFamily: T.fontUI }}>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{ color: T.textMuted, fontWeight: "600", letterSpacing: "0.5px" }}>RESET</span>
                <select value={tbConfig.resetType} onChange={(e) => updateTbConfig((c) => ({ ...c, resetType: e.target.value }))}
                  style={{ background: T.bg2, border: `1px solid ${T.border2}`, borderRadius: T.r4, color: T.textPrimary, fontSize: "12px", padding: "2px 6px", cursor: "pointer", fontFamily: T.fontUI }}>
                  <option value="sync">Sync</option>
                  <option value="async">Async</option>
                  <option value="none">None</option>
                </select>
              </div>
              <div style={{ width: "1px", height: "18px", background: T.border1 }} />
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{ color: T.textMuted, fontWeight: "600", letterSpacing: "0.5px" }}>POLARITY</span>
                <div style={{ display: "flex", borderRadius: T.r4, overflow: "hidden", border: `1px solid ${T.border2}` }}>
                  {[["high", "Active High"], ["low", "Active Low"]].map(([val, label]) => (
                    <button key={val} onClick={() => updateTbConfig((c) => ({ ...c, resetActive: val }))}
                      style={{ padding: "2px 10px", border: "none", cursor: "pointer", fontSize: "12px", fontFamily: T.fontUI, background: tbConfig.resetActive === val ? `${T.blue}22` : T.bg2, color: tbConfig.resetActive === val ? T.blue : T.textMuted, fontWeight: tbConfig.resetActive === val ? "600" : "400" }}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <div style={{ width: "1px", height: "18px", background: T.border1 }} />
              <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", color: T.textMuted }}>
                <input type="checkbox" checked={tbConfig.useCornerCases} onChange={(e) => updateTbConfig((c) => ({ ...c, useCornerCases: e.target.checked }))} />
                Corner Cases
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", color: T.textMuted }}>
                <input type="checkbox" checked={tbConfig.useRandom} onChange={(e) => updateTbConfig((c) => ({ ...c, useRandom: e.target.checked }))} />
                Random
              </label>
              {tbConfig.useRandom && (
                <>
                  <input type="number" value={tbConfig.numRandomSteps} min={1} max={32}
                    onChange={(e) => updateTbConfig((c) => ({ ...c, numRandomSteps: e.target.value }))}
                    style={{ width: "46px", background: T.bg2, border: `1px solid ${T.border2}`, borderRadius: T.r4, color: T.textPrimary, fontSize: "12px", padding: "2px 6px", fontFamily: T.fontMono }}
                    title="Number of random steps" />
                  <span style={{ color: T.textMuted, fontSize: "11px" }}>seed:</span>
                  <input type="number" value={tbConfig.randomSeed}
                    onChange={(e) => updateTbConfig((c) => ({ ...c, randomSeed: e.target.value }))}
                    placeholder="auto"
                    style={{ width: "60px", background: T.bg2, border: `1px solid ${T.border2}`, borderRadius: T.r4, color: T.textPrimary, fontSize: "12px", padding: "2px 6px", fontFamily: T.fontMono }} />
                </>
              )}
              <div style={{ width: "1px", height: "18px", background: T.border1 }} />
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{ color: T.textMuted, fontWeight: "600", letterSpacing: "0.5px" }}>DURATION</span>
                <input type="number" value={tbConfig.simDurationNs} min={500} step={500}
                  onChange={(e) => updateTbConfig((c) => ({ ...c, simDurationNs: e.target.value }))}
                  style={{ width: "72px", background: T.bg2, border: `1px solid ${T.border2}`, borderRadius: T.r4, color: T.textPrimary, fontSize: "12px", padding: "2px 6px", fontFamily: T.fontMono }} />
                <span style={{ color: T.textMuted }}>ns</span>
              </div>
            </div>

            {tbConfigDirty && testbenchCode && (
              <div style={{ padding: "6px 12px", marginBottom: "8px", background: `${T.amber}12`, border: `1px solid ${T.amber}44`, borderRadius: T.r6, fontSize: "11px", color: T.amber, fontFamily: T.fontUI }}>
                ⚠ Config changed after testbench was generated. Click ◈ TB to regenerate.
              </div>
            )}

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "10px" }}>
              <span style={{ fontSize: "17px", color: T.textMuted, fontFamily: T.fontUI }}>
                Each row = one clock cycle. Add <span style={{ color: T.amber, fontFamily: T.fontMono }}>expected</span> values to enable auto-assertion.
              </span>
              <button onClick={() => setTbSteps([...tbSteps, { time: tbSteps.length * 100, values: {}, expected: {}, label: `step_${tbSteps.length}` }])}
                style={{ padding: "4px 12px", background: `${T.blue}12`, border: `1px solid ${T.blue}44`, borderRadius: T.r6, fontSize: "17px", color: T.blue, cursor: "pointer", fontFamily: T.fontUI, flexShrink: 0 }}>
                + Step
              </button>
            </div>

            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", fontSize: "17px", borderCollapse: "collapse", color: T.textSecondary }}>
                <thead>
                  <tr style={{ background: T.bg3 }}>
                    <th style={{ padding: "6px 10px", border: `1px solid ${T.border1}`, color: T.textMuted, textAlign: "left", fontFamily: T.fontMono, fontWeight: "600", fontSize: "16px", minWidth: "80px" }}>Label</th>
                    <th style={{ padding: "6px 10px", border: `1px solid ${T.border1}`, color: T.amber, textAlign: "left", fontFamily: T.fontMono, fontWeight: "600", fontSize: "16px", minWidth: "60px" }}>ns</th>
                    {nodes.filter((n) => n.type === "input").map((n) => (
                      <th key={n.id} style={{ padding: "6px 10px", border: `1px solid ${T.border1}`, color: T.blue, textAlign: "left", fontFamily: T.fontMono, fontWeight: "600", fontSize: "16px", minWidth: "70px" }}>↓ {n.data.name}</th>
                    ))}
                    {nodes.filter((n) => n.type === "output").map((n) => (
                      <th key={n.id} style={{ padding: "6px 10px", border: `1px solid ${T.border1}`, color: T.green, textAlign: "left", fontFamily: T.fontMono, fontWeight: "600", fontSize: "16px", minWidth: "70px" }}>✓ {n.data.name}</th>
                    ))}
                    <th style={{ padding: "6px 6px", border: `1px solid ${T.border1}`, width: "28px" }}></th>
                  </tr>
                </thead>
                <tbody>
                  {tbSteps.map((s, idx) => (
                    <tr key={idx} style={{ background: idx % 2 === 0 ? "transparent" : `${T.bg3}55` }}>
                      <td style={{ border: `1px solid ${T.border0}` }}>
                        <input value={s.label ?? `step_${idx}`}
                          onChange={(e) => { const n = [...tbSteps]; n[idx] = { ...n[idx], label: e.target.value }; setTbSteps(n); }}
                          style={{ width: "100%", border: "none", padding: "5px 10px", outline: "none", background: "transparent", color: T.textMuted, fontFamily: T.fontMono, fontSize: "13px" }} />
                      </td>
                      <td style={{ border: `1px solid ${T.border0}` }}>
                        <input type="number" value={s.time}
                          onChange={(e) => { const n = [...tbSteps]; n[idx] = { ...n[idx], time: e.target.value }; setTbSteps(n); }}
                          style={{ width: "100%", border: "none", padding: "5px 10px", outline: "none", background: "transparent", color: T.amber, fontFamily: T.fontMono, fontSize: "13px" }} />
                      </td>
                      {nodes.filter((n) => n.type === "input").map((inNode) => (
                        <td key={inNode.id} style={{ border: `1px solid ${T.border0}` }}>
                          <input value={s.values?.[inNode.data.name] ?? ""}
                            onChange={(e) => { const n = [...tbSteps]; n[idx] = { ...n[idx], values: { ...n[idx].values, [inNode.data.name]: e.target.value } }; setTbSteps(n); }}
                            style={{ width: "100%", border: "none", padding: "5px 10px", outline: "none", background: "transparent", color: T.blue, fontFamily: T.fontMono, fontSize: "13px" }} />
                        </td>
                      ))}
                      {nodes.filter((n) => n.type === "output").map((outNode) => (
                        <td key={outNode.id} style={{ border: `1px solid ${T.border0}`, background: `${T.green}06` }}>
                          <input value={s.expected?.[outNode.data.name] ?? ""}
                            placeholder="—"
                            onChange={(e) => { const n = [...tbSteps]; n[idx] = { ...n[idx], expected: { ...(n[idx].expected || {}), [outNode.data.name]: e.target.value } }; setTbSteps(n); }}
                            style={{ width: "100%", border: "none", padding: "5px 10px", outline: "none", background: "transparent", color: T.green, fontFamily: T.fontMono, fontSize: "13px" }} />
                        </td>
                      ))}
                      <td style={{ border: `1px solid ${T.border0}`, textAlign: "center" }}>
                        <button onClick={() => setTbSteps(tbSteps.filter((_, i) => i !== idx))}
                          style={{ background: "none", border: "none", color: `${T.red}66`, cursor: "pointer", fontSize: "18px", lineHeight: 1 }}>×</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ marginTop: "10px", display: "flex", gap: "16px", fontSize: "16px", color: T.textMuted, fontFamily: T.fontUI }}>
              <span><span style={{ color: T.blue }}>↓</span> = drive input</span>
              <span><span style={{ color: T.green }}>✓</span> = expect output</span>
              <span><span style={{ color: T.amber }}>ns</span> = simulation time</span>
            </div>
          </div>
        )}

        {/* ── RTL TAB ── */}
        {activeTab === "rtl" && (
          <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
            {/* File tree */}
            <div style={{ width: "168px", flexShrink: 0, background: T.bg2, borderRight: `1px solid ${T.border0}`, display: "flex", flexDirection: "column", overflow: "hidden" }}>
              <div style={{ padding: "7px 12px 5px", fontSize: "16px", fontWeight: "700", color: T.textMuted, letterSpacing: "1.5px", textTransform: "uppercase", fontFamily: T.fontMono, borderBottom: `1px solid ${T.border0}` }}>Files</div>
              <div style={{ overflowY: "auto", flex: 1 }}>
                {Object.keys(verilogFiles).length === 0 ? (
                  <div style={{ padding: "14px 12px", fontSize: "17px", color: T.textMuted, fontFamily: T.fontUI, lineHeight: 1.5 }}>Click ◈ RTL to generate</div>
                ) : Object.keys(verilogFiles).map((fname) => {
                  const isTop    = fname === "top.v";
                  const isActive = fname === activeRtlFile;
                  const lineCount = verilogFiles[fname]?.split("\n").length ?? 0;
                  const fileColor = isTop ? T.green : fname.startsWith("mux_") ? T.cyan : fname.startsWith("counter_") ? T.amber : fname.startsWith("shiftreg_") ? "#a78bfa" : fname.startsWith("fifo_") ? "#fb923c" : fname.startsWith("penc_") ? T.purple : fname.startsWith("sync2ff_") ? T.sigClock : fname.startsWith("reg_") ? T.blue : fname.startsWith("fsm_") ? T.red : T.textSecondary;
                  return (
                    <button key={fname} onClick={() => setActiveRtlFile(fname)}
                      style={{ width: "100%", textAlign: "left", padding: "6px 12px", background: isActive ? `${fileColor}14` : "transparent", border: "none", borderLeft: isActive ? `2px solid ${fileColor}` : "2px solid transparent", cursor: "pointer", transition: "all 0.1s ease", display: "flex", flexDirection: "column", gap: "1px" }}
                      onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = T.bg4; }}
                      onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = "transparent"; }}>
                      <span style={{ fontFamily: T.fontMono, fontSize: "17px", color: isActive ? fileColor : T.textSecondary, fontWeight: isActive ? "600" : "400", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block", maxWidth: "140px" }}>{fname}</span>
                      <span style={{ fontSize: "16px", color: T.textMuted, fontFamily: T.fontMono }}>{lineCount} lines</span>
                    </button>
                  );
                })}
              </div>
              {Object.keys(verilogFiles).length > 0 && (
                <div style={{ padding: "6px 12px", borderTop: `1px solid ${T.border0}`, fontSize: "16px", color: T.textMuted, fontFamily: T.fontMono }}>
                  {Object.keys(verilogFiles).length} file{Object.keys(verilogFiles).length !== 1 ? "s" : ""} · {Object.values(verilogFiles).reduce((a, c) => a + (c?.split("\n").length ?? 0), 0)} lines
                </div>
              )}
            </div>
            {/* Code viewer */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column", background: T.bg0, overflow: "hidden" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "4px 14px", background: T.bg2, borderBottom: `1px solid ${T.border0}`, flexShrink: 0 }}>
                <span style={{ fontFamily: T.fontMono, fontSize: "17px", color: T.textSecondary }}>{activeRtlFile || "—"}{verilogFiles[activeRtlFile] ? ` · ${verilogFiles[activeRtlFile].split("\n").length} lines` : ""}</span>
              </div>
              <textarea value={verilogFiles[activeRtlFile] || (Object.keys(verilogFiles).length === 0 ? "// Click ◈ RTL to generate code..." : "// Select a file from the panel on the left")} readOnly
                style={{ flex: 1, padding: "14px 18px", fontFamily: T.fontMono, fontSize: "13px", border: "none", background: "transparent", color: activeRtlFile === "top.v" ? T.green : T.blue, lineHeight: "1.65", resize: "none", outline: "none" }} />
            </div>
          </div>
        )}

        {/* ── TESTBENCH TAB ── */}
        {activeTab === "tb" && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", background: T.bg0, overflow: "hidden" }}>
            <div style={{ padding: "5px 14px", background: T.bg2, borderBottom: `1px solid ${T.border0}`, fontSize: "18px", color: T.textMuted, fontFamily: T.fontMono }}>
              top_tb.v{testbenchCode ? ` · ${testbenchCode.split("\n").length} lines` : ""}
            </div>
            <textarea value={testbenchCode || "// Click ◈ TB to generate testbench..."} readOnly
              style={{ flex: 1, padding: "14px 18px", fontFamily: T.fontMono, fontSize: "13px", border: "none", background: "transparent", color: T.blue, lineHeight: "1.7", resize: "none", outline: "none" }} />
          </div>
        )}

        {/* ── DRC TAB ── */}
        {activeTab === "drc" && (
          <div style={{ flex: 1, overflowY: "auto", padding: "10px 14px", background: T.bg0 }}>
            {drcLogs.length === 0 ? (
              <div style={{ padding: "20px", textAlign: "center", fontSize: "12px", color: T.textMuted, fontFamily: T.fontUI }}>Run ⚡ DRC to check your circuit</div>
            ) : drcLogs.map((entry, i) => (
              <div key={i} style={{ padding: "7px 12px", marginBottom: "4px", borderRadius: T.r6, background: entry.type === "error" ? `${T.red}0a` : entry.type === "warn" ? `${T.amber}0a` : entry.type === "pass" ? `${T.green}0a` : T.bg2, border: `1px solid ${entry.type === "error" ? T.red + "33" : entry.type === "warn" ? T.amber + "33" : entry.type === "pass" ? T.green + "33" : T.border1}` }}>
                <span style={{ fontFamily: T.fontMono, fontSize: "12px", lineHeight: "1.5", color: entry.type === "error" ? T.red : entry.type === "warn" ? T.amber : entry.type === "pass" ? T.green : T.textSecondary }}>{entry.msg}</span>
              </div>
            ))}
          </div>
        )}

        {/* ── VERIFY TAB ── */}
        {activeTab === "verify" && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ padding: "8px 14px", background: T.bg2, borderBottom: `1px solid ${T.border0}`, fontSize: "11px", color: T.textMuted, fontFamily: T.fontUI }}>
              ✦ AI Verification — fill expected outputs in the Stimulus tab ✓ columns, then click Verify.
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px", display: "flex", flexDirection: "column", gap: "12px" }}>
              {verifyRandomWarning && (
                <div style={{ padding: "16px 18px", background: `${T.amber}0f`, border: `1px solid ${T.amber}44`, borderRadius: T.r8, fontFamily: T.fontUI }}>
                  <div style={{ fontSize: "14px", fontWeight: "600", color: T.amber, marginBottom: "10px" }}>⚠ Random inputs enabled — verification needs known expected outputs</div>
                  <div style={{ fontSize: "12px", color: T.textSecondary, lineHeight: "1.8" }}>Random stimulus generates unpredictable inputs, so the agent can't know what the output should be.</div>
                  <button onClick={() => setVerifyRandomWarning(false)}
                    style={{ marginTop: "12px", padding: "5px 14px", background: `${T.amber}18`, border: `1px solid ${T.amber}44`, borderRadius: T.r4, color: T.amber, fontSize: "12px", cursor: "pointer", fontFamily: T.fontUI }}>
                    Got it
                  </button>
                </div>
              )}

              {verifyHistory.length === 0 && (
                <div style={{ margin: "auto", textAlign: "center", color: T.textMuted, fontFamily: T.fontUI, fontSize: "13px", maxWidth: "380px", lineHeight: "1.8" }}>
                  <div style={{ fontSize: "24px", marginBottom: "10px" }}>✦</div>
                  <div style={{ fontWeight: "600", color: T.textSecondary, marginBottom: "6px" }}>AI Verification Agent</div>
                  <div>1. Go to <span style={{ color: T.amber }}>Stimulus</span> tab — add input values per step</div>
                  <div>2. Fill expected outputs in <span style={{ color: T.green }}>✓ green columns</span></div>
                  <div>3. Click <span style={{ color: "#c4b5fd" }}>▶ Verify</span> below</div>
                </div>
              )}

              {verifyHistory.map((msg, idx) => (
                <div key={idx} style={{ display: "flex", flexDirection: "column", alignItems: "flex-start" }}>
                  <div style={{ fontSize: "10px", color: T.textMuted, marginBottom: "4px", fontFamily: T.fontUI }}>
                    {msg.role === "auto_agent" ? "⚡ Auto-Verify Agent" : "Agent"}
                  </div>
                  <div style={{ maxWidth: "95%", width: "100%", padding: "12px 14px", borderRadius: T.r8, background: T.bg3, border: `1px solid ${T.border1}`, fontFamily: T.fontUI, fontSize: "13px", color: T.textPrimary, lineHeight: "1.6" }}>
                    {/* Verdict */}
                    {msg.verdict && (
                      <div style={{ display: "inline-flex", alignItems: "center", gap: "6px", padding: "3px 10px", borderRadius: T.r4, marginBottom: "8px", fontSize: "11px", fontWeight: "700",
                        background: (msg.verdict === "pass" || msg.verdict === "correct") ? `${T.green}18` : (msg.verdict === "error" || msg.verdict === "bug_found") ? `${T.red}18` : `${T.amber}18`,
                        color: (msg.verdict === "pass" || msg.verdict === "correct") ? T.green : (msg.verdict === "error" || msg.verdict === "bug_found") ? T.red : T.amber,
                        border: `1px solid ${(msg.verdict === "pass" || msg.verdict === "correct") ? T.green : (msg.verdict === "error" || msg.verdict === "bug_found") ? T.red : T.amber}33`,
                      }}>
                        {msg.verdict === "pass" ? "✅ PASS" : msg.verdict === "correct" ? "✅ CORRECT" : msg.verdict === "bug_found" ? "🐛 BUG FOUND" : msg.verdict === "error" ? "❌ ERROR" : "⚠ FAIL"}
                        {msg.pass_count !== undefined && <span style={{ opacity: 0.7 }}>&nbsp;· {msg.pass_count} pass &nbsp;{msg.fail_count} fail</span>}
                        {msg.confidence && <span style={{ opacity: 0.7, fontWeight: "400" }}>&nbsp;· {msg.confidence} confidence</span>}
                      </div>
                    )}
                    <div style={{ marginBottom: "8px" }}>{msg.text}</div>
                    {msg.next_action && msg.verdict !== "pass" && (
                      <div style={{ padding: "8px 10px", marginBottom: "8px", background: `${T.violet}0f`, border: `1px solid ${T.violet}22`, borderRadius: T.r4, fontSize: "12px", color: "#c4b5fd", fontFamily: T.fontUI }}>
                        <span style={{ fontWeight: "600", marginRight: "6px" }}>→ Next:</span>{msg.next_action}
                      </div>
                    )}
                    {msg.suggested_fix && (
                      <div style={{ padding: "8px 10px", marginBottom: "6px", background: `${T.violet}0f`, border: `1px solid ${T.violet}22`, borderRadius: T.r4 }}>
                        <div style={{ fontSize: "10px", fontWeight: "700", color: "#c4b5fd", marginBottom: "3px" }}>→ SUGGESTED FIX</div>
                        <div style={{ fontSize: "12px", color: T.textSecondary }}>{msg.suggested_fix}</div>
                      </div>
                    )}
                    {msg.console && (
                      <div style={{ marginTop: "8px" }}>
                        <div style={{ fontSize: "10px", color: T.textMuted, marginBottom: "4px", fontFamily: T.fontUI, letterSpacing: "0.5px" }}>CONSOLE OUTPUT</div>
                        <pre style={{ margin: 0, padding: "8px 10px", background: T.bg0, borderRadius: T.r4, border: `1px solid ${T.border0}`, fontFamily: T.fontMono, fontSize: "10px", color: T.textSecondary, lineHeight: "1.6", overflowX: "auto", maxHeight: "160px", overflowY: "auto", whiteSpace: "pre-wrap" }}>{msg.console}</pre>
                      </div>
                    )}
                    {msg.testbench && (
                      <div style={{ marginTop: "8px" }}>
                        <button onClick={() => setVerifyExpanded((ex) => ({ ...ex, [`tb_${idx}`]: !ex[`tb_${idx}`] }))}
                          style={{ background: "none", border: "none", color: T.textMuted, fontSize: "11px", cursor: "pointer", padding: 0, fontFamily: T.fontUI }}>
                          {verifyExpanded[`tb_${idx}`] ? "▾" : "▸"} View generated testbench ({msg.testbench.split("\n").length} lines)
                        </button>
                        {verifyExpanded[`tb_${idx}`] && (
                          <pre style={{ margin: "4px 0 0 0", padding: "8px 10px", background: T.bg0, borderRadius: T.r4, border: `1px solid ${T.border0}`, fontFamily: T.fontMono, fontSize: "10px", color: T.blue, lineHeight: "1.6", overflowX: "auto", maxHeight: "200px", overflowY: "auto", whiteSpace: "pre" }}>{msg.testbench}</pre>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {verifyLoading && (
                <div style={{ display: "flex", flexDirection: "column", gap: "6px", padding: "10px 14px", background: T.bg3, borderRadius: T.r8, border: `1px solid ${T.border1}`, maxWidth: "300px" }}>
                  {["Generating testbench…", "Running simulation…", "Analyzing results…"].map((step, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: "8px", fontFamily: T.fontUI, fontSize: "12px", color: T.textMuted }}>
                      <div style={{ width: "6px", height: "6px", borderRadius: "50%", background: T.violet, opacity: 0.4 + i * 0.3 }} />
                      {step}
                    </div>
                  ))}
                </div>
              )}
              {verifyAutoLoading && (
                <div style={{ display: "flex", flexDirection: "column", gap: "6px", padding: "10px 14px", background: T.bg3, borderRadius: T.r8, border: `1px solid ${T.blue}33`, maxWidth: "320px" }}>
                  {["Understanding circuit…", "Generating test plan…", "Running simulation…", "Interpreting results…"].map((step, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: "8px", fontFamily: T.fontUI, fontSize: "12px", color: T.textMuted }}>
                      <div style={{ width: "6px", height: "6px", borderRadius: "50%", background: T.blue, opacity: 0.3 + i * 0.25 }} />
                      {step}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Verify footer */}
            <div style={{ borderTop: `1px solid ${T.border0}`, background: T.bg2 }}>
              <div style={{ padding: "8px 14px 0 14px" }}>
                <input value={verifyIntent} onChange={(e) => setVerifyIntent(e.target.value)}
                  placeholder="Design intent for ▶ Verify (optional): e.g. '2-input OR gate'"
                  style={{ width: "100%", padding: "6px 10px", boxSizing: "border-box", background: T.bg3, border: `1px solid ${T.border2}`, borderRadius: T.r6, color: T.textPrimary, fontSize: "12px", fontFamily: T.fontUI, outline: "none" }}
                  onFocus={(e) => (e.target.style.borderColor = `${T.violet}55`)}
                  onBlur={(e) => (e.target.style.borderColor = T.border2)} />
              </div>
              <div style={{ padding: "8px 14px", display: "flex", alignItems: "center", gap: "8px" }}>
                <div style={{ flex: 1, fontSize: "11px", color: T.textMuted, fontFamily: T.fontUI, lineHeight: "1.5" }}>
                  <span style={{ color: T.green }}>▶ Verify</span> uses your stimulus table.&nbsp;
                  <span style={{ color: T.blue }}>⚡ Auto-Verify</span> — agent tests autonomously.
                </div>
                <button onClick={runVerification} disabled={verifyLoading || verifyAutoLoading}
                  style={{ padding: "7px 14px", flexShrink: 0, background: verifyLoading ? T.bg5 : `linear-gradient(135deg, ${T.violet}33, ${T.blue}22)`, border: `1px solid ${verifyLoading ? T.border2 : T.violet + "55"}`, borderRadius: T.r6, color: verifyLoading ? T.textMuted : "#c4b5fd", fontSize: "12px", fontWeight: "600", cursor: (verifyLoading || verifyAutoLoading) ? "not-allowed" : "pointer", fontFamily: T.fontUI, whiteSpace: "nowrap" }}>
                  {verifyLoading ? "Verifying…" : "▶ Verify"}
                </button>
                <button onClick={runAutoVerification} disabled={verifyLoading || verifyAutoLoading}
                  style={{ padding: "7px 16px", flexShrink: 0, background: verifyAutoLoading ? T.bg5 : `linear-gradient(135deg, ${T.blue}33, ${T.cyan}22)`, border: `1px solid ${verifyAutoLoading ? T.border2 : T.blue + "55"}`, borderRadius: T.r6, color: verifyAutoLoading ? T.textMuted : T.blue, fontSize: "12px", fontWeight: "600", cursor: (verifyLoading || verifyAutoLoading) ? "not-allowed" : "pointer", fontFamily: T.fontUI, whiteSpace: "nowrap" }}>
                  {verifyAutoLoading ? "Running…" : "⚡ Auto-Verify"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default BottomPanel;
