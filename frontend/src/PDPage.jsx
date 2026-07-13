import { useState, useEffect, useRef } from "react";

const ChevronLeft  = ({ className }) => <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>;
const Play         = ({ className }) => <svg className={className} viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>;
const Copy         = ({ className }) => <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>;
const Download     = ({ className }) => <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>;
const SettingsIcon = ({ className }) => <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>;
const CheckCircle2 = ({ className }) => <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="9 12 11 14 15 10"/></svg>;
const AlertCircle  = ({ className }) => <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>;
const Loader2      = ({ className }) => <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>;
const Circle       = ({ className }) => <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/></svg>;

if (typeof document !== "undefined" && !document.getElementById("tw-cdn")) {
  const s = document.createElement("script");
  s.id = "tw-cdn"; s.src = "https://cdn.tailwindcss.com";
  document.head.appendChild(s);
}

const PD_API   = "http://localhost:7070";

const SESSION_KEY = "rtlcopilot_pd_session";

function getVerilogFingerprint(verilogFiles) {
  return Object.entries(verilogFiles || {})
    .map(([k, v]) => k + ":" + (v || "").length)
    .sort().join("|");
}

function saveSession(runId, stages, configs, outputs) {
  try {
    const data = {
      runId,
      stages: stages.map(s => ({ id: s.id, status: s.status, timeTaken: s.timeTaken })),
      configs,
      outputs: Object.fromEntries(
        Object.entries(outputs).map(([id, lines]) => [id, lines.slice(-20)])
      ),
      savedAt: Date.now(),
    };
    localStorage.setItem(SESSION_KEY, JSON.stringify(data));
  } catch (_) {}
}

function loadSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (Date.now() - data.savedAt > 86400000) {
      localStorage.removeItem(SESSION_KEY);
      return null;
    }
    return data;
  } catch (_) { return null; }
}

function clearSession() {
  try { localStorage.removeItem(SESSION_KEY); } catch (_) {}
}


const MAIN_API = "http://localhost:8080";

async function callPDAssist({ mode, stage, logs, runId, config, verilogFiles, outputs }) {
  let run_meta = {};
  try {
    const metaRes = await fetch(PD_API + "/run/" + runId + "/meta");
    if (metaRes.ok) run_meta = await metaRes.json();
  } catch (_) {}
  const verilog = Object.values(verilogFiles || {}).join("\n\n").slice(0, 800);
  const allLogs = Object.entries(outputs || {})
    .filter(([_, lines]) => lines.length > 0)
    .map(([id, lines]) => "=== " + id.toUpperCase() + " ===\n" + lines.slice(-100).join("\n"))
    .join("\n\n")
    .slice(0, 50000);  
  let authToken = "";
  try {
    for (const key of Object.keys(localStorage)) {
      if (key.includes("auth") || key.includes("session") || key.startsWith("sb-")) {
        const val = JSON.parse(localStorage.getItem(key) || "{}");
        if (val?.access_token) { authToken = val.access_token; break; }
        if (val?.session?.access_token) { authToken = val.session.access_token; break; }
      }
    }
  } catch (_) {}

  const res = await fetch(MAIN_API + "/pd_assist", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(authToken ? { "Authorization": "Bearer " + authToken } : {}),
    },
    body: JSON.stringify({ mode, stage, logs, allLogs, run_meta, verilog, config }),
  });
  if (!res.ok) throw new Error("Backend error " + res.status);
  const data = await res.json();
  if (data.status === "error") throw new Error(data.reply);
  return data.reply;
}

// PD verification 

const CHECKED_STAGES = ["synthesis", "placement", "cts", "routing"];

function getAuthToken() {
  try {
    for (const key of Object.keys(localStorage)) {
      if (key.includes("auth") || key.includes("session") || key.startsWith("sb-")) {
        const val = JSON.parse(localStorage.getItem(key) || "{}");
        if (val?.access_token) return val.access_token;
        if (val?.session?.access_token) return val.session.access_token;
      }
    }
  } catch (_) {}
  return "";
}

// User-configured thresholds travel as query params — changing a threshold in
// Config re-evaluates checks instantly, no stage re-run needed.
function checkThresholdQuery(stageId, configs) {
  const params = new URLSearchParams();
  const num = v => v != null && v !== "" && !isNaN(parseFloat(v));
  if (stageId === "placement") {
    if (num(configs?.placement?.wns_margin_ns)) params.set("wns_margin_ns", configs.placement.wns_margin_ns);
    if (num(configs?.placement?.max_util_pct))  params.set("max_util_pct",  configs.placement.max_util_pct);
  }
  if (stageId === "cts") {
    if (num(configs?.cts?.wns_margin_ns)) params.set("wns_margin_ns", configs.cts.wns_margin_ns);
  }
  const q = params.toString();
  return q ? "?" + q : "";
}

async function fetchStageChecks(runId, stageId, configs) {
  const res = await fetch(PD_API + "/check/" + runId + "/" + stageId + checkThresholdQuery(stageId, configs));
  if (!res.ok) throw new Error("check fetch failed: " + res.status);
  return await res.json();
}

// LLM explains only — all fix values were already computed in pd_verification.py
async function callCheckExplain({ stage, checks, fixes, guidance }) {
  const authToken = getAuthToken();
  const res = await fetch(MAIN_API + "/pd_assist", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(authToken ? { "Authorization": "Bearer " + authToken } : {}),
    },
    body: JSON.stringify({ mode: "check_explain", stage, checks, fixes, guidance }),
  });
  if (!res.ok) throw new Error("Backend error " + res.status);
  const data = await res.json();
  if (data.status === "error") throw new Error(data.explanation || "AI unavailable");
  return data.explanation;
}

const CHECK_STATUS_RANK = { error: 3, warning: 2, unset: 1, ok: 0 };
const CHECK_DOT_CLS = {
  ok: "bg-green-400", warning: "bg-yellow-400",
  error: "bg-red-400", unset: "bg-gray-500",
};

function worstCheckStatus(checkData) {
  let worst = null;
  for (const c of checkData?.checks || []) {
    if (worst === null || (CHECK_STATUS_RANK[c.status] ?? 0) > (CHECK_STATUS_RANK[worst] ?? 0)) {
      worst = c.status;
    }
  }
  return worst;
}

const STAGES = [
  { id: "synthesis", name: "Synthesis",       tool: "Yosys",    outputFile: "netlist.v",     outputLabel: "Netlist (.v)"       },
  { id: "floorplan", name: "Floorplan",        tool: "OpenROAD", outputFile: "floorplan.def", outputLabel: "Floorplan (.def)"   },
  { id: "pdn",       name: "PDN Generation",   tool: "OpenROAD", outputFile: "pdn.def",       outputLabel: "PDN DEF (.def)"     },
  { id: "placement", name: "Placement",        tool: "OpenROAD", outputFile: "placement.def", outputLabel: "Placement (.def)"   },
  { id: "cts",       name: "Clock Tree (CTS)", tool: "OpenROAD", outputFile: "cts.def",       outputLabel: "CTS DEF (.def)"     },
  { id: "routing",   name: "Routing",          tool: "OpenROAD", outputFile: "routed.def",    outputLabel: "Routed DEF (.def)"  },
  { id: "spef",      name: "RC Extraction",    tool: "OpenROAD", outputFile: "output.spef",   outputLabel: "SPEF (.spef)"       },
  { id: "timing",    name: "Timing Analysis",  tool: "OpenSTA",  outputFile: "timing.rpt",    outputLabel: "Timing Report"      },
  { id: "drc",       name: "DRC + GDS",        tool: "KLayout",  outputFile: "output.gds",    outputLabel: "GDS (.gds)"         },
];

const DEFAULT_CONFIGS = {
  synthesis: {
    cell_lib: "sky130_fd_sc_hd", corner: "tt",
    clock_period_ns: 10, flatten: false,
    abc_strategy: "balanced", opt_level: 2,
  },
  floorplan: {
    cell_lib: "sky130_fd_sc_hd", corner: "tt",
    die_area: "0 0 1000 1000", core_util: 0.45,
    aspect_ratio: 1.0, core_margin_um: 10, pin_placement: "random",
  },
  placement: {
    cell_lib: "sky130_fd_sc_hd", corner: "tt",
    density: 0.6, timing_driven: true,
    congestion_driven: false, cell_padding: 4,
    clock_port: "clk", clock_period_ns: 10,
    // verification thresholds — empty = unchecked ("unset" status)
    wns_margin_ns: "", max_util_pct: "",
  },
  routing: {
    cell_lib: "sky130_fd_sc_hd", corner: "tt",
    bottom_routing_layer: "met1", top_routing_layer: "met5",
    congestion_iterations: 30, antenna_fixing: true,
  },
  timing: {
    cell_lib: "sky130_fd_sc_hd", corner: "tt",
    clock_period_ns: 10, clock_uncertainty_ns: 0.1,
    input_delay_frac: 0.2, output_delay_frac: 0.2, clock_port: "",
  },
  pdn: {
    cell_lib: "sky130_fd_sc_hd", corner: "tt",
    vdd_net: "VDD", vss_net: "VSS",
    straps_layer: "met4", straps_width: 1.6, straps_pitch: 27.1,
  },
  cts: {
    cell_lib: "sky130_fd_sc_hd", corner: "tt",
    clock_port: "clk", clock_period_ns: 10,
    cts_buf_list: "sky130_fd_sc_hd__clkbuf_4 sky130_fd_sc_hd__clkbuf_8",
    cts_max_slew: 0.4, cts_max_cap: 0.08,
    // verification threshold — empty = unchecked ("unset" status)
    wns_margin_ns: "",
  },
  spef: {
    cell_lib: "sky130_fd_sc_hd", corner: "tt",
  },
  drc: {},
};

function StatusIcon({ status }) {
  if (status === "pending")  return <Circle       className="w-4 h-4 text-gray-500" />;
  if (status === "running")  return <Loader2      className="w-4 h-4 text-yellow-400 animate-spin" />;
  if (status === "complete") return <CheckCircle2 className="w-4 h-4 text-green-400" />;
  if (status === "error")    return <AlertCircle  className="w-4 h-4 text-red-400" />;
  return null;
}

function StatusBadge({ status }) {
  const cls = {
    pending:  "bg-gray-700 text-gray-300",
    running:  "bg-yellow-700 text-yellow-100",
    complete: "bg-green-700 text-green-100",
    error:    "bg-red-700 text-red-100",
  }[status] || "bg-gray-700 text-gray-300";
  return <span className={`px-2 py-0.5 rounded text-xs font-mono font-semibold uppercase ${cls}`}>{status}</span>;
}

function Field({ label, children, tip }) {
  return (
    <div>
      <div className="flex items-center mb-1">
        <label className="text-xs text-[#888896] uppercase tracking-wide font-semibold">{label}</label>
        {tip && <Tooltip text={tip} />}
      </div>
      {children}
    </div>
  );
}

const inputCls = "w-full bg-[#0a0a0f] border border-[#2a2a3a] rounded px-2 py-1 text-sm text-[#e0e0e8] focus:border-[#8b5cf6] outline-none";

function Inp({ value, onChange, type = "text", min, max, step }) {
  return (
    <input type={type} value={value} min={min} max={max} step={step}
      onChange={e => onChange(type === "number" ? parseFloat(e.target.value) : e.target.value)}
      className={inputCls} />
  );
}

function Sel({ value, onChange, options }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} className={inputCls}>
      {options.map(o => <option key={o.value ?? o} value={o.value ?? o}>{o.label ?? o}</option>)}
    </select>
  );
}

