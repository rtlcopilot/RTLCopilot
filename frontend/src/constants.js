
export const GRID_X = 220;
export const GRID_Y = 160;
export const MAX_COLS = 4;


export const T = {
  bg0:      "#05080f",
  bg1:      "#090e18",
  bg2:      "#0d1320",
  bg3:      "#111827",
  bg4:      "#161f30",
  bg5:      "#1c2840",
  border0:  "#161f30",
  border1:  "#1c2840",
  border2:  "#243250",
  textPrimary:   "#d8e4f0",
  textSecondary: "#6b849e",
  textMuted:     "#2e4460",
  textCode:      "#93c5fd",
  blue:     "#3b9eff",
  blueGlow: "rgba(59,158,255,0.12)",
  cyan:     "#22d3ee",
  green:    "#10b981",
  amber:    "#f59e0b",
  red:      "#ef4444",
  purple:   "#8b5cf6",
  violet:   "#7c3aed",
  sigInput:  "#3b9eff",
  sigOutput: "#10b981",
  sigClock:  "#f59e0b",
  sigReset:  "#ef4444",
  fontUI:   "'IBM Plex Sans', 'Inter', system-ui, sans-serif",
  fontMono: "'JetBrains Mono', 'Fira Code', monospace",
  r4:  "4px",
  r6:  "6px",
  r8:  "8px",
  r12: "12px",
};


export const COLORS = {
  navy:   T.bg2,
  blue:   T.blue,
  border: T.border1,
  bg:     T.bg0,
  text:   T.textPrimary,
  accent: T.green,
};

export const nodeBox = {
  padding: "12px",
  borderRadius: T.r8,
  background: T.bg4,
  border: `1px solid ${T.border1}`,
  minWidth: "140px",
  textAlign: "center",
  fontSize: "11px",
  fontWeight: "500",
  color: T.textPrimary,
  boxShadow: `0 4px 24px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.025)`,
  fontFamily: T.fontUI,
};

export const mathBox = {
  ...nodeBox,
  background: T.bg3,
  border: `1px solid ${T.blue}33`,
  boxShadow: `0 4px 24px rgba(0,0,0,0.5), 0 0 0 1px ${T.blue}0d`,
};

export const stateCircle = {
  background: `radial-gradient(ellipse at 30% 30%, ${T.bg4} 0%, ${T.bg2} 100%)`,
  border: `1.5px solid ${T.purple}66`,
  boxShadow: `0 0 0 3px ${T.purple}12, 0 4px 20px rgba(0,0,0,0.6), inset 0 1px 0 ${T.purple}22`,
  borderRadius: "50%",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
};

