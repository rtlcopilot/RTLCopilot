import React, { useState, useEffect, useRef, useCallback } from "react";
import ReactFlow, { Background, useNodesState, useEdgesState, addEdge } from "reactflow";
import "reactflow/dist/style.css";
import PDPage from "./PDPage";

import { T, GLOBAL_CSS } from "./constants";
import { GRID_X, GRID_Y, MAX_COLS } from "./constants";
import { API_BASE, supabase } from "./config";
import { nextFreeIndex, detectLoops, stripNodeForSave } from "./utils";
import { COMPONENTS, COMPONENT_CATEGORIES } from "./componentCategories";
import { nodeTypes, edgeTypes } from "./nodeTypes";

import ComponentPalette from "./components/ComponentPalette";
import Toolbar from "./components/Toolbar";
import BottomPanel from "./components/BottomPanel";
import WaveformViewer from "./components/WaveformViewer";
import AiSidebar from "./components/AiSidebar";
import { AuthModal, OnboardingModal, FeedbackModal, ByokModal } from "./components/Modals";
import CustomBlockModal from "./components/CustomBlockModal";


export default function App() {
  React.useEffect(() => {
    const id = "rtl-copilot-styles";
    if (document.getElementById(id)) return;
    const el = document.createElement("style");
    el.id = id;
    el.textContent = GLOBAL_CSS;
    document.head.appendChild(el);
  }, []);

  const [nodes, setNodes, _onNodesChange] = useNodesState([]);
  const [edges, setEdges, _onEdgesChange] = useEdgesState([]);

  const onNodesChange = React.useCallback((changes) => {
    _onNodesChange(changes);
    if (changes.some((c) => c.type !== "select" && c.type !== "dimensions")) setIsDirty(true);
  }, [_onNodesChange]);

  const onEdgesChange = React.useCallback((changes) => {
    _onEdgesChange(changes);
    if (changes.some((c) => c.type !== "select")) setIsDirty(true);
  }, [_onEdgesChange]);

  const [selected, setSelected] = useState(COMPONENTS[0]);

  const [verilogFiles,   setVerilogFiles]   = useState({});
  const [canonicalIR,    setCanonicalIR]    = useState(null);  
  const [activeRtlFile,  setActiveRtlFile]  = useState("top.v");
  const [testbenchCode,  setTestbenchCode]  = useState(null);
  const [tbSteps,        setTbSteps]        = useState([{ time: 0, values: {} }]);
  const [tbConfig,       setTbConfig]       = useState({
    resetType: "sync", resetActive: "high",
    useCornerCases: false, useRandom: false,
    numRandomSteps: 8, randomSeed: "",
    simDurationNs: 2000,
  });
  const [tbConfigDirty, setTbConfigDirty] = useState(false);

  const updateTbConfig = (updater) => {
    setTbConfig(updater);
    if (tbReady) setTbConfigDirty(true);
  };

  const [verifyHistory,      setVerifyHistory]      = useState([]);
  const [verifyLoading,      setVerifyLoading]      = useState(false);
  const [verifyExpanded,     setVerifyExpanded]     = useState({});
  const [verifyRandomWarning, setVerifyRandomWarning] = useState(false);
  const [verifyAutoLoading,  setVerifyAutoLoading]  = useState(false);
  const [verifyIntent,       setVerifyIntent]       = useState("");
 
  const [params, setParams] = useState([{ name: "DATA_WIDTH", value: "8" }]);

  const [promptValue, setPromptValue] = useState("");
  const [chatHistory, setChatHistory] = useState([{ role: "assistant", text: "Hello! I can help you design circuits. What should we build?" }]);
  const [isAiOpen,    setIsAiOpen]    = useState(false);
  const [aiLoading,   setAiLoading]   = useState(false);
  const [aiMode,      setAiMode]      = useState("build");

  const [showBottomPanel,    setShowBottomPanel]    = useState(false);
  const [activeTab,          setActiveTab]          = useState("rtl");
  const [bottomPanelHeight,  setBottomPanelHeight]  = useState(340);
  const [drcLogs,            setDrcLogs]            = useState([]);

  const [simulationResult, setSimulationResult] = useState(null);
  const [showWaveform,     setShowWaveform]     = useState(false);
  const [simulating,       setSimulating]       = useState(false);
  const [waveformHeight,   setWaveformHeight]   = useState(420);

  const [toast, setToast] = useState(null);
  const showToast = (msg, type = "info") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const [isFeedbackOpen,      setIsFeedbackOpen]      = useState(false);
  const [feedbackRating,      setFeedbackRating]      = useState(0);
  const [feedbackText,        setFeedbackText]        = useState("");
  const [feedbackTrigger,     setFeedbackTrigger]     = useState("");
  const [feedbackSubmitting,  setFeedbackSubmitting]  = useState(false);
  const [feedbackWhatBuilding, setFeedbackWhatBuilding] = useState("");
  const [feedbackAiAccuracy,  setFeedbackAiAccuracy]  = useState("");
  const [feedbackBlockers,    setFeedbackBlockers]    = useState([]);
  const [feedbackWouldPay,    setFeedbackWouldPay]    = useState("");

  const feedbackShownRef = useRef(new Set(
    JSON.parse(localStorage.getItem("rtl_feedback_shown") || "[]")
  ));

  const triggerFeedback = (trigger) => {
    if (feedbackShownRef.current.has(trigger)) return;
    feedbackShownRef.current.add(trigger);
    localStorage.setItem("rtl_feedback_shown",
      JSON.stringify([...feedbackShownRef.current]));
    setFeedbackTrigger(trigger);
    setFeedbackRating(0);
    setFeedbackText("");
    setTimeout(() => setIsFeedbackOpen(true), 1800);
  };

  const [rtlReady,  setRtlReady]  = useState(false);
  const [tbReady,   setTbReady]   = useState(false);
  const [isDirty,   setIsDirty]   = useState(false);
  const [isSaving,  setIsSaving]  = useState(false);

  const [user,             setUser]             = useState(null);
  const [isAuthOpen,       setIsAuthOpen]       = useState(false);
  const [isDropdownOpen,   setIsDropdownOpen]   = useState(false);
  const [projects,         setProjects]         = useState([]);
  const [projectName,      setProjectName]      = useState("Untitled Design");
  const [currentProjectId, setCurrentProjectId] = useState(null);
  const [projectsLoading,  setProjectsLoading]  = useState(false);
  const [isByokOpen,       setIsByokOpen]       = useState(false);
  const [byokKey,          setByokKey]          = useState(() => localStorage.getItem("rtl_byok_key") || "");
  const [byokProvider,     setByokProvider]     = useState(() => localStorage.getItem("rtl_byok_provider") || "openai");
  const [byokModel,        setByokModel]        = useState(() => localStorage.getItem("rtl_byok_model") || "");

  const [isCustomBlockOpen, setIsCustomBlockOpen] = useState(false);
  const [customBlocks,      setCustomBlocks]      = useState([]);

  const [showOnboarding,     setShowOnboarding]     = useState(false);
  const [onboardingData,     setOnboardingData]     = useState({ name: "", org: "", jobTitle: "", purpose: "" });
  const [onboardingSubmitting, setOnboardingSubmitting] = useState(false);

  const [hasEntered,   setHasEntered]   = useState(false);
  const [currentPage,  setCurrentPage]  = useState("app");
  const [isMobile,     setIsMobile]     = useState(() => window.innerWidth < 1024);
  const [rfInstance,   setRfInstance]   = useState(null);

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 1024);
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  const _authHeaders = async () => {
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    const storedKey = localStorage.getItem("rtl_byok_key") || "";
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (storedKey.trim()) headers["X-User-Api-Key"] = storedKey.trim();
    const storedProvider = localStorage.getItem("rtl_byok_provider") || "openai";
    if (storedKey.trim()) headers["X-User-Api-Provider"] = storedProvider;
    const storedModel = localStorage.getItem("rtl_byok_model") || "";
    if (storedKey.trim() && storedModel.trim()) headers["X-User-Model"] = storedModel.trim();
    return headers;
  };

  useEffect(() => {
    if (!user) { setCustomBlocks([]); return; }
    (async () => {
      try {
        const headers = await _authHeaders();
        const res  = await fetch(`${API_BASE}/custom_blocks`, { headers });
        const data = await res.json();
        if (data.status === "ok") setCustomBlocks(data.blocks || []);
      } catch (e) { /* non-fatal */ }
    })();
  }, [user]);

  const fetchProjects = async () => {
    setProjectsLoading(true);
    try {
      const headers = await _authHeaders();
      const res = await fetch(`${API_BASE}/projects`, { headers });
      if (res.status === 401) { setUser(null); return; }
      const d = await res.json();
      if (d.status === "ok") setProjects(d.projects || []);
    } catch (e) { console.error("fetchProjects:", e); }
    finally { setProjectsLoading(false); }
  };

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        const u = session.user;
        setUser({ id: u.id, name: u.user_metadata?.full_name || u.email, email: u.email, avatar: u.user_metadata?.avatar_url || null });
        fetchProjects();
      }
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (session?.user) {
        const u = session.user;
        const profile = { id: u.id, name: u.user_metadata?.full_name || u.email, email: u.email, avatar: u.user_metadata?.avatar_url || null };
        setUser(profile);
        setIsAuthOpen(false);
        fetchProjects();
        if (event === "SIGNED_IN") {
          setHasEntered(true);
          const key = `rtl_onboarded_${session.user.id}`;
          if (!localStorage.getItem(key)) {
            setOnboardingData((d) => ({ ...d, name: session.user.user_metadata?.full_name || "" }));
            setTimeout(() => setShowOnboarding(true), 600);
          }
        }
      } else {
        setUser(null); setProjects([]);
      }
    });
    return () => subscription.unsubscribe();
  }, []); 

  const handleSignIn = async () => {
    const IS_DESKTOP = typeof window !== "undefined" && window.electronAPI !== undefined;
  await supabase.auth.signInWithOAuth({ 
  provider: "google", 
  options: { 
    redirectTo: IS_DESKTOP ? "http://localhost:5173" : window.location.origin,
    queryParams: {
      prompt: "select_account",
    },
  } 
});
  };

  const handleSignOut = async () => {
    if (isDirty && nodes.length > 0) {
      if (!window.confirm("You have unsaved changes. Sign out and lose them?")) return;
    }
    await supabase.auth.signOut();
    setUser(null); setProjects([]); setIsAuthOpen(false);
    _resetCanvas();
  };


  const _resetCanvas = () => {
    setNodes([]); setEdges([]);
    setParams([{ name: "DATA_WIDTH", value: "8" }]);
    setVerilogFiles({}); setTestbenchCode("");
    setRtlReady(false); setTbReady(false);
    setCurrentProjectId(null); setProjectName("Untitled Design"); setIsDirty(false);
  };


  const saveProject = async () => {
    if (!user) { setIsAuthOpen(true); return; }
    if (isSaving) return;
    if (nodes.length === 0) { showToast("Nothing to save — add some blocks first", "error"); return; }
    setIsSaving(true);
    const canvas = {
      nodes: nodes.map(stripNodeForSave),
      edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle, type: e.type, data: e.data })),
      params,
    };
    try {
      let ok = false;
      const headers = await _authHeaders();
      if (currentProjectId) {
        const res = await fetch(`${API_BASE}/projects/${currentProjectId}`, { method: "PUT", headers, body: JSON.stringify({ name: projectName, canvas }) });
        const d = await res.json();
        ok = d.status === "ok";
      } else {
        const res = await fetch(`${API_BASE}/projects`, { method: "POST", headers, body: JSON.stringify({ name: projectName, description: "", canvas }) });
        const d = await res.json();
        if (d.status === "ok") { setCurrentProjectId(d.project?.id || null); ok = true; }
        if (d.status === "not_configured") { showToast("Supabase not configured — check backend .env", "error"); return; }
      }
      await fetchProjects();
      if (ok) {
        showToast("Project saved!", "success");
        const saveCount = parseInt(localStorage.getItem("rtl_save_count") || "0") + 1;
        localStorage.setItem("rtl_save_count", saveCount);
        if (saveCount === 3) triggerFeedback("project_saved");
      }
    } catch (e) {
      console.error("saveProject:", e);
      showToast("Save failed — check console", "error");
    } finally {
      setIsSaving(false);
    }
  };

  const loadProject = async (proj) => {
    if (isDirty && nodes.length > 0) {
      if (!window.confirm("You have unsaved changes. Load anyway and lose them?")) return;
    }
    try {
      const headers = await _authHeaders();
      const res = await fetch(`${API_BASE}/projects/${proj.id}/load`, { headers });
      if (res.status === 404) { showToast("Project not found", "error"); await fetchProjects(); return; }
      if (res.status === 403) { showToast("Access denied", "error"); return; }
      const d = await res.json();
      if (d.status === "ok" && d.project?.canvas) {
        const { nodes: ns, edges: es, params: ps } = d.project.canvas;
        setNodes((ns || []).map((n) => hydrateNode(n)));
        setEdges((es || []).map((e) => ({ ...e, type: e.data?.isFsm ? "fsm" : "smoothstep", animated: false })));
        if (ps) setParams(ps);
        setProjectName(d.project.name); setCurrentProjectId(proj.id);
        setIsDirty(false); setRtlReady(false); setTbReady(false);
        setVerilogFiles({}); setTestbenchCode("");
        showToast(`Loaded "${proj.name}"`, "success");
      } else {
        showToast("Failed to load — project data is empty", "error");
      }
    } catch (e) { console.error("loadProject:", e); showToast("Failed to load project", "error"); }
  };

  const deleteProject = async (projId, projName) => {
    if (!user) return;
    if (!window.confirm(`Delete "${projName}"? This cannot be undone.`)) return;
    try {
      const headers = await _authHeaders();
      const res = await fetch(`${API_BASE}/projects/${projId}`, { method: "DELETE", headers });
      if (res.status === 403) { showToast("Access denied", "error"); return; }
      if (currentProjectId === projId) _resetCanvas();
      await fetchProjects();
      showToast("Project deleted", "success");
    } catch (e) { console.error("deleteProject:", e); showToast("Delete failed", "error"); }
  };

  const handleValueChange = useCallback((nodeId, newValue) => {
    setNodes((nds) => nds.map((node) => node.id === nodeId ? { ...node, data: { ...node.data, value: newValue } } : node));
  }, [setNodes]);

  const hydrateNode = useCallback((node) => ({
    ...node,
    data: {
      ...node.data,
      onChangeValue: handleValueChange,
      onDelete: (id) => { setNodes((nds) => nds.filter((n) => n.id !== id)); setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id)); },
      setWidth:       (w) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, width: w } } : n)),
      setBitIndex:    (i) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, bitIndex: i } } : n)),
      setMuxSize:     (s) => {
        const numInputs = parseInt(s) || 2;
        const selWidth  = Math.max(1, Math.ceil(Math.log2(numInputs)));
        setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, muxSize: s, selWidth } } : n));
      },
      setJoinerSize:  (s) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, joinerSize: s } } : n)),
      setValue:       (v) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, value: v } } : n)),
      setIterations:  (it) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, iterations: it } } : n)),
      setFifoDepth:   (v) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, fifoDepth: v } } : n)),
      setAeThresh:    (v) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, aeThresh: v } } : n)),
      rename:         (name) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, name } } : n)),
      setLsbPriority: (v) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, lsbPriority: v } } : n)),
      setFsmOutputs:  (v) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, fsmOutputs: v } } : n)),
      setEdgeType:    (v) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, edgeType: v } } : n)),
      setAddrWidth:   (v) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, addrWidth: v } } : n)),
      setCountDir:    (v) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, countDir: v } } : n)),
      setSrMode:      (v) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, srMode: v } } : n)),
      setShiftDir:    (v) => setNodes((ns) => ns.map((n) => n.id === node.id ? { ...n, data: { ...n.data, shiftDir: v } } : n)),
    },
  }), [setNodes, setEdges, handleValueChange]);

  const handleDeleteCustomBlock = async (blockId) => {
    try {
      const headers = await _authHeaders();
      await fetch(`${API_BASE}/custom_blocks/${blockId}`, { method: "DELETE", headers });
      setCustomBlocks(prev => prev.filter(b => b.id !== blockId));
      showToast("Custom block deleted", "info");
    } catch (e) {
      showToast("Failed to delete block", "error");
    }
  };

  const addNode = () => {
    const idx = nextFreeIndex(nodes, selected.type);
    const id  = `${selected.type}_${idx}`;
    const cordicOps = ["sine_cos", "arctan", "sinh_cosh", "tanh", "exp", "ln", "sqrt"];
    if (selected.type === "custom_block") {
      (async () => {
        let customVerilog = selected.customVerilog || "";
        if (!customVerilog && selected.customBlockId) {
          try {
            const headers = await _authHeaders();
            const res  = await fetch(`${API_BASE}/custom_blocks/${selected.customBlockId}/full`, { headers });
            const data = await res.json();
            if (data.status === "ok") customVerilog = data.verilog || "";
          } catch (e) { /* fallback to empty */ }
        }
        setNodes((nds) => [...nds, hydrateNode({
          id, type: "custom_block",
          position: { x: (nodes.length % MAX_COLS) * GRID_X + 50, y: Math.floor(nodes.length / MAX_COLS) * GRID_Y + 50 },
          data: {
            name: selected.customName || id, label: selected.label,
            customName:      selected.customName,
            customPorts:     selected.customPorts     || [],
            customBlockType: selected.customBlockType || "",
            customVerilog,
            customBlockId:   selected.customBlockId,
            width: "8", isMacro: true,
          },
        })]);
      })();
      return;
    }
    setNodes((nds) => [...nds, hydrateNode({
      id, type: selected.type,
      position: { x: (nodes.length % MAX_COLS) * GRID_X + 50, y: Math.floor(nodes.length / MAX_COLS) * GRID_Y + 50 },
      data: { name: id, label: selected.label, op: selected.op, width: "8", value: 0, onChangeValue: handleValueChange, iterations: cordicOps.includes(selected.op) ? "16" : undefined, isMacro: !!selected.abstraction },
    })]);
  };

  const onNodesDelete = useCallback((deleted) => {
    const ids = deleted.map((n) => n.id);
    setEdges((eds) => eds.filter((e) => !ids.includes(e.source) && !ids.includes(e.target)));
  }, [setEdges]);

  const onEdgesDelete = useCallback((deleted) => {
    setEdges((eds) => eds.filter((e) => !deleted.find((d) => d.id === e.id)));
    setNodes((nds) => nds.map((node) => ({ ...node, style: { ...node.style, border: "2px solid #222", boxShadow: "none" } })));
  }, [setEdges, setNodes]);

  const onConnect = useCallback((params) => {
    const sourceNode = nodes.find((n) => n.id === params.source);
    const targetNode = nodes.find((n) => n.id === params.target);
    const isFsmEdge  = sourceNode?.type === "fsm_state" && targetNode?.type === "fsm_state";
    setEdges((eds) => addEdge({
      ...params,
      type: isFsmEdge ? "fsm" : "smoothstep",
      data: { condition: isFsmEdge ? "1" : "", isFsm: isFsmEdge, isEditing: false },
      style: { strokeWidth: 1.5, stroke: isFsmEdge ? T.purple : `${T.blue}cc` },
    }, eds));
  }, [nodes, setEdges]);

  const onEdgeDoubleClick = useCallback((evt, edge) => {
    if (!edge.data?.isFsm) return;
    evt.stopPropagation();
    setEdges((eds) => eds.map((ed) => ({ ...ed, data: { ...ed.data, isEditing: ed.id === edge.id } })));
  }, [setEdges]);

  useEffect(() => {
    const onEdit = (e) => setEdges((eds) => eds.map((ed) => ({ ...ed, data: { ...ed.data, isEditing: ed.id === e.detail } })));
    const onDone = (e) => {
      const { id, val } = e.detail;
      setEdges((eds) => eds.map((ed) => ed.id === id ? { ...ed, data: { ...ed.data, condition: val, isEditing: false } } : ed));
    };
    window.addEventListener("fsm-edge-edit", onEdit);
    window.addEventListener("fsm-edge-done", onDone);
    return () => { window.removeEventListener("fsm-edge-edit", onEdit); window.removeEventListener("fsm-edge-done", onDone); };
  }, [setEdges]);


  const isValidConnection = (connection) => {
    const source = nodes.find((n) => n.id === connection.source);
    const target = nodes.find((n) => n.id === connection.target);
    if (!source || !target) return false;
    if (connection.source === connection.target) return false;
    if (source.type === "output") return false;
    if (target.type === "input") return false;
    if (edges.some((e) => e.target === connection.target && e.targetHandle === connection.targetHandle)) return false;
    if ((target.data.op === "buf" || target.data.op === "not") && connection.targetHandle === "in1") return false;
    return true;
  };


  const calculateCircuit = (currentNodes, currentEdges) => {
    const memo = {};
    const computeNode = (nodeId) => {
      if (memo[nodeId] !== undefined) return memo[nodeId];
      const node = currentNodes.find((n) => n.id === nodeId);
      if (!node) return 0;
      if (node.type === "input" || node.type === "const" || node.data.op === "const") return node.data.value;
      if (node.type === "reg" || node.type === "fsm_state" || node.type.startsWith("macro_")) return parseInt(node.data.value || 0);
      const incoming = currentEdges.filter((e) => e.target === nodeId);
      const getValFromPin = (pinId) => { const edge = incoming.find((e) => e.targetHandle === pinId); return edge ? computeNode(edge.source) : 0; };
      const in0 = getValFromPin("in0") || getValFromPin("in");
      const in1 = getValFromPin("in1");
      let out = 0;
      if (node.type === "mux") {
        const numInputs = parseInt(node.data.muxSize || 2);
        const numSelBits = Math.max(1, Math.ceil(Math.log2(numInputs)));
        let selValue = 0;
        for (let i = 0; i < numSelBits; i++) selValue |= ((getValFromPin(`sel${i}`) || 0) & 1) << i;
        out = getValFromPin(`in${Math.min(selValue, numInputs - 1)}`) || 0;
      } else if (node.type === "splitter") {
        const rawRange = (node.data.bitIndex || "0").toString().trim();
        if (rawRange.includes(":")) {
          const [hiStr, loStr] = rawRange.split(":");
          const hi = parseInt(hiStr) || 0; const lo = parseInt(loStr) || 0;
          out = (in0 >> lo) & ((1 << (hi - lo + 1)) - 1);
        } else { out = (in0 >> (parseInt(rawRange) || 0)) & 1; }
      } else if (node.type === "concatenator") {
        out = (in0 << 8) | in1;
      } else if (node.type === "encoder") {
        out = 1 << in0;
      } else if (node.type === "decoder") {
        out = Math.log2(in0 & -in0); if (!isFinite(out)) out = 0;
      } else {
        switch (node.data.op || node.type) {
          case "and": out = in0 & in1; break; case "or":  out = in0 | in1; break;
          case "xor": out = in0 ^ in1; break; case "not": out = ~in0; break;
          case "buf": out = in0; break;  case "probe": out = in0; break;
          case "add": out = in0 + in1; break; case "sub": out = in0 - in1; break;
          case "mul": out = in0 * in1; break;
          case "eq":  out = (in0 === in1) ? 1 : 0; break;
          case "gt":  out = (in0 > in1)   ? 1 : 0; break;
          case "lt":  out = (in0 < in1)   ? 1 : 0; break;
          default: out = in0;
        }
      }
      out = out & ((1 << parseInt(node.data.width || 8)) - 1);
      memo[nodeId] = out;
      return out;
    };
    return currentNodes.map((node) => ({ ...node, data: { ...node.data, value: computeNode(node.id) } }));
  };

  const nodesRef = useRef(nodes);
  useEffect(() => { nodesRef.current = nodes; }, [nodes]);

  const nodeValuesKey = nodes.map((n) => n.data.value).join(",");
  useEffect(() => {
    const loops = detectLoops(nodesRef.current, edges);
    if (loops.length === 0) {
      setNodes((nds) => {
        const updated = calculateCircuit(nds, edges);
        const hasChanged = updated.some((node, i) => node.data.value !== nds[i]?.data.value);
        return hasChanged ? updated : nds;
      });
    }
  }, [edges, nodeValuesKey, setNodes]); // eslint-disable-line

  const triggerClockTick = () => {
    setNodes((nds) => {
      const valOf = (nodeId) => { const n = nds.find((x) => x.id === nodeId); return n ? (parseInt(n.data.value) || 0) : 0; };
      return nds.map((node) => {
        if (node.type === "reg") { const e = edges.find((e) => e.target === node.id && e.targetHandle === "d"); if (e) return { ...node, data: { ...node.data, value: valOf(e.source) } }; }
        if (node.type === "macro_counter") {
          const enEdge = edges.find((e) => e.target === node.id && e.targetHandle === "en");
          const en = enEdge ? valOf(enEdge.source) : 1;
          if (en) { const w = parseInt(node.data.width || 8); const max = Math.pow(2, w) - 1; const cur = parseInt(node.data.value) || 0; return { ...node, data: { ...node.data, value: cur >= max ? 0 : cur + 1 } }; }
        }
        if (node.type === "macro_shiftreg") {
          const mode = (node.data.srMode || "PISO").toUpperCase();
          const dir  = (node.data.shiftDir || "right").toLowerCase();
          const w    = parseInt(node.data.width || 8);
          const cur  = parseInt(node.data.value) || 0;
          const mask = Math.pow(2, w) - 1;

          const enEdge   = edges.find((e) => e.target === node.id && e.targetHandle === "en");
          const loadEdge = edges.find((e) => e.target === node.id && e.targetHandle === "load");
          const dinEdge  = edges.find((e) => e.target === node.id && e.targetHandle === "din");
          const sinEdge  = edges.find((e) => e.target === node.id && e.targetHandle === "sin");

          const en   = enEdge   ? valOf(enEdge.source)   : 1;
          const load = loadEdge ? valOf(loadEdge.source) : 0;
          const din  = dinEdge  ? valOf(dinEdge.source)  : 0;
          const sin  = sinEdge  ? (valOf(sinEdge.source) & 1) : 0;

          if (load && (mode === "PISO" || mode === "PIPO")) {
            return { ...node, data: { ...node.data, value: din & mask } };
          }
          if (en) {
            let next = cur;
            if (mode === "SISO" || mode === "SIPO") {
              // Serial in
              if (dir === "right") next = ((sin << (w - 1)) | (cur >> 1)) & mask;
              else                 next = ((cur << 1) | sin) & mask;
            } else if (mode === "PISO") {
              // Shift only (parallel load handled above)
              if (dir === "right") next = (cur >> 1) & mask;
              else                 next = (cur << 1) & mask;
            } else if (mode === "PIPO") {
              next = din & mask;  // PIPO: only load makes sense
            }
            return { ...node, data: { ...node.data, value: next } };
          }
        }
        return node;
      });
    });
  };

  const runDRC = () => {
    const errorNodes = new Set(); const warnNodes = new Set(); const logs = [];
    const resolveOutWidth = (node, srcPort) => {
      if (!node) return 1;
      const w = parseInt(node.data.width || "1");
      if (node.type === "macro_fifo") return ["full","empty","ae"].includes(srcPort) ? 1 : w;
      if (node.type === "macro_penc") return srcPort === "valid" ? 1 : Math.max(1, Math.ceil(Math.log2(Math.max(w, 2))));
      if (node.type === "macro_cfgcounter") return srcPort === "tc" ? 1 : w;
      if (node.type === "macro_edgedet") return 1;
      return w;
    };
    const expectedPinWidth = (node, pinId) => {
      const w = parseInt(node.data.width || "1");
      if (node.type === "mux") return pinId.startsWith("sel") ? 1 : w;
      if (node.type === "macro_fifo") return (pinId === "wr_en" || pinId === "rd_en") ? 1 : w;
      if (node.type === "macro_cfgcounter") return (pinId === "enable" || pinId === "load") ? 1 : w;
      if (node.type === "macro_dpram") { const aw = parseInt(node.data.addrWidth || "6"); if (pinId === "we_a" || pinId === "we_b") return 1; if (pinId === "addr_a" || pinId === "addr_b") return aw; return w; }
      if (node.type === "macro_edgedet") return 1;
      if (node.type === "splitter" || node.type === "concatenator") return null;
      if (node.type === "macro_counter") return (pinId === "en" || pinId === "res") ? 1 : w;
      if (node.type === "macro_shiftreg") return pinId === "en" ? 1 : w;
      return w;
    };
    nodes.forEach((targetNode) => {
      const incomingEdges = edges.filter((e) => e.target === targetNode.id);
      const usedHandles = new Set();
      incomingEdges.forEach((edge) => {
        const pinId = edge.targetHandle || "default";
        const srcNode = nodes.find((n) => n.id === edge.source);
        const srcPort = edge.sourceHandle || "out";
        if (usedHandles.has(pinId)) { errorNodes.add(targetNode.id); logs.push(`❌ Collision: Multiple drivers on "${pinId}" of ${targetNode.data.name}`); }
        usedHandles.add(pinId);
        if (!srcNode) return;
        const actualSrcWidth = resolveOutWidth(srcNode, srcPort);
        if (targetNode.type === "splitter" && pinId === "in") {
          const raw = (targetNode.data.bitIndex || "0").toString().trim();
          const hi  = parseInt(raw.includes(":") ? raw.split(":")[0] : raw) || 0;
          if (actualSrcWidth < hi + 1) { errorNodes.add(targetNode.id); errorNodes.add(srcNode.id); logs.push(`📏 Splitter too narrow: ${srcNode.data.name} (${actualSrcWidth}-bit) → ${targetNode.data.name} needs ≥${hi+1} bits`); }
          return;
        }
        const expected = expectedPinWidth(targetNode, pinId);
        if (expected !== null && actualSrcWidth !== expected) {
          errorNodes.add(targetNode.id); errorNodes.add(srcNode.id);
          logs.push(`📏 Width mismatch: ${srcNode.data.name}.${srcPort} (${actualSrcWidth}-bit) → ${targetNode.data.name}.${pinId} (expects ${expected}-bit)`);
        }
      });
      const connectedPins = new Set(incomingEdges.map((e) => e.targetHandle));
      if (targetNode.type === "comb") {
        const unary = targetNode.data.op === "buf" || targetNode.data.op === "not";
        if (!connectedPins.has("in0")) { warnNodes.add(targetNode.id); logs.push(`⚠️  ${targetNode.data.name}: input "in0" unconnected`); }
        if (!unary && !connectedPins.has("in1")) { warnNodes.add(targetNode.id); logs.push(`⚠️  ${targetNode.data.name}: input "in1" unconnected`); }
      }
      const REQUIRED_PINS = { reg: ["d"], macro_counter: ["en"], macro_shiftreg: ["din","en"], macro_sync: ["d"], macro_edgedet: ["signal_in"], macro_cfgcounter: ["enable"], macro_fifo: ["wr_en","din","rd_en"], macro_dpram: ["addr_a","addr_b"] };
      (REQUIRED_PINS[targetNode.type] || []).forEach((pin) => { if (!connectedPins.has(pin)) { warnNodes.add(targetNode.id); logs.push(`⚠️  ${targetNode.data.name}: required pin "${pin}" unconnected`); } });
    });
    detectLoops(nodes, edges).forEach((msg) => {
      logs.push(`🔄 ${msg}`);
      nodes.forEach((n) => { if (msg.includes(n.data.name) || msg.includes(n.id)) errorNodes.add(n.id); });
    });
    setNodes((nds) => nds.map((node) => {
      const isErr  = errorNodes.has(node.id);
      const isWarn = warnNodes.has(node.id);
      if (!isErr && !isWarn) { const { border: _b, boxShadow: _s, ...restStyle } = node.style || {}; return { ...node, style: restStyle }; }
      return { ...node, style: { ...(node.style || {}), border: isErr ? "2px solid #ef4444" : "2px solid #f59e0b", boxShadow: isErr ? "0 0 12px rgba(239,68,68,0.45)" : "0 0 10px rgba(245,158,11,0.4)" } };
    }));
    const structured = logs.map((msg) => ({ msg, type: msg.startsWith("❌") || msg.startsWith("🔄") ? "error" : msg.startsWith("⚠") ? "warn" : "info" }));
    if (structured.length === 0) structured.push({ msg: "✅ DRC Passed — no issues found!", type: "pass" });
    setDrcLogs(structured);
    setShowBottomPanel(true);
    setActiveTab("drc");
  };

  const compileIR = () => {
    let hwN = []; let hwE = [];
    const macroTypes = ["macro_counter","macro_sync","macro_shiftreg","macro_rom","encoder","decoder","macro_fifo","macro_penc","macro_edgedet","macro_dpram","macro_cfgcounter"];
    nodes.forEach((n) => {
      const w = n.data.width; const nm = n.data.name;
      if (n.type === "custom_block") {
        hwN.push({ id: n.id, type: "custom_block", name: nm, width: w,
          customName:      n.data.customName      || nm,
          customPorts:     n.data.customPorts     || [],
          customVerilog:   n.data.customVerilog   || "",
          customBlockType: n.data.customBlockType || "",
          customBlockId:   n.data.customBlockId   || "",
        });
        edges.filter((e) => e.target === n.id || e.source === n.id).forEach((e) => {
          if (!hwE.some((ex) => ex.src === e.source && ex.dst === e.target && ex.src_port === e.sourceHandle && ex.dst_port === e.targetHandle))
            hwE.push({ src: e.source, dst: e.target, src_port: e.sourceHandle, dst_port: e.targetHandle, condition: "1" });
        });
      } else if (macroTypes.includes(n.type)) {
        hwN.push({ id: n.id, type: n.type, name: nm, width: w, depth: n.data.depth || "256", joinerSize: n.data.joinerSize, fifoDepth: n.data.fifoDepth || "16", aeThresh: n.data.aeThresh || "4", lsbPriority: n.data.lsbPriority ?? 0, edgeType: n.data.edgeType ?? 0, addrWidth: n.data.addrWidth || "6", countDir: n.data.countDir ?? 1, srMode: n.data.srMode || "PISO", shiftDir: n.data.shiftDir || "right", terminalValue: n.data.terminalValue || null });
        edges.filter((e) => e.target === n.id || e.source === n.id).forEach((e) => {
          if (!hwE.some((ex) => ex.src === e.source && ex.dst === e.target && ex.src_port === e.sourceHandle && ex.dst_port === e.targetHandle))
            hwE.push({ src: e.source, dst: e.target, src_port: e.sourceHandle, dst_port: e.targetHandle, condition: e.data?.condition || e.label || "1", ...(e.priority !== undefined ? { priority: e.priority } : {}) });
        });
      } else if (!n.data.isMacro) {
        hwN.push({ id: n.id, type: n.type, op: n.data.op, width: w, value: n.data.value, bitIndex: n.data.bitIndex, name: nm, muxSize: n.data.muxSize, joinerSize: n.data.joinerSize, fsmOutputs: n.data.fsmOutputs || [], srMode: n.data.srMode || "PISO", shiftDir: n.data.shiftDir || "right", isFsmOutput: n.data.isFsmOutput || false, overrides: n.data.overrides, default: n.data.default, fsm: n.data.fsm });
        edges.filter((e) => e.source === n.id || e.target === n.id).forEach((e) => {
          if (!hwE.some((ex) => ex.src === e.source && ex.dst === e.target && ex.src_port === e.sourceHandle && ex.dst_port === e.targetHandle))
            hwE.push({ src: e.source, dst: e.target, src_port: e.sourceHandle, dst_port: e.targetHandle, condition: e.data?.condition || e.label || "1", ...(e.priority !== undefined ? { priority: e.priority } : {}) });
        });
      }
    });
    const output_logic = nodes
      .filter((n) => n.id.startsWith("_output_mux") && n.data?.op === "__state_mux__")
      .map((n) => ({
        output:    n.data.name    || "",
        type:      "state_mux",
        fsm:       n.data.fsm    || "",
        default:   n.data.default    || "1'b0",
        overrides: n.data.overrides  || {},
      }));
    return { module: "top", parameters: Object.fromEntries(params.map((p) => [p.name, p.value])), ports: nodes.filter((n) => ["input","output"].includes(n.type)).map((n) => ({ id: n.id, name: n.data.name, dir: n.type, width: n.data.width })), nodes: hwN, edges: hwE, output_logic };
  };


  const generateVerilog = async () => {
    try {
      // Use canonicalIR from AI path if available — it has signal_list, output_logic,
      // gated_by etc. that compileIR() (canvas recompile) cannot reconstruct.
      // Fall back to compileIR() for manual-only canvas builds.
      let ir = canonicalIR ?? compileIR();
      // Patch custom blocks into IR — canonicalIR never contains them
      const _cbNodes = nodes.filter(n => n.type === "custom_block");
      if (_cbNodes.length > 0) {
        const _existingIds = new Set((ir.nodes || []).map(n => n.id));
        const _newCb = _cbNodes.filter(n => !_existingIds.has(n.id)).map(n => ({
          id: n.id, type: "custom_block", name: n.data.name, width: n.data.width,
          customName:      n.data.customName      || n.data.name,
          customPorts:     n.data.customPorts     || [],
          customVerilog:   n.data.customVerilog   || "",
          customBlockType: n.data.customBlockType || "",
          customBlockId:   n.data.customBlockId   || "",
        }));
        const _cbEdges = edges
          .filter(e => _cbNodes.some(n => n.id === e.source || n.id === e.target))
          .map(e => ({ src: e.source, dst: e.target, src_port: e.sourceHandle, dst_port: e.targetHandle, condition: "1" }))
          .filter(e => !(ir.edges||[]).some(x => x.src===e.src && x.dst===e.dst && x.src_port===e.src_port));
        ir = { ...ir, nodes: [...(ir.nodes||[]), ..._newCb], edges: [...(ir.edges||[]), ..._cbEdges] };
      }
      const res = await fetch(`${API_BASE}/generate_verilog`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ir }) });
      const data = await res.json();
      if (data.files) { setVerilogFiles(data.files); setActiveRtlFile("top.v"); setRtlReady(true); setTbReady(false); showToast("RTL generated", "success"); triggerFeedback("rtl_generated"); }
      else if (data.verilog) { setVerilogFiles({ "top.v": data.verilog }); setActiveRtlFile("top.v"); setRtlReady(true); }
    } catch (err) { showToast("Error generating Verilog", "error"); }
  };

  const generateTB = async () => {
    try {
      const res = await fetch(`${API_BASE}/generate_testbench`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ir: compileIR(), stimulus: { steps: tbSteps, reset_type: tbConfig.resetType, reset_active: tbConfig.resetActive, use_corner_cases: tbConfig.useCornerCases, use_random: tbConfig.useRandom, num_random_steps: Number(tbConfig.numRandomSteps) || 8, random_seed: tbConfig.randomSeed !== "" ? parseInt(tbConfig.randomSeed, 10) : null, sim_duration_ns: Number(tbConfig.simDurationNs) || 2000 } }),
      });
      const data = await res.json();
      setTestbenchCode(data.testbench); setTbReady(true); setTbConfigDirty(false);
      showToast("Testbench generated", "success");
    } catch (err) { showToast("Error generating Testbench", "error"); }
  };

  const runSimulation = async () => {
    if (!verilogFiles["top.v"] || !testbenchCode) { showToast("Generate RTL and Testbench first", "error"); return; }
    setSimulating(true);
    try {
      const response = await fetch(`${API_BASE}/simulate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ verilog_files: verilogFiles, testbench: testbenchCode }) });
      const result = await response.json();
      if (result.status === "success") { setSimulationResult(result); setShowWaveform(true); showToast("Simulation complete", "success"); triggerFeedback("simulation_done"); }
      else { showToast("Simulation failed — check console", "error"); setShowBottomPanel(true); }
    } catch (error) { showToast("Simulation error: " + error.message, "error"); }
    finally { setSimulating(false); }
  };

  const runVerification = async () => {
    if (!verilogFiles["top.v"]) { showToast("Generate RTL first (◈ RTL)", "error"); return; }
    const hasManualStepsWithExpected = tbSteps.some((s) => !s._auto && s.expected && Object.values(s.expected).some((v) => String(v).trim() !== ""));
    if (tbConfig.useRandom && !hasManualStepsWithExpected) { setVerifyRandomWarning(true); return; }
    setVerifyRandomWarning(false);
    setVerifyLoading(true);
    try {
      const headers = await _authHeaders();
      const res = await fetch(`${API_BASE}/ai_verify`, {
        method: "POST", headers,
        body: JSON.stringify({ ir: compileIR(), verilog_files: verilogFiles, design_intent: verifyIntent.trim(), stimulus: { steps: tbSteps, reset_type: tbConfig.resetType, reset_active: tbConfig.resetActive, use_corner_cases: tbConfig.useCornerCases, use_random: tbConfig.useRandom, num_random_steps: Number(tbConfig.numRandomSteps) || 8, random_seed: tbConfig.randomSeed !== "" ? parseInt(tbConfig.randomSeed, 10) : null, sim_duration_ns: Number(tbConfig.simDurationNs) || 2000 } }),
      });
      const data = await res.json();
      const lastIter = (data.iterations || []).slice(-1)[0] || {};
      if (data.status !== "ok") { setVerifyHistory((h) => [...h, { role: "agent", text: data.error || data.summary || "Verification failed.", verdict: "error", pass_count: 0, fail_count: 0, iterations: [], testbench: "", console: "" }]); return; }
      setVerifyHistory((h) => [...h, { role: "agent", text: data.summary, verdict: data.verdict, pass_count: data.pass_count, fail_count: data.fail_count, issue_type: data.issue_type || "", next_action: data.next_action || "", iterations: data.iterations || [], edits: data.edits_applied || [], testbench: lastIter.testbench || "", console: lastIter.console || "" }]);
    } catch (err) { setVerifyHistory((h) => [...h, { role: "agent", text: `Connection error: ${err.message}`, verdict: "error", pass_count: 0, fail_count: 0, iterations: [], testbench: "", console: "" }]); }
    finally { setVerifyLoading(false); }
  };

  const runAutoVerification = async () => {
    if (!verilogFiles["top.v"]) { showToast("Generate RTL first (◈ RTL)", "error"); return; }
    setVerifyAutoLoading(true);
    try {
      const headers = await _authHeaders();
      const res = await fetch(`${API_BASE}/ai_auto_verify`, { method: "POST", headers, body: JSON.stringify({ ir: compileIR(), verilog_files: verilogFiles }) });
      const data = await res.json();
      if (data.status !== "ok") { setVerifyHistory((h) => [...h, { role: "auto_agent", text: data.error || "Auto-verification failed.", verdict: "error", confidence: "", circuit_type: "", test_plan: null, findings: [], iterations: [], suggested_fix: "" }]); return; }
      setVerifyHistory((h) => [...h, { role: "auto_agent", text: data.summary, verdict: data.verdict, confidence: data.confidence, circuit_type: data.circuit_type, circuit_description: data.circuit_description, test_plan: data.test_plan, findings: data.findings || [], root_cause: data.root_cause || "", suggested_fix: data.suggested_fix || "", coverage_assessment: data.coverage_assessment || "", iterations: data.iterations || [] }]);
    } catch (err) { setVerifyHistory((h) => [...h, { role: "auto_agent", text: `Connection error: ${err.message}`, verdict: "error", confidence: "", circuit_type: "", test_plan: null, findings: [], iterations: [], suggested_fix: "" }]); }
    finally { setVerifyAutoLoading(false); }
  };


  if (isMobile) {
    return (
      <div style={{ width: "100vw", height: "100vh", background: "#0b0d14", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", fontFamily: "'IBM Plex Sans', sans-serif", padding: "32px 24px", textAlign: "center" }}>
        <style>{`@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');`}</style>
        <div style={{ width: "64px", height: "64px", borderRadius: "16px", background: "#0f1320", border: "1px solid #1a2030", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "28px", marginBottom: "28px" }}>⌨</div>
        <h1 style={{ fontSize: "24px", fontWeight: "700", color: "#e2e8f0", letterSpacing: "-0.5px", marginBottom: "12px", lineHeight: 1.2 }}>RTL Copilot requires<br />a larger screen</h1>
        <p style={{ fontSize: "15px", color: "#475569", lineHeight: "1.65", maxWidth: "300px", marginBottom: "32px" }}>Circuit design, waveform simulation, and Verilog editing require a laptop or desktop display.</p>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", padding: "14px 20px", background: "#0f1320", border: "1px solid #1a2030", borderRadius: "10px", fontSize: "13px", color: "#334155", fontFamily: "'JetBrains Mono', monospace" }}>
          <span style={{ color: "#2563eb" }}>min_width</span>
          <span style={{ color: "#475569" }}>=</span>
          <span style={{ color: "#34a870" }}>1024px</span>
        </div>
      </div>
    );
  }


  if (currentPage === "privacy") {
    return (
      <div style={{ width:"100vw", minHeight:"100vh", background:"#0b0d14", fontFamily:"'IBM Plex Sans',sans-serif", color:"#cdd5e0", overflowY:"auto" }}>
        <div style={{ maxWidth:"760px", margin:"0 auto", padding:"60px 32px" }}>
          <button onClick={() => setCurrentPage("app")} style={{ background:"none", border:"none", color:"#3b9eff", cursor:"pointer", fontSize:"13px", marginBottom:"32px", padding:0 }}>← Back</button>
          <h1 style={{ fontSize:"32px", fontWeight:"700", color:"#e2e8f0", marginBottom:"8px" }}>Privacy Policy</h1>
          <p style={{ fontSize:"13px", color:"#475569", marginBottom:"40px" }}>Last updated: March 2026</p>
          {[
            { title:"Information We Collect", body:"We collect information you provide when creating an account (name, email via Google OAuth), circuit designs you save to the cloud, feedback you submit, and usage data such as the number of AI generations used." },
            { title:"How We Use Your Information", body:"We use your information to provide and improve RTL Copilot, send important service updates, and analyse usage patterns to build better features." },
            { title:"AI Training Data (Free Plan)", body:"To improve RTL Copilot's AI circuit generation, circuit designs and prompts submitted by users on the Free plan may be used to train and evaluate our models. By using the Free plan, you consent to this use. Starter and Pro plan users are opted out of training data collection by default." },
            { title:"Data Storage", body:"Your data is stored securely on Supabase. Circuit designs are associated with your account and protected by row-level security — no other user can access your projects." },
            { title:"Contact", body:"For privacy questions or data requests, contact us at privacy@rtlcopilot.com" },
          ].map((s,i) => (
            <div key={i} style={{ marginBottom:"28px", paddingBottom:"28px", borderBottom:"1px solid #131820" }}>
              <h2 style={{ fontSize:"16px", fontWeight:"600", color:"#cbd5e1", marginBottom:"10px" }}>{s.title}</h2>
              <p style={{ fontSize:"14px", color:"#64748b", lineHeight:"1.8" }}>{s.body}</p>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (currentPage === "docs") {
    return (
      <div style={{ width:"100vw", minHeight:"100vh", background:"#0b0d14", fontFamily:"'IBM Plex Sans',sans-serif", color:"#cdd5e0", overflowY:"auto" }}>
        <div style={{ maxWidth:"760px", margin:"0 auto", padding:"60px 32px" }}>
          <button onClick={() => setCurrentPage("app")} style={{ background:"none", border:"none", color:"#3b9eff", cursor:"pointer", fontSize:"13px", marginBottom:"32px", padding:0 }}>← Back to app</button>
          <h1 style={{ fontSize:"32px", fontWeight:"700", color:"#e2e8f0", marginBottom:"8px" }}>Documentation</h1>
          <p style={{ fontSize:"14px", color:"#475569", marginBottom:"48px" }}>Everything you need to design, simulate, and export RTL circuits.</p>
          <p style={{ fontSize:"13px", color:"#475569", lineHeight:"1.8" }}>Full documentation lives in the app. Open RTL Copilot and click the Docs button in the toolbar for interactive help.</p>
        </div>
      </div>
    );
  }

  if (currentPage === "pd") {
    return <PDPage verilogFiles={verilogFiles} onBack={() => setCurrentPage("app")} />;
  }

  if (!hasEntered) {
    return (
      <div style={{ width:"100vw", minHeight:"100vh", background:"#090e18", fontFamily:"'IBM Plex Sans', sans-serif", color:"#cdd5e0", overflowY:"auto" }}>
        <nav style={{ position:"fixed", top:0, left:0, right:0, zIndex:100, height:"64px", display:"flex", alignItems:"center", padding:"0 40px", justifyContent:"space-between", background:"rgba(9,14,24,0.90)", backdropFilter:"blur(20px)", borderBottom:"1px solid #0e1520" }}>
          <span style={{ fontSize:"17px", fontWeight:"700", color:"#d8e4f0" }}>RTL <span style={{ color:"#4d7cff" }}>Copilot</span></span>
          <div style={{ display:"flex", gap:"10px" }}>
            <button onClick={() => setHasEntered(true)} style={{ height:"38px", padding:"0 18px", background:"transparent", border:"1px solid #1c2840", borderRadius:"8px", color:"#6b849e", fontSize:"14px", cursor:"pointer", fontFamily:"'IBM Plex Sans',sans-serif" }}>Sign In</button>
            <button onClick={() => setHasEntered(true)} style={{ height:"38px", padding:"0 20px", background:"#4d7cff", border:"none", borderRadius:"8px", color:"#fff", fontSize:"14px", fontWeight:"600", cursor:"pointer", fontFamily:"'IBM Plex Sans',sans-serif" }}>Get Started</button>
          </div>
        </nav>
        <section style={{ minHeight:"100vh", display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", padding:"120px 40px 80px", textAlign:"center" }}>
          <h1 style={{ fontSize:"clamp(40px,5.5vw,68px)", fontWeight:"700", letterSpacing:"-2.5px", lineHeight:1.06, color:"#f1f5f9", marginBottom:"22px" }}>
            Design circuits visually.<br />
            <span style={{ color:"#6b849e" }}>Get production Verilog instantly.</span>
          </h1>
          <p style={{ fontSize:"18px", color:"#6b849e", lineHeight:"1.75", maxWidth:"460px", marginBottom:"38px" }}>
            RTL Copilot is an AI-assisted hardware design platform. Drag blocks, describe circuits in plain English, and export clean hierarchical Verilog — all in the browser.
          </p>
          <div style={{ display:"flex", gap:"12px" }}>
            <button onClick={() => setHasEntered(true)} style={{ height:"50px", padding:"0 30px", borderRadius:"10px", background:"#4d7cff", border:"none", fontSize:"16px", fontWeight:"600", color:"#fff", cursor:"pointer", fontFamily:"'IBM Plex Sans',sans-serif" }}>Start Designing Free →</button>
            <button onClick={() => setCurrentPage("docs")} style={{ height:"50px", padding:"0 26px", borderRadius:"10px", background:"transparent", border:"1px solid #1c2840", fontSize:"15px", color:"#6b849e", cursor:"pointer", fontFamily:"'IBM Plex Sans',sans-serif" }}>See How It Works</button>
          </div>
        </section>
        <footer style={{ borderTop:"1px solid #0a0e18", padding:"32px 40px", textAlign:"center" }}>
          <p style={{ fontSize:"13px", color:"#1e293b" }}>&copy; {new Date().getFullYear()} RTL Copilot · <span style={{ cursor:"pointer", color:"#334155" }} onClick={() => setCurrentPage("privacy")}>Privacy</span> · <a href="mailto:rtlcopilot@gmail.com" style={{ color:"#334155", textDecoration:"none" }}>Contact</a></p>
        </footer>
      </div>
    );
  }

  return (
    <div style={{ width: "100vw", height: "100vh", display: "flex", flexDirection: "column", fontFamily: T.fontUI, background: T.bg1, color: T.textPrimary }}>

      {/* Sign-in gate */}
      {!user && (
        <div style={{ position: "fixed", inset: 0, zIndex: 3000, background: "#080c14", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", fontFamily: T.fontUI }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "28px", fontWeight: "700", color: T.textPrimary, marginBottom: "8px" }}>RTL <span style={{ color: T.blue }}>Copilot</span></div>
            <div style={{ fontSize: "14px", color: T.textMuted, marginBottom: "32px" }}>Sign in to access the canvas</div>
            <button onClick={() => setIsAuthOpen(true)}
              style={{ padding: "10px 28px", fontSize: "14px", fontWeight: "600", background: `linear-gradient(135deg, ${T.blue}22, ${T.violet}22)`, border: `1px solid ${T.blue}55`, borderRadius: T.r8, color: T.blue, cursor: "pointer", fontFamily: T.fontUI }}>
              Sign in with Google
            </button>
            <div style={{ marginTop: "16px" }}>
              <button onClick={() => setHasEntered(false)} style={{ background: "none", border: "none", color: T.textMuted, fontSize: "12px", cursor: "pointer", fontFamily: T.fontUI }}>← Back to home</button>
            </div>
          </div>
        </div>
      )}

      {/* Toolbar */}
      <Toolbar
        setHasEntered={setHasEntered} setCurrentPage={setCurrentPage}
        user={user} setIsAiOpen={setIsAiOpen}
        byokKey={byokKey} setIsByokOpen={setIsByokOpen}
        byokProvider={byokProvider} setByokProvider={setByokProvider}
        runDRC={runDRC} triggerClockTick={triggerClockTick}
        rtlReady={rtlReady} tbReady={tbReady} nodes={nodes} simulating={simulating}
        generateVerilog={generateVerilog} generateTB={generateTB} runSimulation={runSimulation}
        setShowBottomPanel={setShowBottomPanel} setActiveTab={setActiveTab}
        verilogFiles={verilogFiles} testbenchCode={testbenchCode}
        projectName={projectName} setProjectName={setProjectName}
        saveProject={saveProject} isSaving={isSaving} isDirty={isDirty}
        showBottomPanel={showBottomPanel}
        isDropdownOpen={isDropdownOpen} setIsDropdownOpen={setIsDropdownOpen}
        fetchProjects={fetchProjects} 
        setIsAuthOpen={setIsAuthOpen}
        projects={projects} projectsLoading={projectsLoading} currentProjectId={currentProjectId}
        loadProject={loadProject} deleteProject={deleteProject} handleSignOut={handleSignOut}
        resetCanvas={_resetCanvas}
      />

      {/* Parameter bar */}
      <div style={{ height: "34px", flexShrink: 0, display: "flex", alignItems: "center", gap: "6px", padding: "0 14px", background: T.bg1, borderBottom: `1px solid ${T.border0}`, overflowX: "auto" }}>
        <span style={{ fontSize: "12px", fontWeight: "700", color: T.textMuted, textTransform: "uppercase", letterSpacing: "1.5px", fontFamily: T.fontMono, whiteSpace: "nowrap", flexShrink: 0 }}>param</span>
        {params.map((p, i) => (
          <div key={i} className="param-chip">
            <input value={p.name} onChange={(e) => { const n = [...params]; n[i].name = e.target.value; setParams(n); }} style={{ width: `${Math.max(40, p.name.length * 7.5)}px` }} />
            <span className="param-eq">=</span>
            <input className="param-val" value={p.value} onChange={(e) => { const n = [...params]; n[i].value = e.target.value; setParams(n); }} />
            <button className="param-del" onClick={() => { if (params.length > 1) setParams(params.filter((_, idx) => idx !== i)); }}>×</button>
          </div>
        ))}
        <button onClick={() => setParams([...params, { name: "PARAM", value: "0" }])}
          style={{ height: "24px", padding: "0 9px", background: "transparent", border: `1px dashed ${T.border2}`, borderRadius: T.r6, color: T.textMuted, fontSize: "17px", cursor: "pointer", fontFamily: T.fontUI, whiteSpace: "nowrap" }}
          onMouseEnter={(e) => { e.currentTarget.style.color = T.textSecondary; e.currentTarget.style.borderColor = `${T.blue}44`; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = T.textMuted; e.currentTarget.style.borderColor = T.border2; }}>
          + param
        </button>
        {/* Clear canvas button */}
        {nodes.length > 0 && (
          <button onClick={() => {
            if (window.confirm("Clear the canvas? This will remove all blocks and connections.")) {
              _resetCanvas();
            }
          }}
            style={{ marginLeft: "auto", height: "24px", padding: "0 10px", background: "transparent", border: `1px solid ${T.border2}`, borderRadius: T.r6, color: T.textMuted, fontSize: "11px", cursor: "pointer", fontFamily: T.fontUI, whiteSpace: "nowrap", flexShrink: 0 }}
            onMouseEnter={(e) => { e.currentTarget.style.color = "#ef4444"; e.currentTarget.style.borderColor = "#ef444466"; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = T.textMuted; e.currentTarget.style.borderColor = T.border2; }}>
            ✕ Clear canvas
          </button>
        )}
      </div>

      {/* Canvas area */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden", position: "relative" }}>
        <ComponentPalette
          selected={selected}
          setSelected={setSelected}
          onAdd={addNode}
          customBlocks={customBlocks}
          onCreateCustomBlock={() => setIsCustomBlockOpen(true)}
          onDeleteCustomBlock={handleDeleteCustomBlock}
        />
        <div style={{ flex: 1, position: "relative" }}>
          <ReactFlow
            nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
            onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
            onNodesDelete={onNodesDelete} onEdgesDelete={onEdgesDelete}
            isValidConnection={isValidConnection} onConnect={onConnect} onInit={setRfInstance} fitView
            onEdgeDoubleClick={onEdgeDoubleClick}
            connectionLineType="smoothstep"
            defaultEdgeOptions={{ type: "smoothstep", animated: false, style: { strokeWidth: 1.5, stroke: `${T.blue}cc` } }}>
            <Background color={T.border1} gap={24} variant="dots" style={{ opacity: 0.35 }} />
          </ReactFlow>
        </div>
      </div>

      {/* Bottom panel */}
      <BottomPanel
        showBottomPanel={showBottomPanel} setShowBottomPanel={setShowBottomPanel}
        bottomPanelHeight={bottomPanelHeight} setBottomPanelHeight={setBottomPanelHeight}
        activeTab={activeTab} setActiveTab={setActiveTab}
        verilogFiles={verilogFiles} activeRtlFile={activeRtlFile} setActiveRtlFile={setActiveRtlFile}
        testbenchCode={testbenchCode}
        tbSteps={tbSteps} setTbSteps={setTbSteps}
        tbConfig={tbConfig} updateTbConfig={updateTbConfig} tbConfigDirty={tbConfigDirty}
        nodes={nodes}
        drcLogs={drcLogs}
        verifyHistory={verifyHistory} verifyLoading={verifyLoading} verifyAutoLoading={verifyAutoLoading}
        verifyExpanded={verifyExpanded} setVerifyExpanded={setVerifyExpanded}
        verifyRandomWarning={verifyRandomWarning} setVerifyRandomWarning={setVerifyRandomWarning}
        verifyIntent={verifyIntent} setVerifyIntent={setVerifyIntent}
        runVerification={runVerification} runAutoVerification={runAutoVerification}
        setCurrentPage={setCurrentPage}
      />

      {/* Waveform viewer */}
      {showWaveform && simulationResult && (
        <WaveformViewer data={simulationResult} waveformHeight={waveformHeight} setWaveformHeight={setWaveformHeight} />
      )}

      {/* AI Sidebar */}
      <AiSidebar
        isOpen={isAiOpen} onClose={() => setIsAiOpen(false)}
        chatHistory={chatHistory} setChatHistory={setChatHistory}
        promptValue={promptValue} setPromptValue={setPromptValue}
        aiLoading={aiLoading} setAiLoading={setAiLoading}
        aiMode={aiMode} setAiMode={setAiMode}
        nodes={nodes} edges={edges}
        hydrateNode={hydrateNode} setNodes={setNodes} setEdges={setEdges}
       
        byokKey={byokKey}
        _authHeaders={_authHeaders}
        setVerilogFiles={setVerilogFiles}
        setActiveRtlFile={setActiveRtlFile}
        setRtlReady={setRtlReady}
        setCanonicalIR={setCanonicalIR}
      />

      {/* Modals */}
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} handleSignIn={handleSignIn} />
      <OnboardingModal showOnboarding={showOnboarding} onboardingData={onboardingData} setOnboardingData={setOnboardingData} onboardingSubmitting={onboardingSubmitting} setOnboardingSubmitting={setOnboardingSubmitting} user={user} setShowOnboarding={setShowOnboarding} />
      <CustomBlockModal
        isOpen={isCustomBlockOpen}
        onClose={() => setIsCustomBlockOpen(false)}
        onBlockSaved={(newBlock) => {
          setCustomBlocks(prev => [newBlock, ...prev]);
          showToast(`"${newBlock.name}" saved to My Blocks`, "success");
        }}
        _authHeaders={_authHeaders}
        API_BASE={API_BASE}
      />
      <ByokModal isOpen={isByokOpen} onClose={() => setIsByokOpen(false)} byokKey={byokKey} setByokKey={setByokKey} byokProvider={byokProvider} setByokProvider={setByokProvider} byokModel={byokModel} setByokModel={setByokModel} />
      <FeedbackModal isFeedbackOpen={isFeedbackOpen} setIsFeedbackOpen={setIsFeedbackOpen} feedbackRating={feedbackRating} setFeedbackRating={setFeedbackRating} feedbackText={feedbackText} setFeedbackText={setFeedbackText} feedbackTrigger={feedbackTrigger} feedbackSubmitting={feedbackSubmitting} setFeedbackSubmitting={setFeedbackSubmitting} feedbackWhatBuilding={feedbackWhatBuilding} setFeedbackWhatBuilding={setFeedbackWhatBuilding} feedbackAiAccuracy={feedbackAiAccuracy} setFeedbackAiAccuracy={setFeedbackAiAccuracy} feedbackBlockers={feedbackBlockers} setFeedbackBlockers={setFeedbackBlockers} feedbackWouldPay={feedbackWouldPay} setFeedbackWouldPay={setFeedbackWouldPay} user={user} showToast={showToast} />

      {/* Toast */}
      {toast && (
        <div style={{ position: "fixed", bottom: "28px", left: "50%", transform: "translateX(-50%)", background: toast.type === "success" ? `${T.green}22` : toast.type === "error" ? `${T.red}22` : `${T.blue}22`, border: `1px solid ${toast.type === "success" ? T.green : toast.type === "error" ? T.red : T.blue}66`, borderRadius: T.r8, padding: "10px 20px", fontSize: "18px", fontWeight: "500", color: toast.type === "success" ? T.green : toast.type === "error" ? T.red : T.blue, fontFamily: T.fontUI, zIndex: 9999, boxShadow: "0 8px 32px rgba(0,0,0,0.4)", backdropFilter: "blur(8px)", whiteSpace: "nowrap", animation: "fade-up 0.2s ease both" }}>
          {toast.type === "success" ? "✓  " : toast.type === "error" ? "✕  " : ""}
          {toast.msg}
        </div>
      )}
    </div>
  );
}