function Toggle({ value, onChange, label }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <div onClick={() => onChange(!value)}
        className={`w-8 h-4 rounded-full transition-colors relative flex-shrink-0 ${value ? "bg-[#8b5cf6]" : "bg-[#2a2a3a]"}`}>
        <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform ${value ? "translate-x-4" : "translate-x-0.5"}`} />
      </div>
      <span className="text-xs text-[#888896]">{label}</span>
    </label>
  );
}

const TOOLTIPS = {
  cell_lib: "The Sky130 standard cell library variant. HD (High Density) packs more cells per area and is the default for most designs. HS (High Speed) optimizes for performance at the cost of area. MS (Medium Speed) is a balanced option.",
  corner: "The process-voltage-temperature corner for timing analysis. TT (Typical-Typical) is nominal 25°C at 1.8V. SS (Slow-Slow) is the worst-case slow corner at 100°C, 1.6V — use for setup sign-off. FF (Fast-Fast) is the best-case fast corner at -40°C, 1.95V — use for hold sign-off.",

  clock_period_ns_synth: "Target clock period in nanoseconds. Yosys uses this to guide ABC technology mapping — tighter periods push the tool to use faster (larger) cells. 10ns = 100MHz.",
  abc_strategy: "ABC optimization strategy. 'balanced' optimizes for both area and speed. 'speed' prioritizes timing at the cost of area. 'area' minimizes cell count at the cost of timing.",
  opt_level: "Optimization aggressiveness (0–3). Higher levels run more optimization passes and produce better QoR but take longer. Level 2 is a good default.",
  flatten: "Flattens the design hierarchy before synthesis. Enables cross-boundary optimizations but makes the netlist harder to debug. Leave OFF for hierarchical designs.",

  die_area: "The total chip die area in microns (x0 y0 x1 y1). This is the full silicon area including I/O ring. For small designs start with 100×100µm and scale up if placement is too congested.",
  core_util: "Fraction of the core area filled with standard cells (0.1–0.9). 0.45 means 45% utilization. Too high (>0.7) causes routing congestion. Too low wastes area. 0.4–0.6 is typical.",
  aspect_ratio: "Width-to-height ratio of the core area. 1.0 = square. Adjust if your design has a natural rectangular shape. Extreme ratios (>3) can cause routing problems.",
  core_margin_um: "Gap between the die edge and the core area in microns. Used for I/O buffers and power ring routing. 10µm is typical for small designs.",

  density: "Target cell density for global placement (0.1–0.9). Higher density packs cells closer together, reducing wire length but increasing routing congestion. 0.6 is a good starting point.",
  timing_driven: "When ON, placement uses timing information to place cells along critical paths closer together, reducing wire delay. Requires a clock port to be specified.",
  congestion_driven: "When ON, placement spreads cells to reduce routing congestion hotspots. Useful for dense designs with many crossing nets.",
  cell_padding: "Extra spacing added around each cell during placement (in routing sites). Higher padding improves routability at the cost of density. 4 is typical.",
  clock_port_placement: "The name of your clock input port. Required for timing-driven placement so OpenROAD knows which signal is the clock.",

  bottom_routing_layer: "Lowest metal layer used for signal routing. met1 is standard. Using met2 as bottom layer leaves met1 exclusively for power rails, improving power integrity.",
  top_routing_layer: "Highest metal layer used for signal routing. met5 allows the most routing resources. Lower top layers (met3/met4) can be used if upper metals are reserved for power.",
  congestion_iterations: "Number of global routing iterations to resolve congestion. Higher values (50–100) improve routing quality for congested designs but take longer.",
  antenna_fixing: "Automatically fixes antenna rule violations — long metal wires that accumulate charge during fabrication and can damage gate oxides. Always keep ON.",

  clock_period_ns_timing: "The clock period for static timing analysis in nanoseconds. Must match your actual operating frequency. All setup/hold checks are relative to this.",
  clock_uncertainty_ns: "Accounts for clock jitter and skew in timing analysis. Added to setup time and subtracted from hold time. 0.1ns is typical for on-chip clocks.",
  clock_port_timing: "The name of your design clock port. Leave empty for combinational (no-clock) designs. The tool skips clock constraints when this is blank.",
  input_delay_frac: "Input arrival delay as a fraction of the clock period. 0.2 means inputs arrive 2ns before the clock edge in a 10ns period. Models upstream logic delay.",
  output_delay_frac: "Output required time as a fraction of the clock period. 0.2 means outputs must be stable 2ns before the next clock edge. Models downstream logic setup.",

  vdd_net: "Name of the power net in your design. Must match the net name in your Verilog. Standard Sky130 cell libraries use VDD or VPWR.",
  vss_net: "Name of the ground net in your design. Must match the net name in your Verilog. Standard Sky130 cell libraries use VSS or VGND.",
  straps_layer: "Metal layer for power straps running across the chip. met4 is standard for Sky130. Higher layers have lower resistance for better power distribution.",
  straps_width: "Width of power straps in microns. Wider straps have lower resistance (better IR drop) but consume more routing area. 1.6µm is typical.",
  straps_pitch: "Distance between power straps in microns. Smaller pitch improves power delivery but uses more metal. 27.1µm matches the Sky130 standard cell height grid.",

  wns_margin_ns: "Verification threshold: the minimum positive setup slack you consider healthy. Checks report a warning when WNS is positive but below this margin. Negative WNS is always an error. Leave empty to skip margin checking.",
  max_util_pct: "Verification threshold: maximum acceptable core utilization in percent. The placement check fails when utilization exceeds this. Leave empty to skip this check.",

  clock_port_cts: "The clock input port name. CTS will build a balanced tree from this port to all flip-flop clock pins.",
  cts_buf_list: "Clock buffer cells used to build the clock tree. clkbuf_4 and clkbuf_8 are standard choices. The number suffix indicates drive strength.",
  cts_max_slew: "Maximum allowed slew rate on clock nets in nanoseconds. Lower values produce sharper clock edges but require more buffers. 0.4ns is typical.",
  cts_max_cap: "Maximum capacitance per clock net segment in picofarads. Lower values force earlier buffer insertion for better signal integrity. 0.08pF is typical.",
};

function Tooltip({ text }) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative inline-block ml-1">
      <button
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        className="w-3.5 h-3.5 rounded-full bg-[#2a2a3a] text-[#888896] text-xs flex items-center justify-center hover:bg-[#8b5cf6] hover:text-white transition-colors leading-none"
      >?</button>
      {show && (
        <div className="absolute z-50 left-5 top-0 w-64 bg-[#1a1a2e] border border-[#8b5cf6] rounded-lg p-3 text-xs text-[#c0c0d0] leading-relaxed shadow-xl">
          {text}
        </div>
      )}
    </div>
  );
}

function ConfigPanel({ stageId, config, onChange }) {
  const set = (k, v) => onChange({ ...config, [k]: v });

  const LibCorner = () => (
    <div className="grid grid-cols-2 gap-3">
      <Field label="Cell Library" tip={TOOLTIPS.cell_lib}>
        <Sel value={config.cell_lib} onChange={v => set("cell_lib", v)} options={[
          { value: "sky130_fd_sc_hd", label: "HD — High Density" },
          { value: "sky130_fd_sc_hs", label: "HS — High Speed"   },
          { value: "sky130_fd_sc_ms", label: "MS — Medium Speed" },
        ]} />
      </Field>
      <Field label="Corner" tip={TOOLTIPS.corner}>
        <Sel value={config.corner} onChange={v => set("corner", v)} options={[
          { value: "tt", label: "TT  25°C  1.80V" },
          { value: "ss", label: "SS 100°C  1.60V" },
          { value: "ff", label: "FF -40°C  1.95V" },
        ]} />
      </Field>
    </div>
  );

  if (stageId === "synthesis") return (
    <div className="space-y-3">
      <LibCorner />
      <div className="grid grid-cols-3 gap-3">
        <Field label="Clock Period (ns)" tip={TOOLTIPS.clock_period_ns_synth}>
          <Inp type="number" value={config.clock_period_ns} onChange={v => set("clock_period_ns", v)} min={1} max={200} step={0.5} />
        </Field>
        <Field label="ABC Strategy" tip={TOOLTIPS.abc_strategy}>
          <Sel value={config.abc_strategy} onChange={v => set("abc_strategy", v)}
            options={["balanced","speed","area"]} />
        </Field>
        <Field label="Opt Level (0–3)" tip={TOOLTIPS.opt_level}>
          <Inp type="number" value={config.opt_level} onChange={v => set("opt_level", v)} min={0} max={3} step={1} />
        </Field>
      </div>
      <Toggle value={config.flatten} onChange={v => set("flatten", v)} label="Flatten hierarchy before synthesis" />
    </div>
  );

  if (stageId === "floorplan") return (
    <div className="space-y-3">
      <LibCorner />
      <Field label="Die Area  (x0 y0 x1 y1  µm)" tip={TOOLTIPS.die_area}>
        <Inp value={config.die_area} onChange={v => set("die_area", v)} />
      </Field>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Core Utilization" tip={TOOLTIPS.core_util}>
          <Inp type="number" value={config.core_util} onChange={v => set("core_util", v)} min={0.1} max={0.9} step={0.05} />
        </Field>
        <Field label="Aspect Ratio" tip={TOOLTIPS.aspect_ratio}>
          <Inp type="number" value={config.aspect_ratio} onChange={v => set("aspect_ratio", v)} min={0.1} max={10} step={0.1} />
        </Field>
        <Field label="Core Margin (µm)" tip={TOOLTIPS.core_margin_um}>
          <Inp type="number" value={config.core_margin_um} onChange={v => set("core_margin_um", v)} min={1} max={100} step={1} />
        </Field>
      </div>
    </div>
  );

  if (stageId === "placement") return (
    <div className="space-y-3">
      <LibCorner />
      <div className="grid grid-cols-2 gap-3">
        <Field label="Density (0.1–0.9)" tip={TOOLTIPS.density}>
          <Inp type="number" value={config.density} onChange={v => set("density", v)} min={0.1} max={0.9} step={0.05} />
        </Field>
        <Field label="Cell Padding (sites)" tip={TOOLTIPS.cell_padding}>
          <Inp type="number" value={config.cell_padding} onChange={v => set("cell_padding", v)} min={0} max={16} step={1} />
        </Field>
      </div>
      <div className="flex gap-6">
        <Toggle value={config.timing_driven}    onChange={v => set("timing_driven", v)}    label="Timing-driven placement" />
        <Toggle value={config.congestion_driven} onChange={v => set("congestion_driven", v)} label="Congestion-driven placement" />
      </div>
      {config.timing_driven && (
        <div className="grid grid-cols-2 gap-3 border-t border-[#2a2a3a] pt-3">
          <Field label="Clock Port (for timing-driven)" tip={TOOLTIPS.clock_port_placement}>
            <Inp value={config.clock_port} onChange={v => set("clock_port", v)} />
          </Field>
          <Field label="Clock Period (ns)">
            <Inp type="number" value={config.clock_period_ns} onChange={v => set("clock_period_ns", v)} min={1} max={200} step={0.5} />
          </Field>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 border-t border-[#2a2a3a] pt-3">
        <Field label="✓ WNS Margin (ns)" tip={TOOLTIPS.wns_margin_ns}>
          <Inp type="number" value={config.wns_margin_ns ?? ""} onChange={v => set("wns_margin_ns", isNaN(v) ? "" : v)} min={0} max={10} step={0.1} />
        </Field>
        <Field label="✓ Max Utilization (%)" tip={TOOLTIPS.max_util_pct}>
          <Inp type="number" value={config.max_util_pct ?? ""} onChange={v => set("max_util_pct", isNaN(v) ? "" : v)} min={1} max={100} step={1} />
        </Field>
      </div>
    </div>
  );

  if (stageId === "routing") return (
    <div className="space-y-3">
      <LibCorner />
      <div className="grid grid-cols-3 gap-3">
        <Field label="Bottom Layer" tip={TOOLTIPS.bottom_routing_layer}>
          <Sel value={config.bottom_routing_layer} onChange={v => set("bottom_routing_layer", v)}
            options={["met1","met2","met3"]} />
        </Field>
        <Field label="Top Layer" tip={TOOLTIPS.top_routing_layer}>
          <Sel value={config.top_routing_layer} onChange={v => set("top_routing_layer", v)}
            options={["met3","met4","met5"]} />
        </Field>
        <Field label="Congestion Iterations" tip={TOOLTIPS.congestion_iterations}>
          <Inp type="number" value={config.congestion_iterations} onChange={v => set("congestion_iterations", v)} min={5} max={100} step={5} />
        </Field>
      </div>
      <Toggle value={config.antenna_fixing} onChange={v => set("antenna_fixing", v)} label="Enable antenna fixing" />
    </div>
  );

  if (stageId === "timing") return (
    <div className="space-y-3">
      <LibCorner />
      <div className="grid grid-cols-2 gap-3">
        <Field label="Clock Period (ns)" tip={TOOLTIPS.clock_period_ns_synth}>
          <Inp type="number" value={config.clock_period_ns} onChange={v => set("clock_period_ns", v)} min={1} max={200} step={0.5} />
        </Field>
        <Field label="Clock Uncertainty (ns)" tip={TOOLTIPS.clock_uncertainty_ns}>
          <Inp type="number" value={config.clock_uncertainty_ns} onChange={v => set("clock_uncertainty_ns", v)} min={0} max={2} step={0.05} />
        </Field>
      </div>
      <Field label="Clock Port" tip={TOOLTIPS.clock_port_timing}>
        <Inp value={config.clock_port} onChange={v => set("clock_port", v)} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Input Delay (fraction of period)" tip={TOOLTIPS.input_delay_frac}>
          <Inp type="number" value={config.input_delay_frac} onChange={v => set("input_delay_frac", v)} min={0} max={0.9} step={0.05} />
        </Field>
        <Field label="Output Delay (fraction of period)" tip={TOOLTIPS.output_delay_frac}>
          <Inp type="number" value={config.output_delay_frac} onChange={v => set("output_delay_frac", v)} min={0} max={0.9} step={0.05} />
        </Field>
      </div>
    </div>
  );

  if (stageId === "pdn") return (
    <div className="space-y-3">
      <LibCorner />
      <div className="grid grid-cols-2 gap-3">
        <Field label="VDD Net" tip={TOOLTIPS.vdd_net}><Inp value={config.vdd_net} onChange={v => set("vdd_net", v)} /></Field>
        <Field label="VSS Net" tip={TOOLTIPS.vss_net}><Inp value={config.vss_net} onChange={v => set("vss_net", v)} /></Field>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Straps Layer" tip={TOOLTIPS.straps_layer}>
          <Sel value={config.straps_layer} onChange={v => set("straps_layer", v)} options={["met3","met4","met5"]} />
        </Field>
        <Field label="Strap Width (µm)" tip={TOOLTIPS.straps_width}>
          <Inp type="number" value={config.straps_width} onChange={v => set("straps_width", v)} min={0.5} max={5} step={0.1} />
        </Field>
        <Field label="Strap Pitch (µm)" tip={TOOLTIPS.straps_pitch}>
          <Inp type="number" value={config.straps_pitch} onChange={v => set("straps_pitch", v)} min={5} max={100} step={0.5} />
        </Field>
      </div>
    </div>
  );

  if (stageId === "cts") return (
    <div className="space-y-3">
      <LibCorner />
      <div className="grid grid-cols-2 gap-3">
        <Field label="Clock Port" tip={TOOLTIPS.clock_port_cts}><Inp value={config.clock_port} onChange={v => set("clock_port", v)} /></Field>
        <Field label="Clock Period (ns)" tip={TOOLTIPS.clock_period_ns_synth}>
          <Inp type="number" value={config.clock_period_ns} onChange={v => set("clock_period_ns", v)} min={1} max={200} step={0.5} />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Max Slew (ns)" tip={TOOLTIPS.cts_max_slew}>
          <Inp type="number" value={config.cts_max_slew} onChange={v => set("cts_max_slew", v)} min={0.1} max={2} step={0.05} />
        </Field>
        <Field label="Max Cap (pF)" tip={TOOLTIPS.cts_max_cap}>
          <Inp type="number" value={config.cts_max_cap} onChange={v => set("cts_max_cap", v)} min={0.01} max={0.5} step={0.01} />
        </Field>
      </div>
      <Field label="Buffer Cells (space-separated)" tip={TOOLTIPS.cts_buf_list}>
        <Inp value={config.cts_buf_list} onChange={v => set("cts_buf_list", v)} />
      </Field>
      <div className="grid grid-cols-2 gap-3 border-t border-[#2a2a3a] pt-3">
        <Field label="✓ WNS Margin (ns)" tip={TOOLTIPS.wns_margin_ns}>
          <Inp type="number" value={config.wns_margin_ns ?? ""} onChange={v => set("wns_margin_ns", isNaN(v) ? "" : v)} min={0} max={10} step={0.1} />
        </Field>
      </div>
    </div>
  );

  if (stageId === "spef") return (
    <div className="space-y-3">
      <LibCorner />
      <p className="text-xs text-[#888896]">RC extraction runs automatically after routing. Results are used by timing analysis if available.</p>
    </div>
  );

  if (stageId === "drc") return (
    <p className="text-xs text-[#888896]">No configuration needed — DRC reads the routed DEF and exports GDS automatically.</p>
  );

  return null;
}

// Verification checks UI 

function CheckStatusIcon({ status }) {
  if (status === "ok")      return <CheckCircle2 className="w-4 h-4 text-green-400 shrink-0 mt-0.5" />;
  if (status === "warning") return <AlertCircle  className="w-4 h-4 text-yellow-400 shrink-0 mt-0.5" />;
  if (status === "error")   return <AlertCircle  className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />;
  return <Circle className="w-4 h-4 text-gray-500 shrink-0 mt-0.5" />;
}

const CHECK_BORDER_CLS = {
  ok: "border-[#1e1e2e]", warning: "border-yellow-800",
  error: "border-red-800", unset: "border-[#2a2a3a] border-dashed",
};

function ChecksPanel({ data, onOpenFix }) {
  const checks = data?.checks || [];
  return (
    <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
      {checks.length === 0 && (
        <div className="text-xs text-[#888896]">No checks available for this stage yet — run the stage first.</div>
      )}
      {checks.map(c => (
        <div key={c.id}
          className={"bg-[#12121a] border rounded-lg p-3 flex items-start gap-3 " + (CHECK_BORDER_CLS[c.status] || "border-[#1e1e2e]")}>
          <CheckStatusIcon status={c.status} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold">{c.label}</span>
              <span className="font-mono text-xs text-[#8b5cf6] shrink-0">
                {c.value ?? "—"}{c.value != null ? (c.unit || "") : ""}
              </span>
            </div>
            <p className="text-xs text-[#888896] mt-0.5">{c.message}</p>
          </div>
          {(c.status === "warning" || c.status === "error") && (
            <button onClick={() => onOpenFix(c)}
              className="shrink-0 px-2.5 py-1 rounded text-xs font-semibold border border-[#8b5cf6] text-[#8b5cf6]
                hover:bg-[#8b5cf6] hover:text-white transition-colors">
              Explain & Fix
            </button>
          )}
        </div>
      ))}
      {data?.guidance && (
        <div className="bg-yellow-900 bg-opacity-20 border border-yellow-800 rounded-lg p-3">
          <p className="text-xs font-semibold text-yellow-400 mb-1">No config-level fix — look upstream</p>
          <p className="text-xs text-yellow-200">{data.guidance}</p>
        </div>
      )}
    </div>
  );
}

function ExplainFixDialog({ stageId, checkData, focusCheck, onApply, onApplyAndRerun, onClose }) {
  const failing = (checkData?.checks || []).filter(c => c.status === "warning" || c.status === "error");
  // Never show a no-op fix — proposed must differ from current
  const fixes = (checkData?.fixes || []).filter(f => f.proposed_value !== f.current_value);
  const [explanation, setExplanation] = useState("");
  const [loading, setLoading] = useState(true);
  const [vals, setVals] = useState(() => fixes.map(f => String(f.proposed_value)));

  useEffect(() => {
    let alive = true;
    callCheckExplain({ stage: stageId, checks: failing, fixes, guidance: checkData?.guidance || "" })
      .then(e => { if (alive) setExplanation(e); })
      .catch(() => { if (alive) setExplanation("AI explanation unavailable — the computed fixes below are still valid."); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  const parseVal = (fix, s) => {
    if (typeof fix.proposed_value !== "number") return s;
    const n = parseFloat(s);
    return isNaN(n) ? fix.proposed_value : n;
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-60 z-50 flex items-center justify-center p-6">
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl w-[560px] max-h-[85vh] overflow-y-auto p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold">Explain & Fix — {focusCheck?.label || stageId}</h2>
          <button onClick={onClose} className="text-[#888896] hover:text-white text-lg leading-none">✕</button>
        </div>

        {/* AI explanation — the LLM explains, it never computes values */}
        <div className="bg-[#0a0a0f] border border-[#2a2a3a] rounded-lg p-3">
          <p className="text-xs font-semibold text-[#8b5cf6] mb-1.5">AI Explanation</p>
          {loading
            ? <div className="flex items-center gap-2 text-xs text-[#888896]"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Analyzing checks…</div>
            : <p className="text-xs text-[#e0e0e8] leading-relaxed">{explanation}</p>}
        </div>

        {/* Deterministic pre-computed fixes */}
        {fixes.length > 0 ? fixes.map((fix, i) => (
          <div key={fix.id || i} className="bg-[#0d0d16] border border-[#2a2a3a] rounded-lg p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold">{fix.label}</span>
              <span className="font-mono text-xs text-[#888896]">{fix.stage} → {fix.field}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="line-through font-mono text-sm text-[#888896]">{String(fix.current_value ?? "—")}</span>
              <span className="text-[#8b5cf6]">→</span>
              <input
                value={vals[i]}
                onChange={e => setVals(p => p.map((v, j) => j === i ? e.target.value : v))}
                className="flex-1 bg-[#0a0a0f] border border-[#8b5cf6] rounded px-2 py-1 text-sm font-mono text-[#e0e0e8] outline-none" />
            </div>
            <p className="text-xs text-[#888896]">{fix.reason}</p>
            <p className="text-xs text-[#666672] font-mono leading-relaxed bg-[#0a0a0f] rounded p-2">{fix.context}</p>
            <div className="flex gap-2 pt-1">
              <button onClick={() => { onApply(fix, parseVal(fix, vals[i])); onClose(); }}
                className="flex-1 py-1.5 rounded text-xs font-semibold border border-[#8b5cf6] text-[#8b5cf6]
                  hover:bg-[#8b5cf6] hover:text-white transition-colors">
                Apply
              </button>
              <button onClick={() => { const v = parseVal(fix, vals[i]); onClose(); onApplyAndRerun(fix, v, stageId); }}
                className="flex-1 py-1.5 rounded text-xs font-semibold bg-[#8b5cf6] text-white hover:bg-[#a78bfa] transition-colors">
                Apply & Re-run {fix.stage !== stageId ? "from " + fix.stage : ""}
              </button>
            </div>
          </div>
        )) : (
          <div className="bg-[#0d0d16] border border-[#2a2a3a] rounded-lg p-3">
            <p className="text-xs text-[#888896]">
              {checkData?.guidance ||
                "No deterministic config fix is available for this check. See the explanation above."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function AIExplainer({ logs, stage, runId, config, verilogFiles, outputs }) {
  const [dialog,  setDialog]  = useState(null);
  const [loading, setLoading] = useState(false);

  const explain = async () => {
    setLoading(true);
    try {
      const reply = await callPDAssist({ mode: "error", stage, logs, runId, config, verilogFiles, outputs });
      setDialog(reply);
    } catch (err) {
      setDialog("Could not reach AI assistant: " + err.message);
    }
    setLoading(false);
  };

  return (
    <>
      {dialog && <AIDialog title={"AI Error Analysis — " + stage} content={dialog} onClose={() => setDialog(null)} />}
      <button onClick={explain} disabled={loading}
        className="mt-2 flex items-center gap-2 px-3 py-1.5 rounded text-xs font-semibold
          bg-gradient-to-r from-[#8b5cf6] to-[#6d28d9] text-white
          hover:from-[#a78bfa] hover:to-[#8b5cf6] transition-all
          disabled:opacity-50 disabled:cursor-not-allowed w-full justify-center">
        {loading ? <><Loader2 className="w-3 h-3 animate-spin" /> Analyzing…</> : "✦ Explain this error with AI"}
      </button>
    </>
  );
}

function QoRAdvisor({ logs, stage, runId, config, verilogFiles, outputs }) {
  const [dialog,     setDialog]     = useState(null);
  const [title,      setTitle]      = useState("");
  const [loadingQor, setLoadingQor] = useState(false);
  const [loadingOpt, setLoadingOpt] = useState(false);

  const analyze = async (mode) => {
    const setL = mode === "qor" ? setLoadingQor : setLoadingOpt;
    setL(true);
    const t = mode === "qor" ? "QoR Analysis — " + stage : "Optimization Guide — " + stage;
    try {
      const reply = await callPDAssist({ mode, stage, logs, runId, config, verilogFiles, outputs });
      setTitle(t);
      setDialog(reply);
    } catch (err) {
      setTitle(t);
      setDialog("Could not reach AI assistant: " + err.message);
    }
    setL(false);
  };

  return (
    <>
      {dialog && <AIDialog title={title} content={dialog} onClose={() => setDialog(null)} />}
      <div className="mt-2 space-y-1.5">
        <button onClick={() => analyze("qor")} disabled={loadingQor || loadingOpt}
          className="flex items-center gap-1.5 px-2 py-1.5 rounded text-xs font-semibold
            bg-gradient-to-r from-[#059669] to-[#047857] text-white
            hover:from-[#10b981] hover:to-[#059669] transition-all
            disabled:opacity-50 disabled:cursor-not-allowed w-full justify-center">
          {loadingQor ? <><Loader2 className="w-3 h-3 animate-spin" /> Analyzing…</> : "✦ QoR Advisor"}
        </button>
        <button onClick={() => analyze("optimize")} disabled={loadingQor || loadingOpt}
          className="flex items-center gap-1.5 px-2 py-1.5 rounded text-xs font-semibold
            bg-gradient-to-r from-[#d97706] to-[#b45309] text-white
            hover:from-[#f59e0b] hover:to-[#d97706] transition-all
            disabled:opacity-50 disabled:cursor-not-allowed w-full justify-center">
          {loadingOpt ? <><Loader2 className="w-3 h-3 animate-spin" /> Analyzing…</> : "✦ Optimize Guide"}
        </button>
      </div>
    </>
  );
}


function RunHistory({ onRestore, onClose }) {
  const [runs,    setRuns]    = useState([]);
  const [loading, setLoading] = useState(true);
  const [dlState, setDlState] = useState({});

  useEffect(() => {
    fetch(PD_API + "/runs")
      .then(r => r.json())
      .then(d => { setRuns(d.runs || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const downloadZip = async (runId) => {
    setDlState(p => ({ ...p, [runId]: "downloading" }));
    try {
      const res  = await fetch(PD_API + "/download_zip/" + runId);
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = "run_" + runId + ".zip"; a.click();
      URL.revokeObjectURL(url);
      setDlState(p => ({ ...p, [runId]: "done" }));
    } catch {
      setDlState(p => ({ ...p, [runId]: "error" }));
    }
  };

  const stageColor = (stages, id) => {
    if (stages.completed_stages?.includes(id)) return "bg-green-500";
    if (stages.failed_stages?.includes(id))    return "bg-red-500";
    return "bg-[#2a2a3a]";
  };

  const STAGE_IDS = ["synthesis","floorplan","pdn","placement","cts","routing","spef","timing","drc"];

  return (
    <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50 p-6">
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl w-full max-w-3xl flex flex-col max-h-[80vh]">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#1e1e2e]">
          <p className="font-semibold text-sm text-white">Run History</p>
          <button onClick={onClose} className="text-[#888896] hover:text-white text-lg">✕</button>
        </div>

        <div className="overflow-y-auto flex-1">
          {loading && <p className="text-center text-[#888896] text-sm p-8">Loading runs…</p>}
          {!loading && runs.length === 0 && (
            <div className="text-center p-8 space-y-1">
              <p className="text-[#888896] text-sm">No previous runs found.</p>
              <p className="text-[#888896] text-xs">Make sure the PD tools container is running.</p>
              <p className="text-[#888896] text-xs">Runs persist at D:\pdtools\work\ via Docker volume.</p>
            </div>
          )}
          {!loading && runs.map(run => (
            <div key={run.run_id} className="px-5 py-4 border-b border-[#1e1e2e] hover:bg-[#1a1a25]">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-xs text-[#8b5cf6] font-semibold">{run.run_id}</span>
                    <span className="text-xs text-[#888896]">{run.design}</span>
                    <span className="text-xs text-[#888896]">{run.created ? new Date(run.created).toLocaleString() : ""}</span>
                  </div>

                  {/* Stage progress dots */}
                  <div className="flex items-center gap-1 mb-2">
                    {STAGE_IDS.map(id => (
                      <div key={id} title={id}
                        className={"w-2 h-2 rounded-full " + stageColor(run, id)} />
                    ))}
                    <span className="text-xs text-[#888896] ml-1">
                      {run.stage_count}/9 stages
                    </span>
                  </div>

                  {/* Metrics */}
                  <div className="flex items-center gap-4 text-xs text-[#888896]">
                    {run.wns_ns   && <span>WNS: <span className="text-green-400">{run.wns_ns}ns</span></span>}
                    {run.power_w  && <span>Power: <span className="text-blue-400">{parseFloat(run.power_w).toExponential(2)}W</span></span>}
                    <span>Lib: {run.cell_lib?.replace("sky130_fd_sc_", "") || "—"}</span>
                    <span>Corner: {run.corner?.toUpperCase() || "—"}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button onClick={() => onRestore(run.run_id)}
                    className="px-3 py-1.5 rounded text-xs font-semibold bg-[#8b5cf6] text-white hover:bg-[#a78bfa] transition-colors">
                    Resume
                  </button>
                  <button onClick={() => downloadZip(run.run_id)}
                    disabled={dlState[run.run_id] === "downloading"}
                    className="px-3 py-1.5 rounded text-xs font-semibold border border-[#2a2a3a] text-[#888896] hover:text-white hover:border-[#8b5cf6] transition-colors disabled:opacity-50">
                    {dlState[run.run_id] === "downloading" ? "…"
                      : dlState[run.run_id] === "done" ? "✓"
                      : <Download className="w-3 h-3" />}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function parseTimingPaths(lines) {
  const text = lines.join("\n");
  const paths = [];

  const sections = text.split(/Path Type:\s*(max|min)/);
  
  for (let i = 1; i < sections.length; i += 2) {
    const pathType = sections[i];
    const section  = sections[i + 1] || "";

    const spM = text.match(/Startpoint:\s*(\S+)/);
    const epM = section.match(/Endpoint:\s*(\S+)/);

    const steps = [];
    const pathLines = section.split("\n");
    let inPath = false;
    let dashCount = 0;

    for (const line of pathLines) {
      if (/^\s*-{5,}/.test(line)) { dashCount++; inPath = dashCount === 1; continue; }
      if (!inPath) continue;
      const m = line.match(/^\s*([\-\d\.]+)\s+([\d\.]+)\s+([v\^]?)\s+(.+)/);
      if (!m) continue;
      const delay = parseFloat(m[1]);
      const time  = parseFloat(m[2]);
      const edge  = m[3];
      const desc  = m[4].trim();
      const cellM = desc.match(/^(\S+)\s+\((\S+)\)/);
      if (cellM) {
        const pin      = cellM[1];
        const cellType = cellM[2];
        const parts    = pin.split("/");
        const name     = parts.length > 1 ? parts[parts.length - 2] : pin;
        steps.push({ delay, time, edge, pin, cellType, name, desc });
      }
    }

    const slackM    = section.match(/([\d\.]+)\s+slack \((MET|VIOLATED)\)/);
    const arrM      = section.match(/([\d\.]+)\s+data arrival time/);
    const reqM      = section.match(/([\d\.]+)\s+data required time/);

    if (steps.length > 0 || slackM) {
      paths.push({
        type:       pathType,
        startpoint: spM ? spM[1] : "unknown",
        endpoint:   epM ? epM[1] : "unknown",
        steps,
        slack:      slackM ? parseFloat(slackM[1]) : null,
        violated:   slackM ? slackM[2] === "VIOLATED" : false,
        arrival:    arrM   ? parseFloat(arrM[1])    : null,
        required:   reqM   ? parseFloat(reqM[1])    : null,
      });
    }
  }
  return paths;
}

function cellShortName(cellType) {
  return cellType.replace("sky130_fd_sc_hd__", "").replace(/_\d+$/, "");
}

function TimingPathViewer({ logs }) {
  const [activeTab, setActiveTab] = useState("setup");
  const paths    = parseTimingPaths(logs);
  const setupPath = paths.find(p => p.type === "max");
  const holdPath  = paths.find(p => p.type === "min");
  const path      = activeTab === "setup" ? setupPath : holdPath;

  if (!setupPath && !holdPath) return (
    <div className="flex-1 flex items-center justify-center text-[#888896] text-sm">
      No timing paths found. Run Timing Analysis first.
    </div>
  );

  const maxDelay = path ? Math.max(...path.steps.map(s => s.delay)) : 1;

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-[#050508]">
      {/* Tab bar */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-[#1e1e2e] shrink-0">
        {setupPath && (
          <button onClick={() => setActiveTab("setup")}
            className={"px-3 py-1 rounded text-xs font-semibold transition-colors " +
              (activeTab === "setup" ? "bg-[#8b5cf6] text-white" : "text-[#888896] hover:text-white")}>
            Setup (max)
            {setupPath && <span className={" ml-1.5 px-1.5 py-0.5 rounded text-xs " + (setupPath.violated ? "bg-red-700 text-red-100" : "bg-green-700 text-green-100")}>
              {setupPath.violated ? "VIOLATED" : "MET " + setupPath.slack?.toFixed(2) + "ns"}
            </span>}
          </button>
        )}
        {holdPath && (
          <button onClick={() => setActiveTab("hold")}
            className={"px-3 py-1 rounded text-xs font-semibold transition-colors " +
              (activeTab === "hold" ? "bg-[#8b5cf6] text-white" : "text-[#888896] hover:text-white")}>
            Hold (min)
            {holdPath && <span className={" ml-1.5 px-1.5 py-0.5 rounded text-xs " + (holdPath.violated ? "bg-red-700 text-red-100" : "bg-green-700 text-green-100")}>
              {holdPath.violated ? "VIOLATED" : "MET " + holdPath.slack?.toFixed(2) + "ns"}
            </span>}
          </button>
        )}
        <div className="flex-1" />
        {path && (
          <div className="text-xs text-[#888896]">
            {path.startpoint} → {path.endpoint}
          </div>
        )}
      </div>

      {path && (
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2">
          {/* Summary bar */}
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="bg-[#12121a] border border-[#1e1e2e] rounded-lg p-3 text-center">
              <p className="text-xs text-[#888896] mb-1">Arrival Time</p>
              <p className="text-lg font-mono font-bold text-[#e0e0e8]">{path.arrival?.toFixed(2)}ns</p>
            </div>
            <div className="bg-[#12121a] border border-[#1e1e2e] rounded-lg p-3 text-center">
              <p className="text-xs text-[#888896] mb-1">Required Time</p>
              <p className="text-lg font-mono font-bold text-[#e0e0e8]">{path.required?.toFixed(2)}ns</p>
            </div>
            <div className={"bg-[#12121a] border rounded-lg p-3 text-center " + (path.violated ? "border-red-700" : "border-green-700")}>
              <p className="text-xs text-[#888896] mb-1">Slack</p>
              <p className={"text-lg font-mono font-bold " + (path.violated ? "text-red-400" : "text-green-400")}>
                {path.slack?.toFixed(2)}ns
              </p>
            </div>
          </div>

          {/* Critical path chain */}
          <p className="text-xs font-semibold text-[#888896] uppercase tracking-wider mb-2">Critical Path</p>
          {path.steps.map((step, i) => {
            const pct     = maxDelay > 0 ? (step.delay / maxDelay) * 100 : 0;
            const isWorst = step.delay === maxDelay && maxDelay > 0;
            const isFF    = step.cellType.includes("dfxtp") || step.cellType.includes("dfrtp");
            const isInput = step.cellType === "in";

            return (
              <div key={i} className={"rounded-lg border p-3 " +
                (isWorst ? "border-orange-600 bg-orange-900 bg-opacity-10" :
                 isFF    ? "border-[#8b5cf6] bg-[#8b5cf6] bg-opacity-5" :
                 isInput ? "border-[#2a2a3a] bg-[#0d0d16]" :
                 "border-[#1e1e2e] bg-[#12121a]")}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className={"text-xs px-1.5 py-0.5 rounded font-mono " +
                      (isFF ? "bg-[#8b5cf6] bg-opacity-20 text-[#8b5cf6]" :
                       isInput ? "bg-blue-900 bg-opacity-30 text-blue-400" :
                       "bg-[#1e1e2e] text-[#888896]")}>
                      {isFF ? "FF" : isInput ? "IN" : "COMB"}
                    </span>
                    <span className="text-sm font-mono text-[#e0e0e8] font-semibold">{step.name}</span>
                    <span className="text-xs text-[#888896]">{cellShortName(step.cellType)}</span>
                    {isWorst && <span className="text-xs text-orange-400 font-semibold">← worst</span>}
                  </div>
                  <div className="text-right">
                    <span className={"text-sm font-mono font-bold " +
                      (step.delay > 0.15 ? "text-orange-400" : step.delay > 0.05 ? "text-yellow-400" : "text-[#888896]")}>
                      +{step.delay.toFixed(2)}ns
                    </span>
                    <span className="text-xs text-[#888896] ml-2">@ {step.time.toFixed(2)}ns</span>
                  </div>
                </div>
                {/* Delay bar */}
                {step.delay > 0 && (
                  <div className="h-1 bg-[#1e1e2e] rounded-full overflow-hidden">
                    <div className={"h-full rounded-full transition-all " +
                      (isWorst ? "bg-orange-500" : step.delay > 0.1 ? "bg-yellow-500" : "bg-[#8b5cf6]")}
                      style={{ width: pct + "%" }} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function MultiCornerPanel({ runId, configs }) {
  const [results,  setResults]  = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState(null);

  const corners = [
    { id: "tt", label: "TT",  desc: "25°C 1.80V",  color: "text-blue-400",   bg: "bg-blue-900"  },
    { id: "ss", label: "SS",  desc: "100°C 1.60V", color: "text-yellow-400", bg: "bg-yellow-900"},
    { id: "ff", label: "FF",  desc: "-40°C 1.95V", color: "text-green-400",  bg: "bg-green-900" },
  ];

  const runAllCorners = async () => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    setResults(null);

    const cornerResults = {};
    for (const corner of corners) {
      try {
        const body = {
          ...configs["timing"],
          top_module: "top",
          run_id: runId,
          corner: corner.id,
        };
        const res = await fetch(PD_API + "/timing", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!res.ok) { cornerResults[corner.id] = { error: "HTTP " + res.status }; continue; }

        const reader  = res.body.getReader();
        const decoder = new TextDecoder();
        let text = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          text += decoder.decode(value, { stream: true });
        }

        const lines  = text.split("\n");
        const wnsM   = text.match(/wns\s+(?:max\s+)?([\-\d\.]+)/i);
        const tnsM   = text.match(/tns\s+(?:max\s+)?([\-\d\.]+)/i);
        const slackM = text.match(/([\d\.]+)\s+slack \(MET\)/);
        const holdM  = text.match(/([\d\.]+)\s+slack \(MET\).*?min/s);
        const powerM = text.match(/Total\s+[\d\.e\+\-]+\s+[\d\.e\+\-]+\s+[\d\.e\+\-]+\s+([\d\.e\+\-]+)/);

        cornerResults[corner.id] = {
          wns:     wnsM   ? parseFloat(wnsM[1])   : null,
          tns:     tnsM   ? parseFloat(tnsM[1])   : null,
          slack:   slackM ? parseFloat(slackM[1]) : null,
          power:   powerM ? powerM[1]              : null,
          passed:  !text.includes("[ERROR") && (slackM ? parseFloat(slackM[1]) >= 0 : true),
          lines,
        };
      } catch (err) {
        cornerResults[corner.id] = { error: err.message };
      }
    }
    setResults(cornerResults);
    setLoading(false);
  };

  const fmt = (v, suffix="ns") => v != null ? v.toFixed(2) + suffix : "—";

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-[#1e1e2e] flex items-center justify-between shrink-0">
        <div>
          <p className="text-sm font-semibold text-[#e0e0e8]">Multi-Corner Timing</p>
          <p className="text-xs text-[#888896]">Runs timing at SS / TT / FF simultaneously</p>
        </div>
        <button onClick={runAllCorners} disabled={loading || !runId}
          className="flex items-center gap-2 px-4 py-2 rounded font-semibold text-sm
            bg-[#8b5cf6] text-white hover:bg-[#a78bfa] transition-colors
            disabled:opacity-50 disabled:cursor-not-allowed">
          {loading
            ? <><Loader2 className="w-4 h-4 animate-spin" /> Running corners…</>
            : "▶ Run All Corners"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {!results && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-[#888896] gap-3">
            <p className="text-sm">Click "Run All Corners" to analyze timing across all PVT corners.</p>
            <p className="text-xs">Runs SS (worst), TT (typical), FF (best) sequentially.</p>
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center h-full gap-4">
            <Loader2 className="w-8 h-8 text-[#8b5cf6] animate-spin" />
            <p className="text-sm text-[#888896]">Running timing analysis across 3 corners…</p>
          </div>
        )}

        {results && (
          <div className="space-y-4">
            {/* Summary table */}
            <div className="bg-[#12121a] border border-[#1e1e2e] rounded-lg overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[#1e1e2e]">
                    <th className="text-left px-4 py-2 text-[#888896] font-semibold">Corner</th>
                    <th className="text-right px-4 py-2 text-[#888896] font-semibold">WNS</th>
                    <th className="text-right px-4 py-2 text-[#888896] font-semibold">TNS</th>
                    <th className="text-right px-4 py-2 text-[#888896] font-semibold">Slack</th>
                    <th className="text-right px-4 py-2 text-[#888896] font-semibold">Power</th>
                    <th className="text-right px-4 py-2 text-[#888896] font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {corners.map(corner => {
                    const r = results[corner.id];
                    if (!r) return null;
                    if (r.error) return (
                      <tr key={corner.id} className="border-b border-[#1e1e2e]">
                        <td className="px-4 py-3">
                          <span className={corner.color + " font-mono font-bold"}>{corner.label}</span>
                          <span className="text-[#888896] ml-2">{corner.desc}</span>
                        </td>
                        <td colSpan={5} className="px-4 py-3 text-red-400 text-right">{r.error}</td>
                      </tr>
                    );
                    return (
                      <tr key={corner.id} className="border-b border-[#1e1e2e]">
                        <td className="px-4 py-3">
                          <span className={corner.color + " font-mono font-bold"}>{corner.label}</span>
                          <span className="text-[#888896] ml-2">{corner.desc}</span>
                        </td>
                        <td className={"px-4 py-3 text-right font-mono " + (r.wns < 0 ? "text-red-400" : "text-[#e0e0e8]")}>
                          {fmt(r.wns)}
                        </td>
                        <td className={"px-4 py-3 text-right font-mono " + (r.tns < 0 ? "text-red-400" : "text-[#e0e0e8]")}>
                          {fmt(r.tns)}
                        </td>
                        <td className={"px-4 py-3 text-right font-mono " + (r.slack != null && r.slack >= 0 ? "text-green-400" : "text-red-400")}>
                          {fmt(r.slack)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-[#888896]">
                          {r.power ? parseFloat(r.power).toExponential(2) + "W" : "—"}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className={"px-2 py-0.5 rounded text-xs font-semibold " +
                            (r.passed ? "bg-green-700 text-green-100" : "bg-red-700 text-red-100")}>
                            {r.passed ? "MET" : "VIOLATED"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Worst corner callout */}
            {(() => {
              const worstCorner = corners
                .filter(c => results[c.id] && results[c.id].slack != null)
                .sort((a, b) => (results[a.id].slack ?? 99) - (results[b.id].slack ?? 99))[0];
              const bestCorner = corners
                .filter(c => results[c.id] && results[c.id].slack != null)
                .sort((a, b) => (results[b.id].slack ?? -99) - (results[a.id].slack ?? -99))[0];
              if (!worstCorner) return null;
              const wr = results[worstCorner.id];
              return (
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-red-900 bg-opacity-20 border border-red-800 rounded-lg p-3">
                    <p className="text-xs font-semibold text-red-400 mb-1">Worst Corner — {worstCorner.label}</p>
                    <p className="text-xs text-red-300">
                      Slack: {fmt(wr.slack)} — {wr.passed ? "passes but tightest" : "VIOLATED — sign-off risk"}
                    </p>
                    <p className="text-xs text-[#888896] mt-1">Use SS corner for setup sign-off</p>
                  </div>
                  <div className="bg-green-900 bg-opacity-20 border border-green-800 rounded-lg p-3">
                    <p className="text-xs font-semibold text-green-400 mb-1">Best Corner — {bestCorner.label}</p>
                    <p className="text-xs text-green-300">
                      Slack: {fmt(results[bestCorner.id].slack)}
                    </p>
                    <p className="text-xs text-[#888896] mt-1">Use FF corner for hold sign-off</p>
                  </div>
                </div>
              );
            })()}
          </div>
        )}
      </div>
    </div>
  );
}

function parseDRCViolations(lines) {
  const text = lines.join("\n");
  const violations = [];

  const summaryMatch = text.match(/\[DRC SUMMARY\]([\s\S]*?)(?=\[|$)/);
  if (summaryMatch) {
    const summaryLines = summaryMatch[1].split("\n");
    for (const line of summaryLines) {
      const m = line.match(/\s+(.+?):\s*(\d+)\s+violations?/i);
      if (m) violations.push({ type: m[1].trim(), count: parseInt(m[2]) });
    }
  }

  const routeViolLines = lines.filter(l =>
    l.includes("Viol/Layer") || l.includes("Metal Spacing") ||
    l.includes("Short") || l.includes("Cut Spacing") || l.includes("NS Metal")
  );

  const isClean  = text.includes("DRC clean") || text.includes("No violations found") || text.includes("DRC clean");
  const totalViol = violations.reduce((s, v) => s + v.count, 0);

  return { violations, isClean, totalViol, hasRoutingViols: routeViolLines.length > 0, routeViolLines };
}

const DRC_EXPLANATIONS = {
  "Metal Spacing":  { short: "Metal wires too close together",         fix: "Reduce Placement Density or increase Die Area in Floorplan Config" },
  "Short":          { short: "Two different nets are shorted together", fix: "Increase Congestion Iterations in Routing Config" },
  "Cut Spacing":    { short: "Via cuts are too close together",         fix: "Increase Cell Padding in Placement Config" },
  "Min Width":      { short: "Metal wire is narrower than minimum",     fix: "This is usually auto-fixed by the router — try re-running Routing" },
  "Enclosure":      { short: "Via not properly enclosed by metal",      fix: "Try different Bottom/Top Layer settings in Routing Config" },
  "Density":        { short: "Metal density out of allowed range",      fix: "Adjust Die Area and Core Utilization in Floorplan Config" },
  "Antenna":        { short: "Long metal wire accumulates charge",      fix: "Enable Antenna Fixing in Routing Config" },
  "NS Metal":       { short: "Non-standard metal routing issue",        fix: "Change Bottom Layer to met1 in Routing Config" },
};

function getDRCExplanation(violType) {
  for (const [key, val] of Object.entries(DRC_EXPLANATIONS)) {
    if (violType.toLowerCase().includes(key.toLowerCase())) return val;
  }
  return { short: "Design rule violation", fix: "Review routing configuration and placement density" };
}

function DRCPanel({ logs, runId, configs, verilogFiles, outputs }) {
  const [aiExplain, setAiExplain] = useState(null);
  const [loading,   setLoading]   = useState(false);
  const drc = parseDRCViolations(logs);

  const explainWithAI = async () => {
    setLoading(true);
    try {
      const reply = await callPDAssist({
        mode: "error", stage: "DRC + GDS",
        logs, runId, config: configs["drc"] || {},
        verilogFiles, outputs,
      });
      setAiExplain(reply);
    } catch (err) {
      setAiExplain("Could not reach AI: " + err.message);
    }
    setLoading(false);
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-[#050508]">
      {/* Status banner */}
      <div className={"rounded-lg border p-4 " +
        (drc.isClean   ? "bg-green-900 bg-opacity-15 border-green-800" :
         drc.totalViol > 0 ? "bg-red-900 bg-opacity-15 border-red-800" :
         "bg-[#12121a] border-[#1e1e2e]")}>
        <div className="flex items-center justify-between">
          <div>
            <p className={"text-sm font-bold " +
              (drc.isClean ? "text-green-400" : drc.totalViol > 0 ? "text-red-400" : "text-[#e0e0e8]")}>
              {drc.isClean   ? "✓ DRC Clean — No violations" :
               drc.totalViol > 0 ? "✗ " + drc.totalViol + " DRC violations found" :
               "DRC results pending — run DRC + GDS stage"}
            </p>
            <p className="text-xs text-[#888896] mt-1">
              {drc.isClean   ? "Design passes all Sky130HD design rules — ready for tapeout" :
               drc.totalViol > 0 ? "Fix violations before tapeout" : ""}
            </p>
          </div>
          {(drc.totalViol > 0 || drc.hasRoutingViols) && (
            <button onClick={explainWithAI} disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold
                bg-gradient-to-r from-[#8b5cf6] to-[#6d28d9] text-white
                hover:from-[#a78bfa] transition-all disabled:opacity-50 shrink-0 ml-3">
              {loading ? <><Loader2 className="w-3 h-3 animate-spin" /> Analyzing…</> : "✦ Explain with AI"}
            </button>
          )}
        </div>
      </div>

      {/* Violations breakdown */}
      {drc.violations.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-[#888896] uppercase tracking-wider">Violations by Type</p>
          {drc.violations.map((v, i) => {
            const exp = getDRCExplanation(v.type);
            return (
              <div key={i} className="bg-[#12121a] border border-[#1e1e2e] rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="bg-red-700 text-red-100 text-xs font-mono px-1.5 py-0.5 rounded font-bold">
                    {v.count}×
                  </span>
                  <span className="text-sm font-semibold text-[#e0e0e8]">{v.type}</span>
                </div>
                <p className="text-xs text-[#888896] mb-1">{exp.short}</p>
                <p className="text-xs text-[#8b5cf6]">↳ Fix: {exp.fix}</p>
              </div>
            );
          })}
        </div>
      )}

      {/* Routing violations from DRT */}
      {drc.hasRoutingViols && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-[#888896] uppercase tracking-wider">
            Routing DRC Violations {drc.violations.length === 0 ? "(from router)" : "(additional)"}
          </p>
          {drc.routeViolLines.map((line, i) => (
            <div key={i} className="bg-[#12121a] border border-[#1e1e2e] rounded px-3 py-2">
              <p className="text-xs font-mono text-[#e0e0e8]">{line.trim()}</p>
            </div>
          ))}
          <p className="text-xs text-[#8b5cf6]">
            ↳ Fix: Reduce Placement Density or increase Congestion Iterations in Routing Config
          </p>
        </div>
      )}

      {/* AI Explanation */}
      {aiExplain && (
        <div className="bg-[#0d0d1a] border border-[#4c1d95] rounded-lg p-4 text-xs text-[#c0c0d0] leading-relaxed whitespace-pre-wrap">
          {aiExplain}
        </div>
      )}
    </div>
  );
}

function PDChatAssistant({ runId, configs, verilogFiles, outputs, stages }) {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Hi! I'm your PD assistant. Ask me anything about your design — timing, area, power, routing, or how to improve your results.",
    }
  ]);
  const [input,   setInput]   = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    if (bottomRef.current) bottomRef.current.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const getContext = async () => {
    let run_meta = {};
    try {
      const metaRes = await fetch(PD_API + "/run/" + runId + "/meta");
      if (metaRes.ok) run_meta = await metaRes.json();
    } catch (_) {}

    const verilog = Object.values(verilogFiles || {}).join("\n\n").slice(0, 600);
    const allLogs = Object.entries(outputs || {})
      .filter(([_, lines]) => lines.length > 0)
      .map(([id, lines]) => "=== " + id.toUpperCase() + " ===\n" + lines.slice(-30).join("\n"))
      .join("\n\n")
      .slice(0, 25000);

    const completedStages = stages.filter(s => s.status === "complete").map(s => s.name);

    return { run_meta, verilog, allLogs, completedStages };
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput("");
    setMessages(p => [...p, { role: "user", text: userMsg }]);
    setLoading(true);

    try {
      const { run_meta, verilog, allLogs, completedStages } = await getContext();

      const history = messages.slice(-6).map(m => ({
        role: m.role === "user" ? "user" : "assistant",
        content: m.text,
      }));

      let authToken = "";
      try {
        for (const key of Object.keys(localStorage)) {
          if (key.includes("auth") || key.includes("session") || key.startsWith("sb-")) {
            const val = JSON.parse(localStorage.getItem(key) || "{}");
            if (val?.access_token) { authToken = val.access_token; break; }
            if (val?.session?.access_token) { authToken = val.session.access_token; break; }
          }
        }
      } catch (_) {}

      const res = await fetch(MAIN_API + "/pd_chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { "Authorization": "Bearer " + authToken } : {}),
        },
        body: JSON.stringify({
          message: userMsg,
          history,
          run_meta,
          verilog,
          allLogs,
          completedStages,
          configs: {
            timing: configs["timing"],
            placement: configs["placement"],
            routing: configs["routing"],
          },
        }),
      });

      if (!res.ok) throw new Error("Backend error " + res.status);
      const data = await res.json();
      setMessages(p => [...p, { role: "assistant", text: data.reply || "Sorry, I couldn't process that." }]);
    } catch (err) {
      setMessages(p => [...p, { role: "assistant", text: "Error: " + err.message }]);
    }
    setLoading(false);
  };

  return (
    <div className="flex flex-col h-full bg-[#050508]">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.map((msg, i) => (
          <div key={i} className={"flex " + (msg.role === "user" ? "justify-end" : "justify-start")}>
            <div className={"max-w-[85%] rounded-xl px-3 py-2 text-xs leading-relaxed " +
              (msg.role === "user"
                ? "bg-[#8b5cf6] text-white rounded-br-none"
                : "bg-[#1a1a25] border border-[#2a2a3a] text-[#c0c0d0] rounded-bl-none")}>
              <p className="whitespace-pre-wrap">{msg.text}</p>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-[#1a1a25] border border-[#2a2a3a] rounded-xl rounded-bl-none px-3 py-2">
              <div className="flex gap-1 items-center">
                <div className="w-1.5 h-1.5 rounded-full bg-[#8b5cf6] animate-bounce" style={{animationDelay:"0ms"}} />
                <div className="w-1.5 h-1.5 rounded-full bg-[#8b5cf6] animate-bounce" style={{animationDelay:"150ms"}} />
                <div className="w-1.5 h-1.5 rounded-full bg-[#8b5cf6] animate-bounce" style={{animationDelay:"300ms"}} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-3 py-3 border-t border-[#1e1e2e] shrink-0">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && sendMessage()}
            placeholder="Ask about timing, area, power, routing..."
            className="flex-1 bg-[#0a0a0f] border border-[#2a2a3a] rounded-lg px-3 py-2 text-xs text-[#e0e0e8] placeholder-[#888896] focus:border-[#8b5cf6] outline-none"
          />
          <button onClick={sendMessage} disabled={loading || !input.trim()}
            className="px-3 py-2 rounded-lg bg-[#8b5cf6] text-white text-xs font-semibold
              hover:bg-[#a78bfa] transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
            Send
          </button>
        </div>
        <p className="text-xs text-[#888896] mt-1.5 text-center">1 credit per message · Context: {Object.keys(outputs || {}).filter(k => (outputs[k]||[]).length > 0).length} stages</p>
      </div>
    </div>
  );
}

function TimingClosureAdvisor({ logs, runId, configs, setConfigs, verilogFiles, outputs, stages, setSelected, onRerunStages }) {
  const [phase,     setPhase]     = useState("idle");  
  const [plan,      setPlan]      = useState(null);
  const [chosen,    setChosen]    = useState(0);
  const [progress,  setProgress]  = useState([]);
  const [beforeWns, setBeforeWns] = useState(null);
  const [afterWns,  setAfterWns]  = useState(null);
  const [error,     setError]     = useState(null);
  const [showModal, setShowModal] = useState(false);

  const getCurrentWns = () => {
    const text = (logs || []).join("\n");
    const m = text.match(/wns\s+(?:max\s+)?([\-\d\.]+)/i);
    return m ? parseFloat(m[1]) : null;
  };

  const analyze = async () => {
    setPhase("analyzing");
    setError(null);
    const wns = getCurrentWns();
    setBeforeWns(wns);

    let authToken = "";
    try {
      for (const key of Object.keys(localStorage)) {
        if (key.includes("auth") || key.includes("session") || key.startsWith("sb-")) {
          const val = JSON.parse(localStorage.getItem(key) || "{}");
          if (val?.access_token) { authToken = val.access_token; break; }
          if (val?.session?.access_token) { authToken = val.session.access_token; break; }
        }
      }
    } catch (_) {}

    const allLogs = Object.entries(outputs || {})
      .filter(([_, lines]) => lines.length > 0)
      .map(([id, lines]) => "=== " + id.toUpperCase() + " ===\n" + lines.slice(-50).join("\n"))
      .join("\n\n")
      .slice(0, 30000);

    try {
      const res = await fetch(MAIN_API + "/pd_timing_fix", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { "Authorization": "Bearer " + authToken } : {}),
        },
        body: JSON.stringify({ allLogs, configs, verilog: Object.values(verilogFiles || {}).join("\n").slice(0, 600) }),
      });
      if (!res.ok) throw new Error("Backend error " + res.status);
      const data = await res.json();
      if (data.timing_met) {
        setPhase("idle");
        return;
      }
      setPlan(data);
      setChosen(0);
      setPhase("plan");
      setShowModal(true);
    } catch (err) {
      setError(err.message);
      setPhase("idle");
    }
  };

  const applyFix = async () => {
    if (!plan || !plan.strategies[chosen]) return;
    const strategy = plan.strategies[chosen];
    setPhase("running");
    setShowModal(true);
    setProgress([]);

    const newConfigs = { ...configs };
    Object.entries(strategy.config_changes).forEach(([stage, changes]) => {
      newConfigs[stage] = { ...(newConfigs[stage] || {}), ...changes };
    });
    setConfigs(newConfigs);

    const stagesToRun = strategy.stages_to_rerun;

    setProgress(stagesToRun.map(id => ({ id, status: "waiting" })));
    for (const stageId of stagesToRun) {
      setProgress(p => p.map(s => s.id === stageId ? { ...s, status: "running" } : s));
      try {
        await onRerunStages(stageId, newConfigs);
        setProgress(p => p.map(s => s.id === stageId ? { ...s, status: "done" } : s));
      } catch (err) {
        setProgress(p => p.map(s => s.id === stageId ? { ...s, status: "error" } : s));
        setError("Failed at " + stageId + ": " + err.message);
        setPhase("done");
        return;
      }
    }

    const timingLogs = outputs["timing"] || [];
    const text = timingLogs.join("\n");
    const m = text.match(/wns\s+(?:max\s+)?([\-\d\.]+)/i);
    setAfterWns(m ? parseFloat(m[1]) : null);
    setPhase("done");
    setShowModal(true);
  };

  const reset = () => { setPhase("idle"); setPlan(null); setProgress([]); setBeforeWns(null); setAfterWns(null); setError(null); };

  const wns = getCurrentWns();
  const hasViolation = wns !== null && wns < 0;

  if (!hasViolation && phase === "idle") return null;

  return (
    <>
      {/* Trigger button — always visible when violation exists */}
      {hasViolation && (
        <button onClick={() => { if (phase === "idle") analyze(); else setShowModal(true); }}
          disabled={phase === "analyzing"}
          className={"mt-2 w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold transition-all border " +
            (phase === "analyzing"
              ? "bg-[#1a1a25] border-[#2a2a3a] text-[#888896] cursor-not-allowed"
              : "bg-gradient-to-r from-red-700 to-red-900 text-white hover:from-red-600 hover:to-red-800 border-red-700")}>
          {phase === "analyzing"
            ? <><Loader2 className="w-3 h-3 animate-spin" /> Analyzing…</>
            : <>⚡ Fix Timing — WNS {wns !== null ? wns.toFixed(2) : "?"}ns</>}
        </button>
      )}

      {/* Modal */}
      {showModal && (phase === "plan" || phase === "running" || phase === "done") && (
        <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50 p-6">
          <div className="bg-[#12121a] border border-[#8b5cf6] rounded-xl w-full max-w-xl flex flex-col max-h-[85vh]">

            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#1e1e2e] shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-[#8b5cf6] text-sm">⚡</span>
                <p className="font-semibold text-sm text-white">Timing Closure Advisor</p>
                {phase === "done" && afterWns !== null && (
                  <span className={"text-xs px-2 py-0.5 rounded font-semibold " +
                    (afterWns >= 0 ? "bg-green-700 text-green-100" : "bg-yellow-700 text-yellow-100")}>
                    {afterWns >= 0 ? "CLOSED" : "PARTIAL"}
                  </span>
                )}
              </div>
              {phase !== "running" && (
                <button onClick={() => { setShowModal(false); if (phase === "done") reset(); }}
                  className="text-[#888896] hover:text-white text-lg leading-none">✕</button>
              )}
            </div>

            <div className="overflow-y-auto flex-1 px-5 py-4 space-y-4">

              {/* AI Explanation */}
              {plan?.explanation && (
                <div className="bg-[#0d0d1a] border border-[#2a2a3a] rounded-lg p-3">
                  <p className="text-xs text-[#c0c0d0] leading-relaxed">{plan.explanation}</p>
                </div>
              )}

              {/* Strategy options */}
              {phase === "plan" && plan && (
                <>
                  <p className="text-xs font-semibold text-[#888896] uppercase tracking-wider">Choose a fix strategy</p>
                  <div className="space-y-2">
                    {plan.strategies.map((s, i) => (
                      <div key={i} onClick={() => setChosen(i)}
                        className={"rounded-lg border p-3 cursor-pointer transition-all " +
                          (chosen === i ? "border-[#8b5cf6] bg-[#8b5cf6] bg-opacity-10" : "border-[#2a2a3a] bg-[#0d0d16] hover:border-[#3a3a4a]")}>
                        <div className="flex items-start gap-3">
                          <div className={"w-4 h-4 rounded-full border-2 flex-shrink-0 mt-0.5 transition-all " +
                            (chosen === i ? "border-[#8b5cf6] bg-[#8b5cf6]" : "border-[#3a3a4a]")} />
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-semibold text-[#e0e0e8] mb-1">{s.description}</p>
                            <p className="text-xs text-[#888896] mb-1">Re-runs: <span className="font-mono">{s.stages_to_rerun.join(" → ")}</span></p>
                            <p className="text-xs text-green-400">{s.expected_improvement}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="flex gap-2 pt-1">
                    <button onClick={applyFix}
                      className="flex-1 py-2 rounded-lg text-xs font-semibold bg-[#8b5cf6] text-white hover:bg-[#a78bfa] transition-colors">
                      ▶ Apply Fix & Re-run
                    </button>
                    <button onClick={() => { setShowModal(false); reset(); }}
                      className="px-4 py-2 rounded-lg text-xs text-[#888896] hover:text-white border border-[#2a2a3a] hover:border-[#3a3a4a] transition-colors">
                      Cancel
                    </button>
                  </div>
                </>
              )}

              {/* Running progress */}
              {phase === "running" && (
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-[#888896] uppercase tracking-wider">Re-running stages…</p>
                  {progress.map((s, i) => (
                    <div key={i} className={"flex items-center gap-3 px-3 py-2 rounded-lg border " +
                      (s.status === "done" ? "border-green-800 bg-green-900 bg-opacity-10" :
                       s.status === "error" ? "border-red-800 bg-red-900 bg-opacity-10" :
                       "border-[#2a2a3a] bg-[#0d0d16]")}>
                      {s.status === "running" && <Loader2 className="w-3 h-3 animate-spin text-[#8b5cf6] flex-shrink-0" />}
                      {s.status === "done"    && <span className="text-green-400 text-xs flex-shrink-0">✓</span>}
                      {s.status === "error"   && <span className="text-red-400 text-xs flex-shrink-0">✗</span>}
                      {s.status === "waiting" && <span className="text-[#444] text-xs flex-shrink-0">○</span>}
                      <span className={"text-xs font-mono " +
                        (s.status === "done" ? "text-green-400" : s.status === "error" ? "text-red-400" : s.status === "running" ? "text-[#e0e0e8]" : "text-[#444]")}>
                        {s.id}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Result */}
              {phase === "done" && (
                <div className="space-y-3">
                  <div className={"rounded-lg border p-4 text-center " +
                    (afterWns !== null && afterWns >= 0 ? "bg-green-900 bg-opacity-15 border-green-700" : "bg-yellow-900 bg-opacity-15 border-yellow-700")}>
                    <p className={"text-base font-bold mb-2 " + (afterWns !== null && afterWns >= 0 ? "text-green-400" : "text-yellow-400")}>
                      {afterWns !== null && afterWns >= 0 ? "✓ Timing Closure Achieved!" : "⚠ Timing Improved but Not Closed"}
                    </p>
                    {beforeWns !== null && afterWns !== null && (
                      <div className="flex items-center justify-center gap-4 text-sm">
                        <span className="text-red-400 font-mono">WNS {beforeWns.toFixed(2)}ns</span>
                        <span className="text-[#888896] text-lg">→</span>
                        <span className={(afterWns >= 0 ? "text-green-400" : "text-yellow-400") + " font-mono font-bold"}>
                          WNS {afterWns.toFixed(2)}ns
                        </span>
                      </div>
                    )}
                  </div>
                  {error && <p className="text-xs text-red-400">{error}</p>}
                  <div className="flex gap-2">
                    <button onClick={() => { setShowModal(false); reset(); }}
                      className="flex-1 py-2 rounded-lg text-xs font-semibold border border-[#2a2a3a] text-[#888896] hover:text-white hover:border-[#3a3a4a] transition-colors">
                      Close
                    </button>
                    {afterWns !== null && afterWns < 0 && (
                      <button onClick={() => { reset(); analyze(); }}
                        className="flex-1 py-2 rounded-lg text-xs font-semibold bg-[#8b5cf6] text-white hover:bg-[#a78bfa] transition-colors">
                        Try Another Fix
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function parseDefForHeatmap(defText) {
  const dieM = defText.match(/DIEAREA\s+\(\s*(\d+)\s+(\d+)\s*\)\s+\(\s*(\d+)\s+(\d+)\s*\)/);
  if (!dieM) return null;
  const [x0, y0, x1, y1] = [+dieM[1], +dieM[2], +dieM[3], +dieM[4]];
  const W = x1 - x0, H = y1 - y0;

  const placements = [];
  const cellTypeMap = {};
  const compRe = /\-\s+\S+\s+(sky130_fd_sc_hd__\S+)\s+\+\s+PLACED\s+\(\s*(\d+)\s+(\d+)\s*\)/g;
  let m;
  while ((m = compRe.exec(defText)) !== null) {
    const cell = m[1], x = +m[2], y = +m[3];
    if (/fill|tap|decap|lpflow_isobufsrc/.test(cell)) continue;
    placements.push({ x, y });
    const type = cell.replace('sky130_fd_sc_hd__', '').replace(/_\d+$/, '');
    cellTypeMap[type] = (cellTypeMap[type] || 0) + 1;
  }
  if (placements.length === 0) return null;

  const PW = W || 1, PH = H || 1;

  const GRID = 16;
  const raw = Array.from({ length: GRID }, () => new Array(GRID).fill(0));
  placements.forEach(({ x, y }) => {
    const gx = Math.min(Math.floor((x - x0) / PW * GRID), GRID - 1);
    const gy = Math.min(Math.floor((y - y0) / PH * GRID), GRID - 1);
    raw[gy][gx]++;
  });

  const kernel = [[1,2,1],[2,4,2],[1,2,1]];
  const ksum = 16;
  const grid = Array.from({ length: GRID }, () => new Array(GRID).fill(0));
  for (let gy = 0; gy < GRID; gy++) {
    for (let gx = 0; gx < GRID; gx++) {
      let val = 0;
      for (let ky = -1; ky <= 1; ky++) {
        for (let kx = -1; kx <= 1; kx++) {
          const ny = gy + ky, nx = gx + kx;
          if (ny >= 0 && ny < GRID && nx >= 0 && nx < GRID) {
            val += raw[ny][nx] * kernel[ky+1][kx+1];
          }
        }
      }
      grid[gy][gx] = val / ksum;
    }
  }

  const maxDensity = Math.max(...grid.flat(), 0.001);
  const rawMax = Math.max(...raw.flat(), 1);
  const topTypes = Object.entries(cellTypeMap).sort((a,b) => b[1]-a[1]).slice(0, 5);

  return { grid, GRID, maxDensity, rawMax, totalCells: placements.length, topTypes,
           dieW: (W/1000).toFixed(0), dieH: (H/1000).toFixed(0) };
}

function densityColor(value, max) {
  if (value <= 0) return "#07070f";
  const r = Math.min(value / max, 1);
  if (r < 0.25) {
    const t = r / 0.25;
    const g = Math.round(22 + t * (163 - 22));
    return `rgb(${Math.round(t*40)},${g},${Math.round(t*30)})`;
  } else if (r < 0.5) {
    const t = (r - 0.25) / 0.25;
    return `rgb(${Math.round(40+t*175)},${Math.round(163+t*(183-163))},${Math.round(30*(1-t))})`;
  } else if (r < 0.75) {
    const t = (r - 0.5) / 0.25;
    return `rgb(${Math.round(215+t*40)},${Math.round(183-t*60)},0)`;
  } else {
    const t = (r - 0.75) / 0.25;
    return `rgb(${Math.round(255)},${Math.round(123-t*123)},0)`;
  }
}

function CongestionHeatmap({ runId }) {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  const load = async () => {
    setLoading(true); setError(null); setData(null);
    try {
      let res = await fetch(PD_API + "/download/" + runId + "/routed.def");
      if (!res.ok) res = await fetch(PD_API + "/download/" + runId + "/placement.def");
      if (!res.ok) throw new Error("No placement data. Run Placement first.");
      const text  = await res.text();
      const parsed = parseDefForHeatmap(text);
      if (!parsed) throw new Error("Could not parse placement data from DEF.");
      setData(parsed);
    } catch (err) { setError(err.message); }
    setLoading(false);
  };

  const level = data
    ? data.rawMax > 5 ? "high" : data.rawMax > 2 ? "medium" : "low"
    : null;

  return (
    <div className="flex flex-col h-full bg-[#050508]">

      {/* ── Top bar: title + stats + verdict ── always visible, never scrolls */}
      <div className="shrink-0 px-4 pt-3 pb-2 space-y-2 border-b border-[#1e1e2e]">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-[#e0e0e8]">Congestion Heatmap</p>
            {data && <p className="text-xs text-[#888896]">{data.totalCells} logic cells · {data.dieW}×{data.dieH}µm die</p>}
          </div>
          <button onClick={load} disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold
              bg-[#8b5cf6] text-white hover:bg-[#a78bfa] disabled:opacity-50 transition-colors">
            {loading ? <><Loader2 className="w-3 h-3 animate-spin"/>Loading…</> : data ? "↺ Reload" : "▶ Generate"}
          </button>
        </div>

        {/* Verdict banner */}
        {data && (
          <div className={"rounded-lg px-3 py-2 text-xs " + (
            level === "high"   ? "bg-red-900 bg-opacity-20 border border-red-700 text-red-300" :
            level === "medium" ? "bg-yellow-900 bg-opacity-20 border border-yellow-700 text-yellow-300" :
                                 "bg-green-900 bg-opacity-20 border border-green-700 text-green-300")}>
            <span className="font-semibold">
              {level === "high" ? "⚠ High Congestion" : level === "medium" ? "⚡ Moderate Congestion" : "✓ Good Distribution"}
            </span>
            {" — "}
            {level === "high"
              ? `Peak ${data.maxDensity} cells/zone. Reduce Placement Density or increase Die Area.`
              : level === "medium"
              ? `Peak ${data.maxDensity} cells/zone. Monitor if routing fails.`
              : `Peak ${data.maxDensity} cells/zone. Routing should complete cleanly.`}
          </div>
        )}

        {/* Stats row */}
        {data && (
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: "Logic Cells", value: data.totalCells },
              { label: "Peak Density", value: data.rawMax + " cells/zone" },
              { label: "Die Area", value: data.dieW + "×" + data.dieH + "µm" },
            ].map((s, i) => (
              <div key={i} className="bg-[#12121a] border border-[#1e1e2e] rounded-lg py-1.5 px-2 text-center">
                <p className="text-xs text-[#888896]">{s.label}</p>
                <p className="text-xs font-mono font-bold text-[#e0e0e8]">{s.value}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Heatmap: flex-1 so it fills ALL remaining space ── */}
      {data && (
        <div className="flex-1 min-h-0 p-3">
          <div className="w-full h-full rounded-lg overflow-hidden border border-[#1e1e2e]"
            style={{
              display: "grid",
              gridTemplateColumns: `repeat(${data.GRID}, 1fr)`,
              gridTemplateRows:    `repeat(${data.GRID}, 1fr)`,
              gap: "1px",
              background: "#1e1e2e",
            }}>
            {[...data.grid].reverse().map((row, ry) =>
              row.map((val, cx) => (
                <div key={ry+"-"+cx}
                  style={{ background: densityColor(val, data.maxDensity) }}
                  title={val > 0 ? `${val} cells` : "empty"}
                />
              ))
            )}
          </div>
        </div>
      )}

      {/* Loading / empty states */}
      {loading && (
        <div className="flex-1 flex items-center justify-center gap-2 text-[#888896] text-sm">
          <Loader2 className="w-4 h-4 animate-spin text-[#8b5cf6]"/>Parsing DEF…
        </div>
      )}
      {!data && !loading && !error && (
        <div className="flex-1 flex flex-col items-center justify-center text-[#888896] gap-2">
          <p className="text-sm">Click Generate to visualize cell placement density</p>
          <p className="text-xs">Requires Placement or Routing to be complete</p>
        </div>
      )}
      {error && (
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-xs text-red-400 bg-red-900 bg-opacity-15 border border-red-800 rounded-lg p-3">{error}</p>
        </div>
      )}

      {/* ── Scrollable footer: legend + cell types ── */}
      {data && (
        <div className="shrink-0 border-t border-[#1e1e2e] px-4 py-3 space-y-3 overflow-y-auto max-h-48">
          {/* Legend */}
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {[
              { color: "#ff0000", label: "Hotspot" },
              { color: "#ff7b00", label: "Congested" },
              { color: "#d7b700", label: "Moderate" },
              { color: "#28a316", label: "Light" },
              { color: "#28631e", label: "Sparse" },
              { color: "#07070f", label: "Empty", border: true },
            ].map((l, i) => (
              <div key={i} className="flex items-center gap-1">
                <div className={"w-3 h-3 rounded-sm flex-shrink-0 " + (l.border ? "border border-[#2a2a3a]" : "")}
                  style={{ background: l.color }}/>
                <span className="text-xs text-[#888896]">{l.label}</span>
              </div>
            ))}
          </div>

          {/* Top cell types */}
          {data.topTypes.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-semibold text-[#888896] uppercase tracking-wider">Top Cell Types</p>
              {data.topTypes.map(([type, count], i) => (
                <div key={i} className="flex items-center gap-2">
                  <div className="flex-1 bg-[#0a0a12] rounded-full h-1 overflow-hidden">
                    <div className="h-full bg-[#8b5cf6] rounded-full"
                      style={{ width: (count / data.topTypes[0][1] * 100) + "%" }}/>
                  </div>
                  <span className="text-xs font-mono text-[#888896] w-16 truncate text-right">{type}</span>
                  <span className="text-xs text-[#e0e0e8] w-5 text-right font-mono">{count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DesignScorecard({ outputs, configs, runId }) {
  const [meta,    setMeta]    = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    fetch(PD_API + "/run/" + runId + "/meta")
      .then(r => r.ok ? r.json() : null)
      .then(m => { setMeta(m); setLoading(false); })
      .catch(() => setLoading(false));
  }, [runId]);

  const allLogs = Object.values(outputs).flat().join("\n");
  const timingLogs = (outputs["timing"] || []).join("\n");

  const parseNum = (text, pattern) => {
    const m = text.match(pattern);
    return m ? parseFloat(m[1]) : null;
  };

  const wns      = parseNum(timingLogs, /wns\s+(?:max\s+)?([\-\d\.]+)/i);
  const slack    = parseNum(timingLogs, /([\d\.]+)\s+slack \(MET\)/);
  const power    = parseNum(timingLogs, /Total\s+[\d\.e+\-]+\s+[\d\.e+\-]+\s+[\d\.e+\-]+\s+([\d\.e+\-]+)/);
  const util     = parseNum(allLogs,    /Utilization:\s+([\d\.]+)/);
  const cells    = parseNum(allLogs,    /(\d+)\s+138\.\d+\s+cells/) ||
                   parseNum(allLogs,    /Number of instances:\s+(\d+)/);
  const clkNs    = parseFloat(configs?.timing?.clock_period_ns || 10);
  const drcClean = (outputs["drc"] || []).join("\n").includes("DRC clean") ||
                   (outputs["drc"] || []).join("\n").includes("No violations");
  const routingDone = (outputs["routing"] || []).length > 0;
  const timingDone  = (outputs["timing"]  || []).length > 0;

  const maxFreqMhz = (slack !== null && slack > 0)
    ? Math.round(1000 / (clkNs - slack)) : null;
  const timingMet  = wns !== null && wns >= 0;
  const powerUw    = power !== null ? power * 1e6 : null;

  const scores = {
    performance: maxFreqMhz !== null
      ? { val: maxFreqMhz + " MHz", pct: Math.min(maxFreqMhz / 1000, 1),
          status: timingMet ? "pass" : "fail",
          note: timingMet ? (maxFreqMhz > 500 ? "Excellent" : "Good") : "Timing violated" }
      : null,

    area: util !== null
      ? { val: util.toFixed(1) + "% util",
          pct: Math.min(util / 80, 1),
          status: util < 5 ? "warn" : util > 80 ? "warn" : "pass",
          note: util < 5 ? "Die oversized — shrink Die Area"
              : util > 80 ? "Very high — routing risk"
              : "Good utilization" }
      : null,

    power: powerUw !== null
      ? { val: powerUw < 1000 ? powerUw.toFixed(1) + " µW" : (powerUw/1000).toFixed(2) + " mW",
          pct: Math.max(0, 1 - powerUw / 1000),
          status: powerUw < 100 ? "pass" : powerUw < 500 ? "warn" : "fail",
          note: powerUw < 100 ? "Excellent — very low power"
              : powerUw < 500 ? "Moderate"
              : "High — consider optimization" }
      : null,

    drc: timingDone || routingDone
      ? { val: drcClean ? "Clean" : "Violations",
          pct: drcClean ? 1 : 0,
          status: drcClean ? "pass" : "fail",
          note: drcClean ? "Passes Sky130HD rules" : "Fix before tapeout" }
      : null,

    timing: timingMet !== null && timingDone
      ? { val: slack !== null ? slack.toFixed(2) + " ns slack" : (wns !== null ? wns.toFixed(2) + " ns WNS" : "?"),
          pct: timingMet ? Math.min((slack || 0) / clkNs, 1) : 0,
          status: timingMet ? "pass" : "fail",
          note: timingMet ? "Setup timing met" : "Setup violated — use Fix Timing" }
      : null,
  };

  const allScores = Object.values(scores).filter(Boolean);
  const passing   = allScores.filter(s => s.status === "pass").length;
  const failing   = allScores.filter(s => s.status === "fail").length;
  const warning   = allScores.filter(s => s.status === "warn").length;
  const ready     = allScores.length >= 3 && failing === 0;
  const partial   = allScores.length >= 3 && failing === 0 && warning > 0;

  const rows = [
    { key: "performance", icon: "⚡", label: "Performance" },
    { key: "area",        icon: "📐", label: "Area" },
    { key: "power",       icon: "🔋", label: "Power" },
    { key: "drc",         icon: "🔍", label: "DRC" },
    { key: "timing",      icon: "🕐", label: "Timing" },
  ];

  const statusColor = (s) =>
    s === "pass" ? "#22c55e" : s === "warn" ? "#eab308" : "#ef4444";
  const statusIcon  = (s) =>
    s === "pass" ? "✓" : s === "warn" ? "⚠" : "✗";
  const barColor    = (s) =>
    s === "pass" ? "#22c55e" : s === "warn" ? "#eab308" : "#ef4444";

  if (loading) return (
    <div className="flex-1 flex items-center justify-center">
      <Loader2 className="w-5 h-5 animate-spin text-[#8b5cf6]" />
    </div>
  );

  if (!timingDone && !routingDone) return (
    <div className="flex-1 flex flex-col items-center justify-center text-[#888896] gap-2 p-6 text-center">
      <p className="text-sm">Run the full flow through Timing Analysis to see your Design Scorecard</p>
      <p className="text-xs">Synthesis → Floorplan → Placement → Routing → Timing</p>
    </div>
  );

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-[#050508]">

      {/* Tapeout readiness verdict */}
      <div className={"mx-4 mt-4 rounded-xl border p-4 " + (
        ready && !partial ? "bg-green-900 bg-opacity-15 border-green-700" :
        partial           ? "bg-yellow-900 bg-opacity-15 border-yellow-700" :
        allScores.length < 3 ? "bg-[#12121a] border-[#1e1e2e]" :
                            "bg-red-900 bg-opacity-15 border-red-700")}>
        <div className="flex items-center justify-between">
          <div>
            <p className={"text-base font-bold " + (
              ready && !partial ? "text-green-400" :
              partial           ? "text-yellow-400" :
              allScores.length < 3 ? "text-[#888896]" : "text-red-400")}>
              {ready && !partial ? "✓ Tapeout Ready" :
               partial           ? "⚠ Ready with Warnings" :
               allScores.length < 3 ? "Run more stages to score" :
               "✗ Not Ready for Tapeout"}
            </p>
            <p className="text-xs text-[#888896] mt-0.5">
              {passing} passing · {warning} warnings · {failing} failing
            </p>
          </div>
          {cells && <div className="text-right">
            <p className="text-xs text-[#888896]">Design</p>
            <p className="text-sm font-mono font-bold text-[#e0e0e8]">{cells} cells</p>
          </div>}
        </div>
      </div>

      {/* Score rows */}
      <div className="px-4 py-4 space-y-3">
        {rows.map(({ key, icon, label }) => {
          const s = scores[key];
          if (!s) return (
            <div key={key} className="flex items-center gap-3 opacity-30">
              <span className="text-base w-6 text-center">{icon}</span>
              <span className="text-xs text-[#888896] w-24">{label}</span>
              <div className="flex-1 h-2 bg-[#1e1e2e] rounded-full" />
              <span className="text-xs text-[#888896] w-28 text-right">not yet run</span>
              <span className="text-xs w-4" />
            </div>
          );
          return (
            <div key={key} className="space-y-1">
              <div className="flex items-center gap-3">
                <span className="text-base w-6 text-center">{icon}</span>
                <span className="text-xs font-semibold text-[#e0e0e8] w-24">{label}</span>
                {/* Progress bar */}
                <div className="flex-1 h-2.5 bg-[#1e1e2e] rounded-full overflow-hidden">
                  <div className="h-full rounded-full transition-all"
                    style={{ width: (s.pct * 100) + "%", background: barColor(s.status) }} />
                </div>
                <span className="text-xs font-mono text-[#e0e0e8] w-28 text-right">{s.val}</span>
                <span className="text-sm font-bold w-4" style={{ color: statusColor(s.status) }}>
                  {statusIcon(s.status)}
                </span>
              </div>
              <p className="text-xs text-[#888896] ml-9">{s.note}</p>
            </div>
          );
        })}
      </div>

      {/* Quick actions */}
      {failing > 0 && (
        <div className="mx-4 mb-4 bg-[#12121a] border border-[#1e1e2e] rounded-lg p-3 space-y-1.5">
          <p className="text-xs font-semibold text-[#888896] uppercase tracking-wider">Quick Actions</p>
          {scores.timing?.status === "fail" &&
            <p className="text-xs text-[#8b5cf6]">⚡ Use "Fix Timing" button in the Timing stage to auto-fix</p>}
          {scores.drc?.status === "fail" &&
            <p className="text-xs text-[#8b5cf6]">🔍 Check the DRC tab in DRC + GDS stage for violations</p>}
          {scores.area?.status === "warn" && scores.area?.note?.includes("oversized") &&
            <p className="text-xs text-[#8b5cf6]">📐 Reduce Die Area in Floorplan Config (try 0 0 40 40)</p>}
          {scores.power?.status === "fail" &&
            <p className="text-xs text-[#8b5cf6]">🔋 Power is high. If performance allows, increase Clock Period in Synthesis + Timing Config to reduce switching activity. Current: {clkNs}ns.</p>}
          {scores.power?.status === "warn" &&
            <p className="text-xs text-[#8b5cf6]">🔋 Power is moderate. If Clock Period can be relaxed above {clkNs}ns, dynamic power will decrease.</p>}
        </div>
      )}
    </div>
  );
}

function AIDialog({ title, content: text, onClose }) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50 p-6">
      <div className="bg-[#12121a] border border-[#8b5cf6] rounded-xl w-full max-w-2xl flex flex-col max-h-[80vh]">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#1e1e2e]">
          <p className="font-semibold text-sm text-white">{title}</p>
          <button onClick={onClose} className="text-[#888896] hover:text-white text-lg leading-none">✕</button>
        </div>
        <div className="overflow-y-auto px-5 py-4 text-xs text-[#c0c0d0] leading-relaxed whitespace-pre-wrap flex-1">
          {text}
        </div>
      </div>
    </div>
  );
}

function DockerPrompt({ reason, onClose }) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-80 flex items-center justify-center z-50">
      <div className="bg-[#12121a] border border-[#8b5cf6] rounded-xl p-8 max-w-md w-full mx-4">
        <h2 className="text-xl font-bold mb-3">Docker Required</h2>
        <p className="text-[#888896] text-sm mb-6">{reason}</p>
        <div className="space-y-3">
          <button onClick={() => window.electronAPI?.openExternal?.("https://www.docker.com/products/docker-desktop/")}
            className="w-full bg-[#8b5cf6] text-white py-2.5 rounded-lg font-semibold hover:bg-[#a78bfa] transition-colors">
            Download Docker Desktop
          </button>
          <button onClick={onClose}
            className="w-full border border-[#1e1e2e] text-[#888896] py-2.5 rounded-lg font-semibold hover:bg-[#1a1a25] transition-colors">
            Go Back
          </button>
        </div>
      </div>
    </div>
  );
}

export default function PDPage({ verilogFiles = {}, onBack }) {
  const [runId,        setRunId]        = useState(null);
  const [stages,       setStages]       = useState(STAGES.map(s => ({ ...s, status: "pending", timeTaken: 0 })));
  const [selected,     setSelected]     = useState("synthesis");
  const [outputs,      setOutputs]      = useState(Object.fromEntries(STAGES.map(s => [s.id, []])));
  const [configs,      setConfigs]      = useState(Object.fromEntries(Object.entries(DEFAULT_CONFIGS).map(([k, v]) => [k, { ...v }])));
  const [showConfig,   setShowConfig]   = useState(false);
  const [dlState,      setDlState]      = useState(Object.fromEntries(STAGES.map(s => [s.id, "idle"])));
  const [layoutView,   setLayoutView]   = useState(null);
  const [dockerReady,  setDockerReady]  = useState(false);
  const [dockerPrompt, setDockerPrompt] = useState(null);
  const [containerLog, setContainerLog] = useState([]);
  const [showHistory,  setShowHistory]  = useState(false);
  const [terminalView, setTerminalView] = useState("terminal"); 
  const [stageChecks,  setStageChecks]  = useState({});   // stageId → /check payload
  const [fixDialog,    setFixDialog]    = useState(null); // { stageId, check }

  const outputRef  = useRef(null);
  const stagesRef  = useRef(null);
  const isDesktop  = typeof window !== "undefined" && !!window.electronAPI;
  useEffect(() => { stagesRef.current = stages; }, [stages]);

  // Re-evaluate checks instantly when threshold config values change.
  // Debounced so rapid typing doesn't fire multiple fetches.
  useEffect(() => {
    if (!runId) return;
    const timer = setTimeout(() => {
      const thresholdStages = ["placement", "cts"];
      for (const sid of thresholdStages) {
        const stage = stages.find(s => s.id === sid);
        if (stage && stage.status === "complete") {
          refreshChecks(sid, runId, configs, false);
        }
      }
    }, 600);
    return () => clearTimeout(timer);
  }, [
    configs?.placement?.wns_margin_ns,
    configs?.placement?.max_util_pct,
    configs?.cts?.wns_margin_ns,
  ]);

  // Refresh verification checks for one stage; failures are non-fatal.
  // autoSwitch=true: switch to Checks tab if errors/warnings found (used after stage run)
  // autoSwitch=false: silent refresh, don't change the current tab (used for threshold changes)
  const refreshChecks = async (stageId, runIdArg, cfgs, autoSwitch = true) => {
    if (!CHECKED_STAGES.includes(stageId)) return null;
    try {
      const d = await fetchStageChecks(runIdArg, stageId, cfgs);
      setStageChecks(p => ({ ...p, [stageId]: d }));
      if (autoSwitch && stageId === selected) {
        const worst = worstCheckStatus(d);
        if (worst === "error" || worst === "warning") setTerminalView("checks");
      }
      return d;
    } catch (_) { return null; }
  };

  useEffect(() => {
    const session = loadSession();
    if (!session || !session.runId) return;
    const currentFP = getVerilogFingerprint(verilogFiles);
    const sessionFP = session.verilogFingerprint || "";
    if (currentFP && sessionFP && currentFP !== sessionFP) {
      clearSession();
      return;
    }
    fetch(PD_API + "/run/" + session.runId + "/meta")
      .then(r => r.ok ? r.json() : null)
      .then(meta => {
        if (!meta) {
          if (session.configs) setConfigs(session.configs);
          clearSession();
          return;
        }
        setRunId(session.runId);
        setStages(p => p.map(s => {
          const containerStage = meta.stages?.[s.id];
          const saved = session.stages?.find(ss => ss.id === s.id);
          if (!containerStage || containerStage.status !== "done") {
            return { ...s, status: "pending", timeTaken: 0 };
          }
          return saved ? { ...s, status: saved.status, timeTaken: saved.timeTaken } : s;
        }));
        if (session.configs) setConfigs(session.configs);
        if (session.outputs) setOutputs(session.outputs);
        // Restore verification checks for every completed checkable stage
        const cfgsForChecks = session.configs || configs;
        for (const sid of CHECKED_STAGES) {
          if (meta.stages?.[sid]) refreshChecks(sid, session.runId, cfgsForChecks);
        }
      })
      .catch(() => {
        if (session.configs) setConfigs(session.configs);
      });
  }, []);

  useEffect(() => {
    if (!isDesktop) { setDockerReady(true); return; }
    (async () => {
      const { installed, running } = await window.electronAPI.pdCheckDocker();
      if (!installed) { setDockerPrompt("Docker Desktop is not installed. It is required to run the Physical Design tools."); return; }
      if (!running)   { setDockerPrompt("Docker Desktop is not running. Please start it and try again."); return; }
      window.electronAPI.onPdPullProgress(l => setContainerLog(p => [...p, l]));
      const result = await window.electronAPI.pdStart();
      window.electronAPI.offPdPullProgress();
      if (!result.ok) { setContainerLog(p => [...p, "[ERROR] " + result.error]); return; }
      setDockerReady(true);
    })();
    return () => { if (isDesktop) window.electronAPI.pdStop?.(); };
  }, []);

  useEffect(() => {
    if (!dockerReady) return;
    fetch(PD_API + "/new_run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ design: "top" }),
    }).then(r => r.json()).then(d => { if (d.run_id) setRunId(d.run_id); }).catch(() => {});
  }, [dockerReady]);

  useEffect(() => {
    if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [outputs, selected]);

  useEffect(() => {
    if (runId) saveSession(runId, stages, configs, outputs);
  }, [runId, stages, configs, outputs]);

  const currentStage = stages.find(s => s.id === selected);
  useEffect(() => { setTerminalView("terminal"); }, [selected]);
  const stageMeta    = STAGES.find(s => s.id === selected);

  const appendLine = (id, line) => setOutputs(p => ({ ...p, [id]: [...(p[id] || []), line] }));
  const setStatus  = (id, status, t) => setStages(p => p.map(s => s.id === id ? { ...s, status, ...(t != null ? { timeTaken: t } : {}) } : s));

  function buildBody() {
    const cfg  = configs[selected];
    const base = { top_module: "top", run_id: runId, ...cfg };
    if (selected === "synthesis") return { ...base, verilog_files: verilogFiles };
    return base;
  }

  const handleRun = async () => {
    if (!dockerReady || !runId || currentStage.status === "running") return;

    if (selected === "synthesis" && Object.keys(verilogFiles).length === 0) {
      appendLine("synthesis", "[ERROR] No Verilog files found. Generate RTL from the canvas first.");
      return;
    }

    setStatus(selected, "running");
    setOutputs(p => ({ ...p, [selected]: [] }));
    setDlState(p => ({ ...p, [selected]: "idle" }));
    const t0 = Date.now();

    const endpointMap = { synthesis: "synthesize", spef: "spef" };
    const endpoint = endpointMap[selected] || selected;

    try {
      const res = await fetch(PD_API + "/" + endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildBody()),
      });

      if (!res.ok) {
        const txt = await res.text();
        appendLine(selected, "[ERROR] HTTP " + res.status + ": " + txt);
        setStatus(selected, "error");
        return;
      }

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let full = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        full += chunk;
        chunk.split("\n").forEach(l => { if (l.trim()) appendLine(selected, l); });
      }

      const elapsed  = parseFloat(((Date.now() - t0) / 1000).toFixed(2));
      const hadError = full.includes("[ERROR") || full.includes("exit code: 1") || full.includes("Error:");
      setStatus(selected, hadError ? "error" : "complete", elapsed);
    if (selected === "drc" && !hadError) setTerminalView("drc");
      if (!hadError) appendLine(selected, "[DONE] " + currentStage.name + " completed in " + elapsed + "s");

      // Verification: run checks after the stage completes (fetch even on
      // error — partial metrics still help). Auto-open the Checks tab when
      // something needs attention.
      const checkData = await refreshChecks(selected, runId, configs, true);
      if (checkData) {
        const worst = worstCheckStatus(checkData);
        if (worst === "error" || worst === "warning") setTerminalView("checks");
      }

    } catch (err) {
      appendLine(selected, "[ERROR] " + err.message);
      setStatus(selected, "error");
    }
  };

  const runStageForFix = async (stageId, overrideConfigs) => {
    const cfgs = overrideConfigs || configs;
    const endpointMap = { synthesis: "synthesize", spef: "spef" };
    const endpoint = endpointMap[stageId] || stageId;
    const cfg = cfgs[stageId] || {};
    const base = { top_module: "top", run_id: runId, ...cfg };
    const body = stageId === "synthesis" ? { ...base, verilog_files: verilogFiles } : base;

    setSelected(stageId);
    setStatus(stageId, "running");
    setOutputs(p => ({ ...p, [stageId]: [] }));

    const res = await fetch(PD_API + "/" + endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let full = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      full += chunk;
      chunk.split("\n").forEach(l => { if (l.trim()) appendLine(stageId, l); });
    }
    const hadError = full.includes("[ERROR") || full.includes("exit code: 1") || full.includes("Error:");
    setStatus(stageId, hadError ? "error" : "complete");
    await refreshChecks(stageId, runId, cfgs);
    if (hadError) throw new Error(stageId + " failed");
  };

  // ── Verification fix application ────────────────────────────────────────────

  const buildConfigsWithFix = (fix, value) => {
    const next = { ...configs, [fix.stage]: { ...configs[fix.stage], [fix.field]: value } };
    // A clock period mismatch between stages is a classic footgun — keep the
    // period consistent everywhere it appears when a fix changes it.
    if (fix.field === "clock_period_ns") {
      for (const sid of ["synthesis", "placement", "cts", "timing"]) {
        if (next[sid] && next[sid].clock_period_ns != null) {
          next[sid] = { ...next[sid], clock_period_ns: value };
        }
      }
    }
    return next;
  };

  // "Apply": write config, navigate to the stage, open its Config panel.
  const applyFix = (fix, value) => {
    setConfigs(buildConfigsWithFix(fix, value));
    setSelected(fix.stage);
    setShowConfig(true);
  };

  // Re-run the flow from the fixed stage through the checked stage, skipping
  // optional stages (pdn/cts/spef…) that were never run in this flow.
  const rerunChain = async (fromStage, toStage, cfgs) => {
    const order = STAGES.map(s => s.id);
    const from = order.indexOf(fromStage);
    let to = order.indexOf(toStage);
    if (from < 0) return;
    if (to < from) to = from;
    const required = new Set(["synthesis", "floorplan", "placement", "routing"]);
    for (let i = from; i <= to; i++) {
      const id = order[i];
      if (!required.has(id)) {
        const wasRun = (stagesRef.current || []).find(s => s.id === id)?.status === "complete";
        if (!wasRun) continue; // optional stage the user never ran — keep skipping it
      }
      try {
        await runStageForFix(id, cfgs);
      } catch (_) {
        return; // stop the chain on failure — the failing stage is now selected
      }
    }
  };

  // "Apply & Re-run": apply, then automatically re-run every stale stage.
  const applyFixAndRerun = async (fix, value, checkedStage) => {
    const next = buildConfigsWithFix(fix, value);
    setConfigs(next);
    await rerunChain(fix.stage, checkedStage, next);
  };

  const handleDownload = async (stageId) => {
    if (!runId) return;
    const meta = STAGES.find(s => s.id === stageId);
    setDlState(p => ({ ...p, [stageId]: "downloading" }));
    try {
      const res = await fetch(PD_API + "/download/" + runId + "/" + meta.outputFile);
      if (!res.ok) { setDlState(p => ({ ...p, [stageId]: "error" })); return; }
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = meta.outputFile; a.click();
      URL.revokeObjectURL(url);
      setDlState(p => ({ ...p, [stageId]: "done" }));
    } catch {
      setDlState(p => ({ ...p, [stageId]: "error" }));
    }
  };

  const canRun = dockerReady && !!runId && currentStage.status !== "running";

  const handleRestore = async (restoredRunId) => {
    setShowHistory(false);
    try {
      const res  = await fetch(PD_API + "/run/" + restoredRunId + "/meta");
      if (!res.ok) throw new Error("Run not found in container");
      const meta = await res.json();
      setRunId(restoredRunId);
      setStages(p => p.map(s => {
        const stageData = meta.stages?.[s.id];
        if (!stageData || stageData.status !== "done") return { ...s, status: "pending", timeTaken: 0 };
        return { ...s, status: "complete", timeTaken: stageData.time_s || 0 };
      }));
      setOutputs({});  
      setStageChecks({});
      for (const sid of CHECKED_STAGES) {
        if (meta.stages?.[sid]) refreshChecks(sid, restoredRunId, configs);
      }
    } catch {
      setRunId(restoredRunId);
      setStages(p => p.map(s => ({ ...s, status: "pending", timeTaken: 0 })));
      setOutputs({});
      setStageChecks({});
    }
  };

  if (!dockerReady && !dockerPrompt) return (
    <div className="flex h-screen bg-[#0a0a0f] text-[#e0e0e8] items-center justify-center flex-col gap-6">
      <Loader2 className="w-10 h-10 text-[#8b5cf6] animate-spin" />
      <div className="text-center">
        <p className="text-lg font-semibold mb-1">Starting PD Tools</p>
        <p className="text-sm text-[#888896] mb-5">Setting up the Docker container…</p>
        <div className="bg-[#12121a] border border-[#1e1e2e] rounded-lg p-4 w-[480px] max-h-48 overflow-y-auto text-left font-mono text-xs text-[#22c55e] space-y-0.5">
          {containerLog.length === 0
            ? <div className="text-[#888896]">Initializing…</div>
            : containerLog.map((l, i) => <div key={i}>{l}</div>)}
        </div>
      </div>
      <button onClick={onBack} className="text-sm text-[#888896] hover:text-[#e0e0e8]">Cancel</button>
    </div>
  );

  return (
    <div className="flex h-screen bg-[#0a0a0f] text-[#e0e0e8]">
      {dockerPrompt && <DockerPrompt reason={dockerPrompt} onClose={onBack} />}
      {showHistory && <RunHistory onRestore={handleRestore} onClose={() => setShowHistory(false)} />}
      {layoutView && (
        <LayoutViewer
          runId={runId}
          view={layoutView.view}
          label={layoutView.label}
          onClose={() => setLayoutView(null)}
        />
      )}
      {fixDialog && stageChecks[fixDialog.stageId] && (
        <ExplainFixDialog
          stageId={fixDialog.stageId}
          checkData={stageChecks[fixDialog.stageId]}
          focusCheck={fixDialog.check}
          onApply={applyFix}
          onApplyAndRerun={applyFixAndRerun}
          onClose={() => setFixDialog(null)}
        />
      )}

      {/* LEFT SIDEBAR */}
      <div className="w-60 bg-[#0a0a0f] border-r border-[#1e1e2e] flex flex-col shrink-0">

        {/* Header */}
        <div className="p-4 border-b border-[#1e1e2e]">
          <button onClick={onBack} className="flex items-center gap-2 text-sm text-[#8b5cf6] hover:text-[#a78bfa] mb-3 transition-colors">
            <ChevronLeft className="w-4 h-4" /> Back to Canvas
          </button>
          <button onClick={() => setShowHistory(true)} className="flex items-center gap-1.5 text-xs text-[#888896] hover:text-[#e0e0e8] mb-3 transition-colors">
            🕐 Run History
          </button>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-gradient-to-br from-[#8b5cf6] to-[#6d28d9] rounded flex items-center justify-center shrink-0">
              <span className="text-xs font-bold text-white">RTL</span>
            </div>
            <div>
              <div className="font-semibold text-sm">RTL Copilot</div>
              <div className="text-xs text-[#888896] bg-[#1e1e2e] px-2 py-0.5 rounded inline-block mt-0.5">Physical Design</div>
            </div>
          </div>
        </div>

        {/* Run status + download all */}
        <div className="px-4 py-2.5 border-b border-[#1e1e2e] flex items-center justify-between">
          <span className="text-xs font-semibold text-[#888896] uppercase tracking-wider">RTL → GDS Flow</span>
          <div className="flex items-center gap-2">
            <div className={`flex items-center gap-1.5 text-xs ${dockerReady ? "text-green-400" : "text-yellow-400"}`}>
              <div className={`w-1.5 h-1.5 rounded-full ${dockerReady ? "bg-green-400" : "bg-yellow-400"}`} />
              {dockerReady ? (runId ? runId.slice(0,8) : "Ready") : "Starting…"}
            </div>
            {runId && (
              <button onClick={() => window.open(PD_API + "/download_zip/" + runId)}
                title="Download all outputs as zip"
                className="text-[#888896] hover:text-[#8b5cf6] transition-colors">
                <Download className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>

        {/* Stage list */}
        <div className="flex-1 overflow-y-auto py-1">
          {stages.map(stage => (
            <div key={stage.id}>
              <button onClick={() => setSelected(stage.id)}
                className={"w-full px-4 py-2.5 text-left border-l-2 transition-colors " +
                  (selected === stage.id ? "border-l-[#8b5cf6] bg-[#1a1a25]" : "border-l-transparent hover:bg-[#12121a]")}>
                <div className="flex items-center gap-2.5">
                  <StatusIcon status={stage.status} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{stage.name}</div>
                    {stage.timeTaken > 0 && <div className="text-xs text-[#888896]">{stage.timeTaken.toFixed(2)}s</div>}
                  </div>
                  {stageChecks[stage.id] && (() => {
                    const worst = worstCheckStatus(stageChecks[stage.id]);
                    return worst
                      ? <div title={"Checks: " + worst}
                          className={"w-2 h-2 rounded-full shrink-0 " + (CHECK_DOT_CLS[worst] || "bg-gray-500")} />
                      : null;
                  })()}
                </div>
              </button>

              {/* Inline download per stage */}
              {stage.status === "complete" && (
                <div className="px-3 pb-2">
                  <button onClick={() => handleDownload(stage.id)}
                    disabled={dlState[stage.id] === "downloading"}
                    className="w-full flex items-center justify-center gap-1.5 py-1 rounded text-xs font-semibold
                      bg-[#1a1a25] border border-[#8b5cf6] text-[#8b5cf6]
                      hover:bg-[#8b5cf6] hover:text-white transition-colors
                      disabled:opacity-50 disabled:cursor-not-allowed">
                    {dlState[stage.id] === "downloading"
                      ? <><Loader2 className="w-3 h-3 animate-spin" /> Downloading…</>
                      : dlState[stage.id] === "done"
                      ? <><CheckCircle2 className="w-3 h-3" /> Downloaded</>
                      : <><Download className="w-3 h-3" /> {STAGES.find(s => s.id === stage.id)?.outputLabel}</>}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* MAIN CONTENT */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Stage header bar */}
        <div className="h-14 border-b border-[#1e1e2e] bg-[#12121a] px-5 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-bold">{currentStage.name}</h1>
            <StatusBadge status={currentStage.status} />
            <span className="text-xs text-[#888896]">{stageMeta?.tool}</span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setShowConfig(p => !p)}
              className={"flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold transition-colors " +
                (showConfig ? "bg-[#8b5cf6] text-white" : "border border-[#2a2a3a] text-[#888896] hover:text-white hover:border-[#8b5cf6]")}>
              <SettingsIcon className="w-3.5 h-3.5" /> Config
            </button>

            {currentStage.status === "complete" && (
              <button onClick={() => handleDownload(selected)}
                disabled={dlState[selected] === "downloading"}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold
                  border border-[#8b5cf6] text-[#8b5cf6] hover:bg-[#8b5cf6] hover:text-white
                  transition-colors disabled:opacity-50">
                <Download className="w-3.5 h-3.5" />
                {dlState[selected] === "done" ? "Downloaded ✓" : stageMeta?.outputLabel}
              </button>
            )}

            <button onClick={handleRun} disabled={!canRun}
              className={"flex items-center gap-1.5 px-4 py-1.5 rounded font-semibold text-sm transition-colors " +
                (canRun ? "bg-[#8b5cf6] text-white hover:bg-[#a78bfa]" : "bg-[#2a2a3a] text-[#888896] cursor-not-allowed")}>
              {currentStage.status === "running"
                ? <><Loader2 className="w-4 h-4 animate-spin" /> Running…</>
                : <><Play className="w-4 h-4" /> Run</>}
            </button>
          </div>
        </div>

        {/* Config panel — collapsible */}
        {showConfig && (
          <div className="border-b border-[#1e1e2e] bg-[#0d0d16] px-5 py-4 shrink-0">
            <ConfigPanel
              stageId={selected}
              config={configs[selected]}
              onChange={cfg => setConfigs(p => ({ ...p, [selected]: cfg }))}
            />
          </div>
        )}

        {/* Terminal + sidebar */}
        <div className="flex-1 overflow-hidden flex gap-4 p-4">

          {/* Terminal */}
          <div className="flex-1 bg-[#050508] border border-[#1e1e2e] rounded-lg flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 border-b border-[#1e1e2e] shrink-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-semibold text-[#888896]">Terminal Output</span>
                {((outputs[selected] || []).length > 0 || selected === "placement" || selected === "routing" || stageChecks[selected]) && (
                  <div className="flex rounded overflow-hidden border border-[#2a2a3a]">
                    <button onClick={() => setTerminalView("terminal")}
                      className={"px-2 py-0.5 text-xs transition-colors " +
                        (terminalView === "terminal" ? "bg-[#8b5cf6] text-white" : "text-[#888896] hover:text-white")}>
                      Logs
                    </button>
                    {stageChecks[selected] && (
                      <button onClick={() => setTerminalView("checks")}
                        className={"px-2 py-0.5 text-xs transition-colors " +
                          (terminalView === "checks" ? "bg-[#8b5cf6] text-white" : "text-[#888896] hover:text-white")}>
                        ✓ Checks
                      </button>
                    )}
                    <button onClick={() => setTerminalView("path")}
                      className={"px-2 py-0.5 text-xs transition-colors " +
                        (terminalView === "path" ? "bg-[#8b5cf6] text-white" : "text-[#888896] hover:text-white")}>
                      ⚡ Path
                    </button>
                    <button onClick={() => setTerminalView("corners")}
                      className={"px-2 py-0.5 text-xs transition-colors " +
                        (terminalView === "corners" ? "bg-[#8b5cf6] text-white" : "text-[#888896] hover:text-white")}>
                      🌡 Corners
                    </button>
                    {selected === "drc" && (
                      <button onClick={() => setTerminalView("drc")}
                        className={"px-2 py-0.5 text-xs transition-colors " +
                          (terminalView === "drc" ? "bg-[#8b5cf6] text-white" : "text-[#888896] hover:text-white")}>
                        🔍 DRC
                      </button>
                    )}
                    {(selected === "placement" || selected === "routing" || selected === "drc") && (
                      <button onClick={() => setTerminalView("heatmap")}
                        className={"px-2 py-0.5 text-xs transition-colors " +
                          (terminalView === "heatmap" ? "bg-[#8b5cf6] text-white" : "text-[#888896] hover:text-white")}>
                        🗺 Map
                      </button>
                    )}
                    <button onClick={() => setTerminalView("chat")}
                      className={"px-2 py-0.5 text-xs transition-colors " +
                        (terminalView === "chat" ? "bg-[#8b5cf6] text-white" : "text-[#888896] hover:text-white")}>
                      💬 Ask AI
                    </button>
                    {(selected === "timing" || selected === "drc") && (
                      <button onClick={() => setTerminalView("score")}
                        className={"px-2 py-0.5 text-xs transition-colors " +
                          (terminalView === "score" ? "bg-[#8b5cf6] text-white" : "text-[#888896] hover:text-white")}>
                        📊 Score
                      </button>
                    )}
                  </div>
                )}
              </div>
              <button onClick={() => navigator.clipboard.writeText((outputs[selected] || []).join("\n"))}
                className="flex items-center gap-1 text-xs text-[#888896] hover:text-[#e0e0e8] transition-colors">
                <Copy className="w-3 h-3" /> Copy
              </button>
            </div>
            {terminalView === "checks" && stageChecks[selected]
              ? <ChecksPanel data={stageChecks[selected]}
                  onOpenFix={(check) => setFixDialog({ stageId: selected, check })} />
              : terminalView === "score" && (selected === "timing" || selected === "drc")
              ? <DesignScorecard outputs={outputs} configs={configs} runId={runId} />
              : terminalView === "chat"
              ? <PDChatAssistant runId={runId} configs={configs} verilogFiles={verilogFiles} outputs={outputs} stages={stages} />
              : terminalView === "heatmap" && (selected === "placement" || selected === "routing" || selected === "drc")
              ? <CongestionHeatmap runId={runId} />
            : terminalView === "drc" && selected === "drc"
              ? <DRCPanel logs={outputs["drc"] || []} runId={runId} configs={configs} verilogFiles={verilogFiles} outputs={outputs} />
              : terminalView === "corners" && selected === "timing"
              ? <MultiCornerPanel runId={runId} configs={configs} />
              : terminalView === "path" && selected === "timing"
              ? <TimingPathViewer logs={outputs["timing"] || []} />
              : <div ref={outputRef} className="flex-1 overflow-y-auto px-4 py-3 font-mono text-xs space-y-0.5">
                  {(outputs[selected] || []).length === 0
                    ? <div className="text-[#333348]">
                        {dockerReady ? "Click Run to start " + currentStage.name + "…" : "Waiting for container…"}
                      </div>
                    : (outputs[selected] || []).map((line, i) => (
                      <div key={i} className={
                        (line.includes("[ERROR") || line.includes("Error:")) ? "text-red-400"    :
                        line.includes("[DONE]") || line.includes("[SUCCESS]") ? "text-green-400"  :
                        line.includes("[WARNING]")                            ? "text-yellow-400" :
                        line.includes("[INFO]")                               ? "text-[#22c55e]"  :
                        "text-[#888896]"
                      }>{line}</div>
                    ))
                  }
                </div>
            }
          </div>

          {/* Info panel */}
          <div className="w-64 shrink-0 flex flex-col gap-3 overflow-y-auto">
            <div className="bg-[#12121a] border border-[#1e1e2e] rounded-lg p-4 space-y-3">
              <p className="text-xs font-semibold text-[#888896] uppercase tracking-wider">Stage Info</p>
              <InfoRow label="Tool"    value={stageMeta?.tool} mono />
              <InfoRow label="Output"  value={stageMeta?.outputFile} mono small />
              <InfoRow label="Library" value={configs[selected]?.cell_lib?.replace("sky130_fd_sc_", "sc_") || "—"} mono />
              <InfoRow label="Corner"  value={(configs[selected]?.corner || "—").toUpperCase()} mono />
              {currentStage.timeTaken > 0 &&
                <InfoRow label="Last Run" value={currentStage.timeTaken.toFixed(2) + "s"} mono purple />}
            </div>

            {currentStage.status === "error" && (
              <div className="bg-red-900 bg-opacity-20 border border-red-800 rounded-lg p-3">
                <p className="text-xs font-semibold text-red-400 mb-1">Stage Failed</p>
                <p className="text-xs text-red-300 mb-2">Check the terminal output for details.</p>
                <AIExplainer logs={outputs[selected] || []} stage={currentStage.name} runId={runId} config={configs[selected]} verilogFiles={verilogFiles} outputs={outputs} />
              </div>
            )}

            {currentStage.status === "complete" && (() => {
              const previewViews = {
                placement: { view: "placement", label: "Placement Layout" },
                routing:   { view: "routing",   label: "Routed Layout"    },
                drc:       { view: "gds",        label: "Final GDS Layout" },
              };
              const pv = previewViews[selected];
              return (
                <div className="bg-green-900 bg-opacity-20 border border-green-800 rounded-lg p-3">
                  <p className="text-xs font-semibold text-green-400 mb-1">Complete ✓</p>
                  <p className="text-xs text-green-300 mb-2">Output saved. Proceed to next stage or download.</p>
                  {pv && (
                    <button
                      onClick={() => setLayoutView(pv)}
                      className="w-full mb-2 py-1.5 rounded text-xs font-semibold
                        bg-gradient-to-r from-[#8b5cf6] to-[#6d28d9] text-white
                        hover:from-[#a78bfa] hover:to-[#8b5cf6] transition-all flex items-center justify-center gap-1.5">
                      🔬 View Layout
                    </button>
                  )}
                  <QoRAdvisor logs={outputs[selected] || []} stage={currentStage.name} runId={runId} config={configs[selected]} verilogFiles={verilogFiles} outputs={outputs} />
                {selected === "timing" && (
                  <TimingClosureAdvisor
                    logs={outputs["timing"] || []}
                    runId={runId}
                    configs={configs}
                    setConfigs={setConfigs}
                    verilogFiles={verilogFiles}
                    outputs={outputs}
                    stages={stages}
                    setSelected={setSelected}
                    onRerunStages={runStageForFix}
                  />
                )}
                </div>
              );
            })()}
          </div>
        </div>
      </div>
    </div>
  );
}

function LayoutViewer({ runId, view, label, onClose }) {
  const [status,   setStatus]   = useState("loading");
  const [imgUrl,   setImgUrl]   = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [scale,    setScale]    = useState(1);
  const [offset,   setOffset]   = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [dragStart,setDragStart]= useState({ x: 0, y: 0 });

  useEffect(() => {
    setStatus("loading");
    setErrorMsg("");
    setScale(1);
    setOffset({ x: 0, y: 0 });
    const url = PD_API + "/preview/" + runId + "/" + view;
    fetch(url)
      .then(async r => {
        if (!r.ok) {
          let detail = "HTTP " + r.status;
          try {
            const json = await r.json();
            detail = json.detail || detail;
          } catch (_) {}
          throw new Error(detail);
        }
        return r.blob();
      })
      .then(blob => {
        setImgUrl(URL.createObjectURL(blob));
        setStatus("ok");
      })
      .catch(err => {
        console.error("Preview error:", err);
        setErrorMsg(err.message);
        setStatus("error");
      });
    return () => { if (imgUrl) URL.revokeObjectURL(imgUrl); };
  }, [runId, view]);

  const onWheel = (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 0.87;
    setScale(s => Math.min(Math.max(s * factor, 0.1), 20));
  };

  const onMouseDown = (e) => {
    setDragging(true);
    setDragStart({ x: e.clientX - offset.x, y: e.clientY - offset.y });
  };
  const onMouseMove = (e) => {
    if (!dragging) return;
    setOffset({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  };
  const onMouseUp = () => setDragging(false);

  return (
    <div className="fixed inset-0 z-50 bg-black bg-opacity-90 flex flex-col">
      <div className="flex items-center justify-between px-5 py-3 border-b border-[#1e1e2e] shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-white">{label}</span>
          <span className="text-xs text-[#888896]">{runId.slice(0, 8)}</span>
          <span className="text-xs text-[#444460]">
            scroll to zoom · drag to pan
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => { setScale(1); setOffset({ x: 0, y: 0 }); }}
            className="px-2.5 py-1 rounded text-xs text-[#888896] hover:text-white border border-[#2a2a3a] hover:border-[#444460] transition-colors">
            Reset
          </button>
          {imgUrl && (
            <a href={imgUrl} download={view + "_preview.png"}
              className="px-2.5 py-1 rounded text-xs bg-[#1e1e2e] text-[#888896] hover:text-white border border-[#2a2a3a] hover:border-[#444460] transition-colors">
              Save PNG
            </a>
          )}
          <button onClick={onClose}
            className="px-2.5 py-1 rounded text-xs bg-[#8b5cf6] text-white hover:bg-[#a78bfa] transition-colors">
            Close
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-hidden flex items-center justify-center relative"
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
        style={{ cursor: dragging ? "grabbing" : "grab" }}>

        {status === "loading" && (
          <div className="flex flex-col items-center gap-3 text-[#888896]">
            <Loader2 className="w-8 h-8 animate-spin text-[#8b5cf6]" />
            <p className="text-sm">Generating layout preview…</p>
            <p className="text-xs text-[#444460]">This may take 15–30 seconds</p>
          </div>
        )}

        {status === "error" && (
          <div className="flex flex-col items-center gap-2 text-[#888896] max-w-lg px-6 text-center">
            <AlertCircle className="w-8 h-8 text-red-400 shrink-0" />
            <p className="text-sm text-red-300">Preview generation failed</p>
            {errorMsg && (
              <p className="text-xs font-mono bg-[#12121a] border border-[#2a2a3a] rounded px-3 py-2 text-left w-full text-[#c0c0d0] whitespace-pre-wrap break-all">
                {errorMsg}
              </p>
            )}
          </div>
        )}

        {status === "ok" && imgUrl && (
          <img
            src={imgUrl}
            alt={label + " layout preview"}
            draggable={false}
            style={{
              transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
              transformOrigin: "center center",
              transition: dragging ? "none" : "transform 0.05s ease",
              maxWidth: "none",
              imageRendering: "pixelated",
            }}
          />
        )}
      </div>
    </div>
  );
}

function InfoRow({ label, value, mono, small, purple }) {
  return (
    <div>
      <p className="text-xs text-[#888896]">{label}</p>
      <p className={`${small ? "text-xs" : "text-sm"} ${mono ? "font-mono" : ""} ${purple ? "text-[#8b5cf6] font-semibold" : "text-[#e0e0e8]"} truncate`}>
        {value || "—"}
      </p>
    </div>
  );
}