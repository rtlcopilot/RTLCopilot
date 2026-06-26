import React from "react";
import JSZip from "jszip";
import { saveAs } from "file-saver";
import { T } from "../constants";

const Toolbar = ({
  setHasEntered, setCurrentPage,
  user, setIsAiOpen,
  byokKey, setIsByokOpen,
  runDRC, triggerClockTick,
  rtlReady, tbReady, nodes, simulating,
  generateVerilog, generateTB, runSimulation,
  setShowBottomPanel, setActiveTab,
  verilogFiles, testbenchCode,
  projectName, setProjectName,
  saveProject, isSaving, isDirty,
  showBottomPanel,
  isDropdownOpen, setIsDropdownOpen,
  fetchProjects,
  setIsAuthOpen,
  projects, projectsLoading, currentProjectId,
  loadProject, deleteProject,
  handleSignOut,
  resetCanvas,
}) => {
  return (
    <div style={{ height: "60px", flexShrink: 0, display: "flex", alignItems: "center", padding: "0 16px", gap: "6px", background: "#0f1624", borderBottom: "1px solid #1e2d47", boxShadow: "0 1px 0 rgba(255,255,255,0.04), 0 4px 24px rgba(0,0,0,0.5)", zIndex: 10 }}>

      {/* Logo */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", paddingRight: "14px", borderRight: `1px solid ${T.border1}`, flexShrink: 0, cursor: "pointer" }}
        onClick={() => setHasEntered(false)} title="Back to home">
        <span style={{ fontSize: "16px", fontWeight: "700", color: T.textPrimary, letterSpacing: "-0.1px" }}>
          RTL <span style={{ color: T.blue }}>Copilot</span>
        </span>
      </div>

      {/* Left buttons — flexShrink:0 ensures these never get squeezed by the pipeline */}
      <div style={{ display: "flex", alignItems: "center", gap: "6px", flexShrink: 0 }}>
        <button className="tb-btn" onClick={() => setCurrentPage("docs")} style={{ fontSize: "11px" }}>Docs</button>
        <button className="tb-btn tb-btn-ai"
          onClick={() => setIsAiOpen(true)}
          style={{ fontWeight: "600" }}>
          ✦ Ask AI
          <span style={{
            marginLeft: "6px", fontSize: "12px", fontWeight: "700", padding: "1px 6px", borderRadius: "10px",
            background: byokKey ? `${T.green}22` : `${T.blue}22`,
            color: byokKey ? T.green : `${T.blue}cc`,
            border: `1px solid ${byokKey ? T.green + "55" : T.blue + "33"}`,
          }}>
            {byokKey ? "🔑 AI" : "✦ AI"}
          </span>
        </button>
        <button
          title={byokKey ? "API key active — click to change" : "Use your own OpenAI API key"}
          onClick={() => setIsByokOpen(true)}
          style={{ height: "28px", padding: "0 9px", borderRadius: "6px", border: `1px solid ${byokKey ? T.green + "55" : T.border2}`, background: byokKey ? `${T.green}18` : "transparent", color: byokKey ? T.green : T.textMuted, fontSize: "11px", cursor: "pointer", fontFamily: T.fontUI, transition: "all 0.15s", flexShrink: 0 }}>
          {byokKey ? "🔑 My Key" : "🔑 API Key"}
        </button>
        <div className="tb-sep" />
        <button className="tb-btn tb-btn-red" onClick={runDRC} title="Run Design Rule Check">DRC Test</button>
        <button className="tb-btn" onClick={triggerClockTick} title="Step clock one cycle" style={{ color: T.textMuted, fontSize: "13px", padding: "0 8px" }}>⏱</button>
        <button className="tb-btn" onClick={() => setCurrentPage("pd")} title="Open Physical Design flow"
          style={{ color: "#c4b5fd", borderColor: "#8b5cf655", background: "#8b5cf611", fontWeight: "600" }}>
          ⬡ PD
        </button>
        {nodes.length > 0 && (
          <button className="tb-btn" title="Clear canvas"
            onClick={() => { if (window.confirm("Clear the canvas? This will remove all blocks and connections.")) resetCanvas(); }}
            style={{ color: "#ef444499", borderColor: "#ef444433", fontSize: "11px" }}
            onMouseEnter={(e) => { e.currentTarget.style.color = "#ef4444"; e.currentTarget.style.borderColor = "#ef444466"; e.currentTarget.style.background = "#ef44440a"; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = "#ef444499"; e.currentTarget.style.borderColor = "#ef444433"; e.currentTarget.style.background = "transparent"; }}>
            ✕ Clear
          </button>
        )}
      </div>

      {/* Pipeline — overflow:hidden + minWidth:0 prevent it from squeezing left/right sections */}
      <div style={{ flex: 1, display: "flex", justifyContent: "center", overflow: "hidden", minWidth: 0 }}>
        <div className="tb-pipeline" style={{ overflowX: "auto", maxWidth: "100%" }}>
          <button className={`tb-pipeline-step ${rtlReady ? "done" : nodes.length > 0 ? "ready" : "idle"}`}
            disabled={nodes.length === 0}
            onClick={async () => { await generateVerilog(); setShowBottomPanel(true); setActiveTab("rtl"); }}>
            {rtlReady ? "✓" : "◈"} RTL
          </button>
          <span className="tb-pipeline-arrow">›</span>
          <button className={`tb-pipeline-step ${tbReady ? "done" : rtlReady ? "ready" : "idle"}`}
            disabled={!rtlReady}
            onClick={async () => { await generateTB(); setShowBottomPanel(true); setActiveTab("tb"); }}>
            {tbReady ? "✓" : "◈"} Testbench
          </button>
          <span className="tb-pipeline-arrow">›</span>
          <button className={`tb-pipeline-step ${simulating ? "active" : tbReady ? "ready" : "idle"} tb-btn-run`}
            disabled={!tbReady || simulating}
            onClick={runSimulation}
            style={{ minWidth: "80px" }}>
            {simulating ? "◌ Running…" : "▶ Simulate"}
          </button>
          <span className="tb-pipeline-arrow">›</span>
          <button className="tb-pipeline-step ready"
            title="Download all generated Verilog files"
            onClick={() => {
              const zip = new JSZip();
              Object.entries(verilogFiles).forEach(([fname, code]) => zip.file(fname, code || ""));
              zip.file("top_tb.v", testbenchCode || "");
              zip.generateAsync({ type: "blob" }).then((c) => saveAs(c, "rtl_design.zip"));
            }}>
            ⬇ ZIP
          </button>
        </div>
      </div>

      {/* Right: project + user */}
      <div style={{ display: "flex", alignItems: "center", gap: "6px", flexShrink: 0 }}>
        <input value={projectName} onChange={(e) => setProjectName(e.target.value)}
          style={{ background: "transparent", border: `1px solid ${T.border2}`, borderRadius: T.r4, padding: "4px 8px", fontSize: "13px", color: T.textSecondary, fontFamily: T.fontUI, width: "150px", outline: "none" }}
          onFocus={(e) => (e.target.style.borderColor = `${T.blue}55`)}
          onBlur={(e) => (e.target.style.borderColor = T.border2)} />
        <button className="tb-btn tb-btn-primary" onClick={saveProject} disabled={isSaving}
          title={user ? (isDirty ? "Unsaved changes" : "Save project") : "Sign in to save"}
          style={{ opacity: isSaving ? 0.6 : 1 }}>
          {isSaving ? "Saving…" : isDirty ? "☁ Save •" : "☁ Save"}
        </button>
        <div className="tb-sep" />
        <button className="tb-btn"
          onClick={() => setShowBottomPanel((v) => !v)}
          style={{ color: showBottomPanel ? T.blue : T.textMuted, borderColor: showBottomPanel ? `${T.blue}44` : T.border2 }}>
          {showBottomPanel ? "▾ Console" : "▸ Console"}
        </button>
        <div className="tb-sep" />

        {/* Profile dropdown */}
        <div style={{ position: "relative" }}>
          {user ? (
            <div style={{ display: "flex", alignItems: "center", gap: "7px", cursor: "pointer", padding: "4px 8px", borderRadius: T.r6, border: `1px solid ${isDropdownOpen ? T.border2 : "transparent"}`, background: isDropdownOpen ? T.bg5 : "transparent", transition: "all 0.12s" }}
              onClick={() => { setIsDropdownOpen((o) => !o); if (!isDropdownOpen) { fetchProjects(); } }}
              onMouseEnter={(e) => { if (!isDropdownOpen) e.currentTarget.style.borderColor = T.border2; }}
              onMouseLeave={(e) => { if (!isDropdownOpen) e.currentTarget.style.borderColor = "transparent"; }}>
              <div style={{ width: "26px", height: "26px", borderRadius: "50%", flexShrink: 0, background: `linear-gradient(135deg, ${T.blue}, ${T.purple})`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: "13px", fontWeight: "700", color: "white" }}>
                {user.name?.[0]?.toUpperCase() || "U"}
              </div>
              <span style={{ fontSize: "13px", color: T.textSecondary, maxWidth: "80px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.name}</span>
              <span style={{ fontSize: "10px", color: T.textMuted }}>{isDropdownOpen ? "▲" : "▼"}</span>
            </div>
          ) : (
            <button className="tb-btn tb-btn-primary" onClick={() => setIsAuthOpen(true)} style={{ whiteSpace: "nowrap", fontWeight: "600" }}>Sign In</button>
          )}

          {isDropdownOpen && user && (
            <>
              <div style={{ position: "fixed", inset: 0, zIndex: 1499 }} onClick={() => setIsDropdownOpen(false)} />
              <div style={{ position: "absolute", top: "calc(100% + 8px)", right: 0, width: "280px", zIndex: 1500, background: T.bg3, border: `1px solid ${T.border1}`, borderRadius: T.r12, boxShadow: `0 16px 48px rgba(0,0,0,0.6), 0 0 0 1px ${T.border2}`, overflow: "hidden" }}>
                {/* User info */}
                <div style={{ padding: "14px 16px", background: T.bg2, borderBottom: `1px solid ${T.border0}` }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <div style={{ width: "36px", height: "36px", borderRadius: "50%", flexShrink: 0, background: `linear-gradient(135deg, ${T.blue}, ${T.purple})`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: "16px", fontWeight: "700", color: "white" }}>
                      {user.name?.[0]?.toUpperCase()}
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: "13px", fontWeight: "600", color: T.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.name}</div>
                      <div style={{ fontSize: "11px", color: T.textMuted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.email}</div>
                    </div>
                  </div>
                </div>

                {/* Projects */}
                <div style={{ padding: "8px 0", borderBottom: `1px solid ${T.border0}`, maxHeight: "220px", overflowY: "auto" }}>
                  <div style={{ padding: "4px 16px 8px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: "10px", fontWeight: "700", color: T.textMuted, textTransform: "uppercase", letterSpacing: "0.8px" }}>Projects</span>
                    <button onClick={() => saveProject()} style={{ fontSize: "11px", color: T.blue, background: "none", border: "none", cursor: "pointer", padding: 0 }}>+ Save current</button>
                  </div>
                  {projectsLoading && <div style={{ padding: "8px 16px", fontSize: "12px", color: T.textMuted }}>Loading…</div>}
                  {!projectsLoading && projects.length === 0 && <div style={{ padding: "8px 16px", fontSize: "12px", color: T.textMuted }}>No saved projects yet</div>}
                  {!projectsLoading && projects.map((proj) => (
                    <div key={proj.id} style={{ display: "flex", alignItems: "center", gap: "8px", padding: "6px 16px", cursor: "pointer", background: proj.id === currentProjectId ? `${T.blue}10` : "transparent", transition: "background 0.1s" }}
                      onMouseEnter={(e) => { if (proj.id !== currentProjectId) e.currentTarget.style.background = T.bg5; }}
                      onMouseLeave={(e) => { if (proj.id !== currentProjectId) e.currentTarget.style.background = "transparent"; }}>
                      <span style={{ fontSize: "12px", color: T.blue, flexShrink: 0 }}>◈</span>
                      <span style={{ fontSize: "12px", color: T.textSecondary, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                        onClick={() => { loadProject(proj); setIsDropdownOpen(false); }}>
                        {proj.name}
                      </span>
                      <button onClick={(e) => { e.stopPropagation(); deleteProject(proj.id, proj.name); }}
                        style={{ background: "none", border: "none", cursor: "pointer", color: `${T.red}55`, fontSize: "14px", lineHeight: 1, padding: "0 2px", flexShrink: 0 }}
                        onMouseEnter={(e) => (e.currentTarget.style.color = T.red)}
                        onMouseLeave={(e) => (e.currentTarget.style.color = `${T.red}55`)}>×</button>
                    </div>
                  ))}
                </div>

                {/* Sign out */}
                <div style={{ padding: "6px 0" }}>
                  <button onClick={() => { setIsDropdownOpen(false); handleSignOut(); }}
                    style={{ width: "100%", padding: "8px 16px", textAlign: "left", background: "none", border: "none", cursor: "pointer", fontSize: "12px", color: T.textMuted, fontFamily: T.fontUI, display: "flex", alignItems: "center", gap: "8px", transition: "color 0.12s, background 0.12s" }}
                    onMouseEnter={(e) => { e.currentTarget.style.color = T.red; e.currentTarget.style.background = `${T.red}0a`; }}
                    onMouseLeave={(e) => { e.currentTarget.style.color = T.textMuted; e.currentTarget.style.background = "none"; }}>
                    ↩ Sign Out
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Toolbar;