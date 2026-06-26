import React from "react";
import { T } from "../constants";
import { COMPONENT_CATEGORIES } from "../componentCategories";

const ComponentPalette = ({ selected, setSelected, onAdd, customBlocks = [], onCreateCustomBlock, onDeleteCustomBlock }) => {
  const [collapsed, setCollapsed] = React.useState({});
  const [myBlocksCollapsed, setMyBlocksCollapsed] = React.useState(false);
  const [sidebarOpen, setSidebarOpen] = React.useState(true);

  const toggle = (label) =>
    setCollapsed((prev) => ({ ...prev, [label]: !prev[label] }));

  const MY_BLOCKS_COLOR = "#a78bfa"; 

  return (
    <div
      style={{
        width: sidebarOpen ? "240px" : "40px",
        minWidth: sidebarOpen ? "240px" : "40px",
        background: T.bg2,
        borderRight: `1px solid ${T.border0}`,
        display: "flex",
        flexDirection: "column",
        overflowY: sidebarOpen ? "auto" : "hidden",
        zIndex: 5,
        transition: "width 0.2s ease, min-width 0.2s ease",
        position: "relative",
      }}
    >
      {/* Toggle button */}
      <button
        onClick={() => setSidebarOpen((o) => !o)}
        style={{
          position: "absolute",
          top: "10px",
          right: sidebarOpen ? "10px" : "6px",
          width: "26px",
          height: "26px",
          borderRadius: "6px",
          background: T.bg4,
          border: `1px solid ${T.border2}`,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: T.textSecondary,
          zIndex: 10,
          transition: "all 0.15s",
          flexShrink: 0,
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = T.textPrimary;
          e.currentTarget.style.borderColor = T.blue + "44";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = T.textMuted;
          e.currentTarget.style.borderColor = T.border2;
        }}
        title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <line x1="2" y1="4"  x2="14" y2="4"  stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="2" y1="8"  x2="14" y2="8"  stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="2" y1="12" x2="14" y2="12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>

      {sidebarOpen && (
        <>
          {/* Header */}
          <div
            style={{
              padding: "12px 14px 10px",
              paddingRight: "32px",
              borderBottom: `1px solid ${T.border0}`,
              fontSize: "14px",
              fontWeight: "700",
              letterSpacing: "1.5px",
              color: T.textMuted,
              textTransform: "uppercase",
              fontFamily: T.fontMono,
              flexShrink: 0,
            }}
          >
            Blocks
          </div>

          {/* Add button */}
          <div style={{ padding: "8px 10px 4px", flexShrink: 0 }}>
            <button
              onClick={onAdd}
              style={{
                width: "100%",
                padding: "8px",
                background: selected ? `${T.blue}22` : T.bg4,
                color: selected ? T.blue : T.textSecondary,
                border: `1px solid ${selected ? T.blue + "44" : T.border2}`,
                borderRadius: T.r6,
                cursor: "pointer",
                fontSize: "13px",
                fontWeight: "600",
                letterSpacing: "0.2px",
                fontFamily: T.fontUI,
                transition: "all 0.15s ease",
              }}
            >
              + {selected?.label || "Add Block"}
            </button>
          </div>

          {/* ── My Blocks category ── */}
          <div style={{ borderBottom: `1px solid ${T.border0}` }}>
            <button
              onClick={() => setMyBlocksCollapsed(c => !c)}
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "8px 14px",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                color: MY_BLOCKS_COLOR,
                fontSize: "11px",
                fontWeight: "800",
                letterSpacing: "1px",
                textTransform: "uppercase",
                fontFamily: T.fontUI,
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: MY_BLOCKS_COLOR, display: "inline-block" }} />
                My Blocks
                {customBlocks.length > 0 && (
                  <span style={{
                    fontSize: "9px", fontWeight: "700",
                    background: `${MY_BLOCKS_COLOR}22`,
                    border: `1px solid ${MY_BLOCKS_COLOR}44`,
                    borderRadius: "10px", padding: "1px 5px",
                    color: MY_BLOCKS_COLOR,
                  }}>{customBlocks.length}</span>
                )}
              </span>
              <span style={{
                fontSize: "12px", color: T.textMuted,
                transform: myBlocksCollapsed ? "rotate(-90deg)" : "rotate(0deg)",
                transition: "transform 0.15s ease", display: "inline-block",
              }}>▾</span>
            </button>

            {!myBlocksCollapsed && (
              <div style={{ paddingBottom: "4px" }}>
                {/* Create new custom block button */}
                <button
                  onClick={onCreateCustomBlock}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    padding: "6px 14px 6px 28px",
                    background: "transparent",
                    border: "none",
                    borderLeft: "2px solid transparent",
                    color: MY_BLOCKS_COLOR,
                    fontSize: "12px",
                    fontWeight: "600",
                    cursor: "pointer",
                    fontFamily: T.fontUI,
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    opacity: 0.8,
                  }}
                  onMouseEnter={e => { e.currentTarget.style.opacity = "1"; e.currentTarget.style.background = T.bg5; }}
                  onMouseLeave={e => { e.currentTarget.style.opacity = "0.8"; e.currentTarget.style.background = "transparent"; }}
                >
                  <span style={{ fontSize: "14px" }}>＋</span> New custom block...
                </button>

                {/* Saved custom blocks */}
                {customBlocks.length === 0 && (
                  <div style={{
                    padding: "8px 14px 8px 28px",
                    fontSize: "11px", color: T.textMuted,
                    fontFamily: T.fontUI, lineHeight: "1.4",
                  }}>
                    No custom blocks yet. Create one above.
                  </div>
                )}
                {customBlocks.map((block) => {
                  const isSelected = selected?.customBlockId === block.id;
                  const customItem = {
                    label: block.name,
                    type: "custom_block",
                    customBlockId: block.id,
                    customName: block.name,
                    customPorts: block.ports,
                    customVerilog:   block.verilog,
                    customBlockType: block.block_type || "",
                    description:     block.description,
                  };
                  return (
                    <div
                      key={block.id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        padding: "0 8px 0 28px",
                      }}
                    >
                      <button
                        onClick={() => setSelected(customItem)}
                        onDoubleClick={() => { setSelected(customItem); onAdd(); }}
                        title={block.description || block.name}
                        style={{
                          flex: 1,
                          textAlign: "left",
                          padding: "6px 4px",
                          background: isSelected ? `${MY_BLOCKS_COLOR}15` : "transparent",
                          border: "none",
                          borderLeft: isSelected ? `2px solid ${MY_BLOCKS_COLOR}` : "2px solid transparent",
                          marginLeft: isSelected ? "-2px" : "0",
                          color: isSelected ? MY_BLOCKS_COLOR : T.textSecondary,
                          fontSize: "13px",
                          fontWeight: isSelected ? "600" : "400",
                          cursor: "pointer",
                          transition: "all 0.1s ease",
                          fontFamily: T.fontUI,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                        onMouseEnter={(e) => {
                          if (!isSelected) {
                            e.currentTarget.style.color = T.textPrimary;
                            e.currentTarget.style.background = T.bg5;
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (!isSelected) {
                            e.currentTarget.style.color = T.textSecondary;
                            e.currentTarget.style.background = "transparent";
                          }
                        }}
                      >
                        {block.name}
                      </button>
                      {/* Delete button */}
                      <button
                        onClick={(e) => { e.stopPropagation(); onDeleteCustomBlock(block.id); }}
                        title="Delete block"
                        style={{
                          background: "none", border: "none",
                          cursor: "pointer", color: T.textMuted,
                          fontSize: "12px", padding: "4px",
                          flexShrink: 0, opacity: 0,
                          transition: "opacity 0.1s",
                        }}
                        onMouseEnter={e => { e.currentTarget.style.opacity = "1"; e.currentTarget.style.color = T.red; }}
                        onMouseLeave={e => { e.currentTarget.style.opacity = "0"; e.currentTarget.style.color = T.textMuted; }}
                      >
                        ✕
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* ── Built-in categories ── */}
          {COMPONENT_CATEGORIES.map((cat) => (
            <div key={cat.label} style={{ borderBottom: `1px solid ${T.border0}` }}>
              <button
                onClick={() => toggle(cat.label)}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "8px 14px",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  color: cat.color,
                  fontSize: "11px",
                  fontWeight: "800",
                  letterSpacing: "1px",
                  textTransform: "uppercase",
                  fontFamily: T.fontUI,
                }}
              >
                <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: cat.color, display: "inline-block" }} />
                  {cat.label}
                </span>
                <span
                  style={{
                    fontSize: "12px",
                    color: T.textMuted,
                    transform: collapsed[cat.label] ? "rotate(-90deg)" : "rotate(0deg)",
                    transition: "transform 0.15s ease",
                    display: "inline-block",
                  }}
                >
                  ▾
                </span>
              </button>

              {!collapsed[cat.label] && (
                <div style={{ paddingBottom: "4px" }}>
                  {cat.items.map((item) => {
                    const isSelected = selected?.label === item.label;
                    return (
                      <button
                        key={item.label}
                        onClick={() => setSelected(item)}
                        onDoubleClick={() => { setSelected(item); onAdd(); }}
                        title="Click to select · Double-click to add"
                        style={{
                          width: "100%",
                          textAlign: "left",
                          padding: "6px 14px 6px 28px",
                          background: isSelected ? `${cat.color}15` : "transparent",
                          border: "none",
                          borderLeft: isSelected ? `2px solid ${cat.color}` : "2px solid transparent",
                          color: isSelected ? cat.color : T.textSecondary,
                          fontSize: "13px",
                          fontWeight: isSelected ? "600" : "400",
                          cursor: "pointer",
                          transition: "all 0.1s ease",
                          fontFamily: T.fontUI,
                        }}
                        onMouseEnter={(e) => {
                          if (!isSelected) {
                            e.currentTarget.style.color = T.textPrimary;
                            e.currentTarget.style.background = T.bg5;
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (!isSelected) {
                            e.currentTarget.style.color = T.textSecondary;
                            e.currentTarget.style.background = "transparent";
                          }
                        }}
                      >
                        {item.label}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          ))}

          <div
            style={{
              marginTop: "auto",
              padding: "10px 14px",
              fontSize: "13px",
              color: T.textMuted,
              lineHeight: "1.6",
              borderTop: `1px solid ${T.border0}`,
              fontFamily: T.fontUI,
              flexShrink: 0,
            }}
          >
            Click to select · Double-click to add
          </div>
        </>
      )}
    </div>
  );
};

export default ComponentPalette;