export const deleteBtnStyle = {
  position: "absolute",
  top: "-8px",
  right: "-8px",
  background: "#1a0808",
  color: T.red,
  border: `1px solid ${T.red}44`,
  borderRadius: "50%",
  width: "20px",
  height: "20px",
  cursor: "pointer",
  fontSize: "12px",
  lineHeight: "1",
  zIndex: 999,
  pointerEvents: "all",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

export const GLOBAL_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
  * { box-sizing: border-box; }
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #243250; border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: #3d5a7a; }
  .react-flow__background { background: #05080f !important; }
  .react-flow__edge-path { stroke: #3b9eff !important; stroke-width: 1.5 !important; opacity: 0.65; transition: opacity 0.15s, stroke-width 0.15s; }
  .react-flow__edge-path:hover { opacity: 1; stroke-width: 2 !important; }
  .react-flow__edge.selected .react-flow__edge-path { stroke: #22d3ee !important; opacity: 1; stroke-width: 2 !important; }
  .react-flow__edge-text { font-family: 'JetBrains Mono', monospace; font-size: 11px; fill: #3b9eff !important; font-weight: 500; }
  .react-flow__controls { background: #111827 !important; border: 1px solid #1c2840 !important; border-radius: 8px !important; box-shadow: 0 4px 20px rgba(0,0,0,0.5) !important; overflow: hidden; }
  .react-flow__controls button { background: #111827 !important; fill: #6b849e !important; border: none !important; border-bottom: 1px solid #161f30 !important; width: 28px !important; height: 28px !important; transition: background 0.15s; }
  .react-flow__controls button:hover { background: #1c2840 !important; fill: #d8e4f0 !important; }
  .react-flow__node { background: transparent !important; border: none !important; box-shadow: none !important; }
  .react-flow__node.selected > div { outline: 1.5px solid rgba(59,158,255,0.4) !important; outline-offset: 3px; border-radius: 10px; }
  .react-flow__minimap { background: #111827 !important; border: 1px solid #1c2840 !important; border-radius: 8px !important; }
  .tb-btn { display: inline-flex; align-items: center; gap: 5px; height: 32px; padding: 0 13px; border-radius: 6px; border: 1px solid #243250; background: #161f30; color: #6b849e; font-family: 'IBM Plex Sans', sans-serif; font-size: 12px; font-weight: 500; letter-spacing: 0.2px; cursor: pointer; white-space: nowrap; user-select: none; transition: background 0.12s, color 0.12s, border-color 0.12s, box-shadow 0.12s; }
  .tb-btn:hover { background: #1c2840; color: #d8e4f0; }
  .tb-btn:active { transform: scale(0.97); }
  .tb-btn:disabled { opacity: 0.35; cursor: not-allowed; transform: none; }
  .tb-btn-primary { background: rgba(59,158,255,0.1); border-color: rgba(59,158,255,0.27); color: #3b9eff; }
  .tb-btn-primary:hover { background: rgba(59,158,255,0.16); border-color: rgba(59,158,255,0.47); color: #7ecfff; box-shadow: 0 0 10px rgba(59,158,255,0.1); }
  .tb-btn-green { background: rgba(16,185,129,0.08); border-color: rgba(16,185,129,0.27); color: #10b981; }
  .tb-btn-green:hover { background: rgba(16,185,129,0.15); border-color: rgba(16,185,129,0.4); color: #34d399; }
  .tb-btn-amber { background: rgba(245,158,11,0.07); border-color: rgba(245,158,11,0.25); color: #f59e0b; }
  .tb-btn-amber:hover { background: rgba(245,158,11,0.13); border-color: rgba(245,158,11,0.4); color: #fbbf24; }
  .tb-btn-red { background: rgba(239,68,68,0.06); border-color: rgba(239,68,68,0.2); color: #f87171; }
  .tb-btn-red:hover { background: rgba(239,68,68,0.13); border-color: rgba(239,68,68,0.33); }
  .tb-btn-ai { background: linear-gradient(135deg, rgba(124,58,237,0.16), rgba(59,158,255,0.09)); border-color: rgba(124,58,237,0.27); color: #c4b5fd; }
  .tb-btn-ai:hover { background: linear-gradient(135deg, rgba(124,58,237,0.22), rgba(59,158,255,0.16)); border-color: rgba(124,58,237,0.47); color: #ddd6fe; box-shadow: 0 0 14px rgba(124,58,237,0.1); }
  .tb-btn-run { background: linear-gradient(135deg, rgba(16,185,129,0.27), rgba(16,185,129,0.16)); border-color: rgba(16,185,129,0.53); color: #34d399; font-weight: 700; letter-spacing: 0.3px; }
  .tb-btn-run:hover { background: linear-gradient(135deg, rgba(16,185,129,0.33), rgba(16,185,129,0.22)); border-color: rgba(16,185,129,0.73); color: #6ee7b7; box-shadow: 0 0 18px rgba(16,185,129,0.2); }
  .tb-btn-run:disabled { opacity: 0.25; cursor: not-allowed; transform: none; box-shadow: none; }
  .tb-sep { width: 1px; height: 20px; background: #243250; margin: 0 4px; flex-shrink: 0; }
  .tb-pipeline { display: inline-flex; align-items: center; gap: 1px; background: #0a1020; border: 1px solid #2a3a5c; border-radius: 8px; padding: 3px; box-shadow: inset 0 1px 3px rgba(0,0,0,0.4); }
  .tb-pipeline-step { display: inline-flex; align-items: center; gap: 5px; height: 30px; padding: 0 14px; border-radius: 6px; border: 1px solid transparent; font-family: 'IBM Plex Sans', sans-serif; font-size: 12px; font-weight: 500; cursor: pointer; transition: all 0.15s; white-space: nowrap; }
  .tb-pipeline-step.idle { background: transparent; color: #3d5070; border-color: transparent; }
  .tb-pipeline-step.idle:hover:not(:disabled) { background: #1a2540; color: #5a7090; border-color: #2a3a5c; }
  .tb-pipeline-step.ready { background: #1a2848; color: #7aa8d8; border-color: #2a4070; }
  .tb-pipeline-step.ready:hover { background: #1f3055; color: #9ac0e8; border-color: #3b5585; box-shadow: 0 0 8px rgba(59,158,255,0.15); }
  .tb-pipeline-step.done { background: rgba(16,185,129,0.13); color: #34d399; border-color: rgba(16,185,129,0.27); }
  .tb-pipeline-step.done:hover { background: rgba(16,185,129,0.16); border-color: rgba(16,185,129,0.4); }
  .tb-pipeline-step.active { background: rgba(16,185,129,0.19); color: #6ee7b7; border-color: rgba(16,185,129,0.4); font-weight: 600; box-shadow: 0 0 12px rgba(16,185,129,0.15); }
  .tb-pipeline-step:disabled { opacity: 0.28; cursor: not-allowed; }
  .tb-pipeline-arrow { color: #2a3a5c; font-size: 12px; padding: 0 2px; pointer-events: none; font-weight: 700; }
  .param-chip { display: inline-flex; align-items: center; height: 26px; padding: 0 9px; background: #161f30; border: 1px solid #1c2840; border-radius: 6px; gap: 5px; transition: border-color 0.12s; }
  .param-chip:focus-within { border-color: rgba(59,158,255,0.27); }
  .param-chip input { border: none; background: transparent; outline: none; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #d8e4f0; }
  .param-val { color: #3b9eff !important; font-weight: 600; width: 48px; }
  .param-eq { color: #2e4460; font-family: 'JetBrains Mono', monospace; font-size: 12px; }
  .param-del { border: none; background: none; cursor: pointer; color: #2e4460; font-size: 14px; padding: 0; line-height: 1; transition: color 0.12s; }
  .param-del:hover { color: #ef4444; }
  .panel-tab { display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 16px; background: transparent; border: none; border-bottom: 2px solid transparent; color: #6b849e; font-family: 'IBM Plex Sans', sans-serif; font-size: 12px; font-weight: 500; cursor: pointer; letter-spacing: 0.3px; transition: color 0.12s, border-color 0.12s; }
  .panel-tab:hover { color: #d8e4f0; }
  .panel-tab.active { color: #3b9eff; border-bottom-color: #3b9eff; }
  @keyframes fade-up { from { opacity:0; transform:translateX(-50%) translateY(8px); } to { opacity:1; transform:translateX(-50%) translateY(0); } }
`;
