import React, { useState, useEffect, useRef } from "react";
import { T } from "../constants";

const WaveformViewer = ({ data, waveformHeight, setWaveformHeight }) => {
  const canvasRef  = useRef(null);
  const overlayRef = useRef(null);
  const [cursorTime, setCursorTime] = useState(null);
  const [markerTime, setMarkerTime] = useState(null);
  const [sigOrder,   setSigOrder]   = useState(null);
  const [hiddenSigs, setHiddenSigs] = useState(new Set());
  const [pinnedSigs, setPinnedSigs] = useState(new Set());
  const [dragIdx,    setDragIdx]    = useState(null);
  const [dragOver,   setDragOver]   = useState(null);
  const [zoomLevel,  setZoomLevel]  = useState(1.0);

  const allRealSignals = data?.waveform?.signals?.filter(
    (s) => s.values.length > 0 && !s.name.includes("WIDTH")
  ) || [];

  const orderedSignals = (() => {
    const base = sigOrder
      ? sigOrder.map((name) => allRealSignals.find((s) => s.name === name)).filter(Boolean)
      : allRealSignals;
    const pinned = base.filter((s) => pinnedSigs.has(s.name));
    const rest   = base.filter((s) => !pinnedSigs.has(s.name));
    return [...pinned, ...rest];
  })();

  const visibleSignals = orderedSignals.filter((s) => !hiddenSigs.has(s.name));

  useEffect(() => {
    if (!data?.waveform) return;
    const names = data.waveform.signals
      .filter((s) => s.values.length > 0 && !s.name.includes("WIDTH"))
      .map((s) => s.name);
    setSigOrder(names);
    setHiddenSigs(new Set());
    setPinnedSigs(new Set());
  }, [data]);

  const toggleHide = (name) =>
    setHiddenSigs((prev) => { const n = new Set(prev); n.has(name) ? n.delete(name) : n.add(name); return n; });
  const togglePin = (name) =>
    setPinnedSigs((prev) => { const n = new Set(prev); n.has(name) ? n.delete(name) : n.add(name); return n; });
  const handleDragStart = (e, idx) => { setDragIdx(idx); e.dataTransfer.effectAllowed = "move"; };
  const handleDragOver  = (e, idx) => { e.preventDefault(); setDragOver(idx); };
  const handleDrop      = (e, dropIdx) => {
    e.preventDefault();
    if (dragIdx === null || dragIdx === dropIdx) { setDragIdx(null); setDragOver(null); return; }
    const names = visibleSignals.map((s) => s.name);
    const dragged = names.splice(dragIdx, 1)[0];
    names.splice(dropIdx, 0, dragged);
    setSigOrder((prev) => {
      const allNames = prev || allRealSignals.map((s) => s.name);
      const result = []; let vi = 0;
      for (const n of allNames) {
        if (!hiddenSigs.has(n)) result.push(names[vi++]);
        else result.push(n);
      }
      return result;
    });
    setDragIdx(null); setDragOver(null);
  };

  useEffect(() => {
    if (!data || !data.waveform || !canvasRef.current) return;
    if (visibleSignals.length === 0) return;

    const maxTime = Math.max(...visibleSignals.flatMap((s) => s.values.map((v) => v.time)), 1000);
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const rowHeight = 40;
    const waveH  = 26;
    const yTop   = 6;
    const timeScale = (width - 20) / maxTime;

    ctx.fillStyle = T.bg0;
    ctx.fillRect(0, 0, width, canvas.height);

    const gridStep = Math.pow(10, Math.floor(Math.log10(maxTime / 8)));
    ctx.strokeStyle = T.border1;
    ctx.lineWidth = 0.5;
    for (let t = 0; t <= maxTime; t += gridStep) {
      const x = 10 + t * timeScale;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
      ctx.fillStyle = T.textMuted;
      ctx.font = `8px ${T.fontMono}`;
      ctx.fillText(t, x + 2, 10);
    }

    visibleSignals.forEach((signal, idx) => {
      const rowY = idx * rowHeight;
      const hiY  = rowY + yTop;
      const loY  = rowY + yTop + waveH;
      const midY = rowY + yTop + waveH / 2;

      const strokeColor =
        signal.name.toLowerCase().includes("clk") ? T.sigClock :
        signal.name.toLowerCase().includes("rst") ? T.sigReset :
        signal.width > 1 ? T.cyan : T.green;

      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 1.5;
      const vals = signal.values;

      if (signal.width === 1) {
        ctx.beginPath();
        let lastY = vals[0].value === "1" ? hiY : loY;
        ctx.moveTo(10, lastY);
        for (let i = 0; i < vals.length; i++) {
          const x   = 10 + vals[i].time * timeScale;
          const isH = vals[i].value === "1";
          const newY = isH ? hiY : loY;
          ctx.lineTo(x, lastY);
          ctx.lineTo(x, newY);
          lastY = newY;
        }
        ctx.lineTo(10 + maxTime * timeScale, lastY);
        ctx.stroke();
      } else {
        for (let i = 0; i < vals.length; i++) {
          const x0    = 10 + vals[i].time * timeScale;
          const x1    = i + 1 < vals.length ? 10 + vals[i + 1].time * timeScale : 10 + maxTime * timeScale;
          const w     = Math.max(x1 - x0, 2);
          const slant = Math.min(3, w / 4);
          ctx.beginPath();
          ctx.moveTo(x0, midY);
          ctx.lineTo(x0 + slant, hiY);
          ctx.lineTo(x1 - slant, hiY);
          ctx.lineTo(x1, midY);
          ctx.lineTo(x1 - slant, loY);
          ctx.lineTo(x0 + slant, loY);
          ctx.closePath();
          ctx.stroke();
          const raw = vals[i].value;
          let displayVal = /^[01]+$/.test(raw) ? parseInt(raw, 2).toString() : raw;
          const labelX = x0 + slant + 3;
          const labelW = w - slant * 2 - 6;
          if (labelW > 10) {
            ctx.fillStyle = strokeColor;
            ctx.font = `9px ${T.fontMono}`;
            ctx.save();
            ctx.beginPath();
            ctx.rect(x0 + slant, hiY, labelW + 6, waveH);
            ctx.clip();
            ctx.fillText(displayVal, labelX, midY + 3);
            ctx.restore();
          }
        }
      }

      ctx.strokeStyle = T.border0;
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(0,     rowY + rowHeight - 0.5);
      ctx.lineTo(width, rowY + rowHeight - 0.5);
      ctx.stroke();
    });
  }, [data, visibleSignals, zoomLevel]);

  useEffect(() => {
    if (!overlayRef.current || !data?.waveform) return;
    const maxTime = Math.max(...visibleSignals.flatMap((s) => s.values.map((v) => v.time)), 1000);
    const oc  = overlayRef.current;
    const ctx = oc.getContext("2d");
    ctx.clearRect(0, 0, oc.width, oc.height);
    if (cursorTime === null) return;
    const x = 10 + (cursorTime / maxTime) * (oc.width - 20);
    ctx.strokeStyle = `${T.amber}cc`;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, oc.height); ctx.stroke();
    ctx.setLineDash([]);
    const label = `${cursorTime} ns`;
    ctx.font = `10px 'JetBrains Mono', monospace`;
    const tw = ctx.measureText(label).width;
    const bx = Math.min(x + 4, oc.width - tw - 10);
    ctx.fillStyle = `${T.bg3}f0`;
    ctx.strokeStyle = `${T.amber}88`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(bx, 4, tw + 8, 16, 3);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = T.amber;
    ctx.fillText(label, bx + 4, 15);
    if (markerTime !== null && markerTime !== cursorTime) {
      const mx = 10 + (markerTime / maxTime) * (oc.width - 20);
      ctx.strokeStyle = `${T.cyan}99`;
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 4]);
      ctx.beginPath(); ctx.moveTo(mx, 0); ctx.lineTo(mx, oc.height); ctx.stroke();
      ctx.setLineDash([]);
      const delta = Math.abs(cursorTime - markerTime);
      const deltaLabel = `Δ${delta} ns`;
      const midX = (x + mx) / 2;
      const dtw  = ctx.measureText(deltaLabel).width;
      ctx.fillStyle = `${T.bg3}f0`;
      ctx.strokeStyle = `${T.cyan}88`;
      ctx.beginPath();
      ctx.roundRect(midX - dtw / 2 - 4, 22, dtw + 8, 16, 3);
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = T.cyan;
      ctx.fillText(deltaLabel, midX - dtw / 2, 33);
    }
  }, [cursorTime, markerTime, data, visibleSignals]);

  if (!data || !data.waveform) return null;

  const { timescale } = data.waveform;
  const maxTime = Math.max(
    ...visibleSignals.flatMap((s) => s.values.length > 0 ? s.values.map((v) => v.time) : [0]),
    1000
  );

  return (
    <div style={{ position: "fixed", bottom: 0, left: 0, right: 0, height: `${waveformHeight}px`, background: T.bg1, borderTop: `1px solid ${T.border1}`, boxShadow: "0 -8px 40px rgba(0,0,0,0.5)", display: "flex", flexDirection: "column", zIndex: 1000 }}>
      {/* Drag-to-resize handle */}
      <div
        onMouseDown={(e) => {
          e.preventDefault();
          const startY = e.clientY;
          const startH = waveformHeight;
          const onMove = (ev) => setWaveformHeight(Math.max(200, Math.min(700, startH - (ev.clientY - startY))));
          const onUp   = () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
          window.addEventListener("mousemove", onMove);
          window.addEventListener("mouseup", onUp);
        }}
        style={{ position: "absolute", top: 0, left: 0, right: 0, height: "5px", cursor: "ns-resize", zIndex: 10, background: "transparent" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(59,158,255,0.2)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      />

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", height: "38px", flexShrink: 0, background: T.bg2, borderBottom: `1px solid ${T.border0}`, padding: "0 14px", gap: "12px" }}>
        <span style={{ fontSize: "11px", fontWeight: "600", color: T.textPrimary, fontFamily: T.fontUI }}>Waveform</span>
        <span style={{ fontSize: "10px", color: T.textMuted, fontFamily: T.fontMono }}>
          {timescale} · {maxTime.toLocaleString()} units · {visibleSignals.length}/{allRealSignals.length} signals
        </span>
        {hiddenSigs.size > 0 && (
          <span style={{ fontSize: "10px", color: T.amber, fontFamily: T.fontUI, cursor: "pointer" }} onClick={() => setHiddenSigs(new Set())}>
            {hiddenSigs.size} hidden · show all
          </span>
        )}
        <div style={{ flex: 1 }} />
        <button onClick={() => setZoomLevel((z) => Math.max(0.5, +(z - 0.25).toFixed(2)))}
          style={{ background: T.bg3, border: `1px solid ${T.border2}`, borderRadius: T.r4, color: T.textSecondary, fontSize: "13px", width: "24px", height: "24px", cursor: "pointer", lineHeight: 1 }}>−</button>
        <span style={{ fontSize: "10px", color: T.textMuted, fontFamily: T.fontMono, minWidth: "34px", textAlign: "center" }}>{zoomLevel.toFixed(1)}x</span>
        <button onClick={() => setZoomLevel((z) => Math.min(4.0, +(z + 0.25).toFixed(2)))}
          style={{ background: T.bg3, border: `1px solid ${T.border2}`, borderRadius: T.r4, color: T.textSecondary, fontSize: "13px", width: "24px", height: "24px", cursor: "pointer", lineHeight: 1 }}>+</button>
        <a href={"data:text/plain;charset=utf-8," + encodeURIComponent(data.vcd_raw)} download="simulation.vcd"
          style={{ display: "inline-flex", alignItems: "center", gap: "5px", height: "26px", padding: "0 10px", background: `${T.blue}18`, border: `1px solid ${T.blue}44`, borderRadius: T.r6, color: T.blue, fontSize: "11px", textDecoration: "none", fontFamily: T.fontUI }}>
          ↓ VCD
        </a>
        <button onClick={() => setWaveformHeight(0)}
          style={{ background: "transparent", border: "none", color: T.textMuted, fontSize: "16px", cursor: "pointer", padding: "0 4px", lineHeight: 1, transition: "color 0.12s" }}
          onMouseEnter={(e) => (e.currentTarget.style.color = T.red)}
          onMouseLeave={(e) => (e.currentTarget.style.color = T.textMuted)}>×</button>
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Signal list panel */}
        <div style={{ width: "170px", flexShrink: 0, background: T.bg2, borderRight: `1px solid ${T.border0}`, overflowY: "auto", paddingTop: "28px" }}>
          {visibleSignals.map((sig, i) => {
            const isPinned = pinnedSigs.has(sig.name);
            const sigColor = sig.name.toLowerCase().includes("clk") ? T.sigClock : sig.name.toLowerCase().includes("rst") ? T.sigReset : sig.width > 1 ? T.cyan : T.textSecondary;
            return (
              <div key={sig.name} draggable
                onDragStart={(e) => handleDragStart(e, i)}
                onDragOver={(e) => handleDragOver(e, i)}
                onDrop={(e) => handleDrop(e, i)}
                onDragEnd={() => { setDragIdx(null); setDragOver(null); }}
                style={{ display: "flex", alignItems: "center", height: "40px", padding: "0 6px", borderBottom: `1px solid ${T.border0}`, background: dragOver === i ? `${T.blue}18` : isPinned ? `${T.violet}0f` : "transparent", cursor: "grab", gap: "4px", borderLeft: isPinned ? `2px solid ${T.violet}88` : "2px solid transparent" }}>
                <span style={{ color: T.border2, fontSize: "10px", flexShrink: 0, userSelect: "none" }}>⠿</span>
                <span style={{ fontFamily: T.fontMono, fontSize: "10px", color: sigColor, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {sig.name}{sig.width > 1 && <span style={{ color: T.textMuted, fontSize: "9px" }}> [{sig.width - 1}:0]</span>}
                </span>
                <button onClick={() => togglePin(sig.name)} title={isPinned ? "Unpin" : "Pin to top"}
                  style={{ background: "none", border: "none", cursor: "pointer", padding: "0 2px", color: isPinned ? T.violet : T.border2, fontSize: "9px", flexShrink: 0, lineHeight: 1 }}>📌</button>
                <button onClick={() => toggleHide(sig.name)} title="Hide signal"
                  style={{ background: "none", border: "none", cursor: "pointer", padding: "0 2px", color: T.border2, fontSize: "10px", flexShrink: 0, lineHeight: 1 }}>✕</button>
              </div>
            );
          })}
          {hiddenSigs.size > 0 && (
            <div style={{ padding: "6px 8px", borderTop: `1px solid ${T.border1}` }}>
              <div style={{ fontSize: "9px", color: T.textMuted, fontFamily: T.fontUI, marginBottom: "4px" }}>HIDDEN ({hiddenSigs.size})</div>
              {orderedSignals.filter((s) => hiddenSigs.has(s.name)).map((sig) => (
                <div key={sig.name} style={{ display: "flex", alignItems: "center", height: "24px", padding: "0 4px", gap: "4px", opacity: 0.5 }}>
                  <span style={{ fontFamily: T.fontMono, fontSize: "9px", color: T.textMuted, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{sig.name}</span>
                  <button onClick={() => toggleHide(sig.name)} title="Show signal"
                    style={{ background: "none", border: "none", cursor: "pointer", color: T.textMuted, fontSize: "9px", padding: "0 2px" }}>👁</button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Canvas area */}
        <div style={{ flex: 1, overflowX: "auto", overflowY: "hidden", position: "relative" }}>
          {/* Time ruler */}
          <div style={{ height: "28px", background: T.bg3, borderBottom: `1px solid ${T.border0}`, position: "sticky", top: 0, display: "flex", alignItems: "center", padding: "0 10px", gap: "14px", fontSize: "9px", color: T.textMuted, fontFamily: T.fontMono, letterSpacing: "0.5px" }}>
            <span>TIME SCALE: {timescale}</span>
            {cursorTime !== null && <span style={{ color: T.amber }}>cursor: {cursorTime} ns</span>}
            {markerTime !== null && cursorTime !== null && markerTime !== cursorTime && (
              <span style={{ color: T.cyan }}>&#x394;= {Math.abs(cursorTime - markerTime)} ns</span>
            )}
            {(cursorTime !== null || markerTime !== null) && (
              <button onClick={() => { setCursorTime(null); setMarkerTime(null); }}
                style={{ background: "none", border: "none", color: T.textMuted, cursor: "pointer", fontSize: "9px", padding: "0 4px" }}>clear</button>
            )}
          </div>

          {/* Stacked canvas layers */}
          <div style={{ position: "relative", width: `${Math.round(1600 * zoomLevel)}px`, height: `${visibleSignals.length * 40}px` }}>
            <canvas ref={canvasRef} width={Math.round(1600 * zoomLevel)} height={visibleSignals.length * 40}
              style={{ display: "block", imageRendering: "crisp-edges", position: "absolute", top: 0, left: 0 }} />
            <canvas ref={overlayRef} width={Math.round(1600 * zoomLevel)} height={visibleSignals.length * 40}
              style={{ display: "block", position: "absolute", top: 0, left: 0, cursor: "crosshair" }}
              onMouseMove={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                const px = e.clientX - rect.left;
                const canvasW = Math.round(1600 * zoomLevel);
                const t = Math.round(((px - 10) / (canvasW - 20)) * maxTime);
                setCursorTime(Math.max(0, Math.min(t, maxTime)));
              }}
              onMouseLeave={() => { if (markerTime === null) setCursorTime(null); }}
              onClick={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                const px = e.clientX - rect.left;
                const canvasW = Math.round(1600 * zoomLevel);
                const t = Math.round(((px - 10) / (canvasW - 20)) * maxTime);
                const snapped = Math.max(0, Math.min(t, maxTime));
                setMarkerTime((prev) => prev === snapped ? null : snapped);
              }}
            />
          </div>
        </div>
      </div>

      {/* Console strip */}
      {data.console_output && (
        <div style={{ height: "60px", flexShrink: 0, background: T.bg0, borderTop: `1px solid ${T.border0}`, padding: "6px 14px", overflowY: "auto" }}>
          <pre style={{ margin: 0, fontFamily: T.fontMono, fontSize: "10px", color: T.textSecondary, lineHeight: "1.5" }}>{data.console_output}</pre>
        </div>
      )}
    </div>
  );
};

export default WaveformViewer;
