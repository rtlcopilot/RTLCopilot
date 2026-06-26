import React from "react";
import { T } from "../constants";
import { API_BASE } from "../config";

export const AuthModal = ({ isOpen, onClose, handleSignIn }) => {
  if (!isOpen) return null;
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(5,8,15,0.9)", backdropFilter: "blur(10px)", zIndex: 3000, display: "flex", justifyContent: "center", alignItems: "center" }}>
      <div style={{ background: T.bg3, border: `1px solid ${T.border1}`, borderRadius: T.r12, width: "400px", padding: "32px", boxShadow: "0 24px 60px rgba(0,0,0,0.7)" }}>
        <div style={{ textAlign: "center", marginBottom: "24px" }}>
          <div style={{ fontSize: "22px", fontWeight: "700", color: T.textPrimary, marginBottom: "8px" }}>Sign in to RTL Copilot</div>
          <div style={{ fontSize: "13px", color: T.textMuted }}>Save your designs to the cloud and access them anywhere</div>
        </div>
        <button onClick={handleSignIn}
          style={{ width: "100%", padding: "12px", background: `linear-gradient(135deg, ${T.blue}22, ${T.violet}22)`, border: `1px solid ${T.blue}55`, borderRadius: T.r8, color: T.textPrimary, fontSize: "15px", fontWeight: "600", cursor: "pointer", fontFamily: T.fontUI, display: "flex", alignItems: "center", justifyContent: "center", gap: "10px" }}>
          <svg width="18" height="18" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
          Continue with Google
        </button>
        <button onClick={onClose}
          style={{ width: "100%", marginTop: "12px", padding: "10px", background: "transparent", border: `1px solid ${T.border2}`, borderRadius: T.r8, color: T.textMuted, fontSize: "13px", cursor: "pointer", fontFamily: T.fontUI }}>
          Cancel
        </button>
      </div>
    </div>
  );
};

export const OnboardingModal = ({ showOnboarding, onboardingData, setOnboardingData, onboardingSubmitting, setOnboardingSubmitting, user, setShowOnboarding }) => {
  if (!showOnboarding) return null;

  const handleSubmit = async () => {
    setOnboardingSubmitting(true);
    try {
      await fetch(`${API_BASE}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rating: 5,
          text: `Onboarding: name=${onboardingData.name}, org=${onboardingData.org}, title=${onboardingData.jobTitle}, purpose=${onboardingData.purpose}`,
          trigger: "onboarding",
          user_id: user?.id || null,
        }),
      });
      if (user?.id) localStorage.setItem(`rtl_onboarded_${user.id}`, "1");
    } catch (e) {
      console.error(e);
    } finally {
      setOnboardingSubmitting(false);
      setShowOnboarding(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(5,8,15,0.9)", backdropFilter: "blur(10px)", zIndex: 3000, display: "flex", justifyContent: "center", alignItems: "center" }}>
      <div style={{ background: "#111827", border: "1px solid #1c2840", borderRadius: "12px", width: "460px", boxShadow: "0 24px 60px rgba(0,0,0,0.7)" }}>
        <div style={{ padding: "20px 24px 0" }}>
          <div style={{ fontSize: "20px", fontWeight: "700", color: "#d8e4f0", marginBottom: "6px" }}>Welcome to RTL Copilot 👋</div>
          <div style={{ fontSize: "13px", color: "#6b849e", marginBottom: "20px" }}>Quick intro — takes 30 seconds. Helps us build a better tool.</div>
        </div>
        <div style={{ padding: "0 24px 24px", display: "flex", flexDirection: "column", gap: "12px" }}>
          {[
            { label: "Your name", key: "name", placeholder: "e.g. Suchit Tomar" },
            { label: "Organization / College", key: "org", placeholder: "e.g. IIT Bombay / Qualcomm" },
            { label: "Job title / Role", key: "jobTitle", placeholder: "e.g. VLSI Engineer, Student" },
          ].map((field) => (
            <div key={field.key}>
              <div style={{ fontSize: "11px", fontWeight: "600", color: "#6b849e", textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: "5px" }}>{field.label}</div>
              <input value={onboardingData[field.key]}
                onChange={(e) => setOnboardingData((d) => ({ ...d, [field.key]: e.target.value }))}
                placeholder={field.placeholder}
                style={{ width: "100%", padding: "8px 12px", background: "#0d1320", border: "1px solid #243250", borderRadius: "6px", color: "#d8e4f0", fontSize: "13px", fontFamily: "'IBM Plex Sans', sans-serif", outline: "none" }}
                onFocus={(e) => (e.target.style.borderColor = "rgba(59,158,255,0.5)")}
                onBlur={(e) => (e.target.style.borderColor = "#243250")} />
            </div>
          ))}

          <div>
            <div style={{ fontSize: "11px", fontWeight: "600", color: "#6b849e", textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: "8px" }}>What will you use RTL Copilot for?</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {["Learning RTL", "Prototyping", "Teaching", "Research", "Production design", "Just exploring"].map((opt) => {
                const isSelected = onboardingData.purpose.includes(opt);
                return (
                  <button key={opt}
                    onClick={() => setOnboardingData((d) => ({
                      ...d,
                      purpose: isSelected
                        ? d.purpose.replace(opt, "").replace(/,\s*,/, ",").replace(/^,|,$/, "").trim()
                        : d.purpose ? `${d.purpose}, ${opt}` : opt,
                    }))}
                    style={{ padding: "5px 12px", borderRadius: "100px", fontSize: "12px", cursor: "pointer", fontFamily: "'IBM Plex Sans', sans-serif", background: isSelected ? "rgba(59,158,255,0.15)" : "#0d1320", border: `1px solid ${isSelected ? "rgba(59,158,255,0.5)" : "#243250"}`, color: isSelected ? "#3b9eff" : "#6b849e", transition: "all 0.12s" }}>
                    {opt}
                  </button>
                );
              })}
            </div>
          </div>

          <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
            <button disabled={onboardingSubmitting} onClick={handleSubmit}
              style={{ flex: 1, height: "38px", background: "#3b9eff22", border: "1px solid #3b9eff55", borderRadius: "6px", cursor: onboardingSubmitting ? "not-allowed" : "pointer", fontSize: "13px", fontWeight: "600", color: "#3b9eff", transition: "all 0.15s" }}>
              {onboardingSubmitting ? "Saving…" : "Let's go →"}
            </button>
            <button onClick={() => setShowOnboarding(false)}
              style={{ height: "38px", padding: "0 14px", background: "none", border: "1px solid #1c2840", borderRadius: "6px", cursor: "pointer", fontSize: "12px", color: "#6b849e" }}>
              Skip
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export const FeedbackModal = ({
  isFeedbackOpen, setIsFeedbackOpen,
  feedbackRating, setFeedbackRating,
  feedbackText, setFeedbackText,
  feedbackTrigger,
  feedbackSubmitting, setFeedbackSubmitting,
  feedbackWhatBuilding, setFeedbackWhatBuilding,
  feedbackAiAccuracy, setFeedbackAiAccuracy,
  feedbackBlockers, setFeedbackBlockers,
  feedbackWouldPay, setFeedbackWouldPay,
  user, showToast,
}) => {
  if (!isFeedbackOpen) return null;

  const handleSubmit = async () => {
    setFeedbackSubmitting(true);
    try {
      await fetch(`${API_BASE}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rating: feedbackRating,
          text: [
            feedbackText,
            feedbackWhatBuilding ? `Building: ${feedbackWhatBuilding}` : "",
            feedbackAiAccuracy   ? `AI accuracy: ${feedbackAiAccuracy}` : "",
            feedbackBlockers.length ? `Blockers: ${feedbackBlockers.join(", ")}` : "",
            feedbackWouldPay     ? `Would pay: ${feedbackWouldPay}` : "",
          ].filter(Boolean).join(" | "),
          trigger: feedbackTrigger,
          user_id: user?.id || null,
        }),
      });
      setIsFeedbackOpen(false);
      setFeedbackWhatBuilding(""); setFeedbackAiAccuracy("");
      setFeedbackBlockers([]); setFeedbackWouldPay("");
      showToast("Thanks for your feedback!", "success");
    } catch (e) {
      setIsFeedbackOpen(false);
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(5,8,15,0.85)", backdropFilter: "blur(8px)", zIndex: 3000, display: "flex", justifyContent: "center", alignItems: "center" }}>
      <div style={{ background: T.bg3, border: `1px solid ${T.border1}`, borderRadius: T.r12, width: "440px", padding: "24px", boxShadow: "0 24px 60px rgba(0,0,0,0.7)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div style={{ fontSize: "16px", fontWeight: "700", color: T.textPrimary }}>Quick Feedback</div>
          <button onClick={() => setIsFeedbackOpen(false)} style={{ background: "none", border: "none", color: T.textMuted, fontSize: "18px", cursor: "pointer" }}>×</button>
        </div>

        {/* Star rating */}
        <div style={{ display: "flex", gap: "8px", marginBottom: "14px" }}>
          {[1, 2, 3, 4, 5].map((star) => (
            <button key={star} onClick={() => setFeedbackRating(star)}
              style={{ background: "none", border: "none", cursor: "pointer", fontSize: "24px", color: star <= feedbackRating ? T.amber : T.border2, transition: "color 0.1s" }}>
              ★
            </button>
          ))}
        </div>

        <textarea value={feedbackText} onChange={(e) => setFeedbackText(e.target.value)}
          placeholder="What's working? What could be better?"
          style={{ width: "100%", height: "80px", padding: "10px 12px", background: T.bg2, border: `1px solid ${T.border2}`, borderRadius: T.r6, color: T.textPrimary, fontSize: "13px", fontFamily: T.fontUI, resize: "none", outline: "none", marginBottom: "12px", boxSizing: "border-box" }} />

        <div style={{ display: "flex", gap: "8px" }}>
          <button onClick={handleSubmit} disabled={feedbackRating === 0 || feedbackSubmitting}
            style={{ flex: 1, height: "34px", background: feedbackRating > 0 ? `${T.blue}22` : T.bg2, border: `1px solid ${feedbackRating > 0 ? T.blue + "55" : T.border2}`, borderRadius: T.r6, cursor: feedbackRating > 0 ? "pointer" : "not-allowed", fontSize: "12px", fontWeight: "600", color: feedbackRating > 0 ? T.blue : T.textMuted, transition: "all 0.15s" }}>
            {feedbackSubmitting ? "Sending…" : "Send Feedback"}
          </button>
          <button onClick={() => setIsFeedbackOpen(false)}
            style={{ height: "34px", padding: "0 14px", background: "none", border: `1px solid ${T.border2}`, borderRadius: T.r6, cursor: "pointer", fontSize: "12px", color: T.textMuted }}>
            Skip
          </button>
        </div>
      </div>
    </div>
  );
};

const PROVIDER_MODELS = {
  openai: [
    { value: "gpt-4o-mini",       label: "GPT-4o mini (fast, cheap)"   },
    { value: "gpt-4o",            label: "GPT-4o (most capable)"        },
    { value: "gpt-4-turbo",       label: "GPT-4 Turbo"                  },
  ],
  groq: [
    { value: "llama-3.3-70b-versatile",  label: "Llama 3.3 70B (recommended)" },
    { value: "llama-3.1-8b-instant",     label: "Llama 3.1 8B (fastest)"      },
    { value: "mixtral-8x7b-32768",       label: "Mixtral 8x7B"                },
    { value: "gemma2-9b-it",             label: "Gemma 2 9B"                  },
  ],
  nvidia: [
    { value: "meta/llama-3.3-70b-instruct",   label: "Llama 3.3 70B Instruct (recommended)" },
    { value: "meta/llama-3.1-8b-instruct",    label: "Llama 3.1 8B Instruct (fastest)"      },
    { value: "mistralai/mistral-7b-instruct", label: "Mistral 7B Instruct"                  },
    { value: "google/gemma-2-9b-it",          label: "Gemma 2 9B"                           },
    { value: "microsoft/phi-3-mini-128k-instruct", label: "Phi-3 Mini"                      },
    { value: "deepseek-ai/deepseek-r1",       label: "DeepSeek R1"                          },
    { value: "qwen/qwen2.5-72b-instruct",     label: "Qwen 2.5 72B"                        },
  ],
  local: [
    { value: "custom", label: "Enter model name below" },
  ],
};

const PROVIDER_META = {
  openai: { label: "OpenAI",       keyPlaceholder: "sk-proj-...",   keyHint: <>Get your key at <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer" style={{color:"#60a5fa"}}>platform.openai.com/api-keys</a>. New accounts get free credit.</> },
  groq:   { label: "Groq",         keyPlaceholder: "gsk_...",       keyHint: <>Get a free key at <a href="https://console.groq.com/keys" target="_blank" rel="noreferrer" style={{color:"#60a5fa"}}>console.groq.com/keys</a>. Groq has a generous free tier.</> },
  nvidia: { label: "NVIDIA NIM",   keyPlaceholder: "nvapi-...",     keyHint: <>Get free credits at <a href="https://build.nvidia.com" target="_blank" rel="noreferrer" style={{color:"#60a5fa"}}>build.nvidia.com</a>. Requires phone verification.</> },
  local:  { label: "Local (LM Studio / Ollama)", keyPlaceholder: "none required", keyHint: <>Point LM Studio or Ollama to <strong>localhost:1234</strong>. Enter any value for the key.</> },
};

export const ByokModal = ({ isOpen, onClose, byokKey, setByokKey, byokProvider, setByokProvider, byokModel, setByokModel }) => {
  if (!isOpen) return null;

  const models   = PROVIDER_MODELS[byokProvider] || PROVIDER_MODELS.openai;
  const meta     = PROVIDER_META[byokProvider]   || PROVIDER_META.openai;
  const isSaved  = !!localStorage.getItem("rtl_byok_key");
  const isLocal  = byokProvider === "local";

  const handleProviderChange = (e) => {
    const prov = e.target.value;
    setByokProvider(prov);
    const firstModel = PROVIDER_MODELS[prov]?.[0]?.value || "";
    setByokModel(firstModel === "custom" ? "" : firstModel);
  };

  const handleSave = () => {
    const trimmedKey   = isLocal ? (byokKey.trim() || "local") : byokKey.trim();
    const trimmedModel = byokModel.trim();
    if (!isLocal && !trimmedKey) {
      alert("Please enter an API key.");
      return;
    }
    if (!trimmedModel) {
      alert("Please select or enter a model.");
      return;
    }
    localStorage.setItem("rtl_byok_key",      trimmedKey);
    localStorage.setItem("rtl_byok_provider", byokProvider);
    localStorage.setItem("rtl_byok_model",    trimmedModel);
    setByokKey(trimmedKey);
    onClose();
  };

  const handleClear = () => {
    localStorage.removeItem("rtl_byok_key");
    localStorage.removeItem("rtl_byok_provider");
    localStorage.removeItem("rtl_byok_model");
    setByokKey("");
    setByokProvider("openai");
    setByokModel("");
    onClose();
  };

  const inputStyle = {
    width: "100%", padding: "9px 12px", background: T.bg0,
    border: `1px solid ${T.border2}`, borderRadius: T.r6,
    color: T.textPrimary, fontSize: "13px", fontFamily: T.fontUI,
    outline: "none", boxSizing: "border-box", marginBottom: "14px",
  };
  const labelStyle = {
    display: "block", fontSize: "12px", color: T.textMuted, fontFamily: T.fontUI,
    marginBottom: "6px", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.05em",
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(5,8,15,0.82)", backdropFilter: "blur(8px)", zIndex: 2000, display: "flex", justifyContent: "center", alignItems: "center" }}>
      <div style={{ background: T.bg3, border: `1px solid ${T.border1}`, borderRadius: T.r12, width: "480px", boxShadow: "0 24px 60px rgba(0,0,0,0.6)", overflow: "hidden" }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", background: T.bg2, borderBottom: `1px solid ${T.border0}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{ fontSize: "18px" }}>🔑</span>
            <span style={{ fontSize: "16px", fontWeight: "600", color: T.textPrimary, fontFamily: T.fontUI }}>Use Your Own API Key</span>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: T.textMuted, fontSize: "20px", lineHeight: 1 }}>✕</button>
        </div>

        {/* Body */}
        <div style={{ padding: "20px" }}>
          <p style={{ fontSize: "13px", color: T.textSecondary, fontFamily: T.fontUI, lineHeight: "1.6", marginBottom: "16px" }}>
            Use your own API key and quota instead of purchasing credits. Your key is stored only in your browser.
          </p>

          {isSaved && (
            <div style={{ background: `${T.green}18`, border: `1px solid ${T.green}44`, borderRadius: T.r6, padding: "8px 12px", marginBottom: "14px", fontSize: "12px", color: T.green, fontFamily: T.fontUI }}>
              ✓ API key active — credits will not be deducted for AI features
            </div>
          )}

          {/* Provider dropdown */}
          <label style={labelStyle}>Provider</label>
          <select value={byokProvider} onChange={handleProviderChange}
            style={{ ...inputStyle, cursor: "pointer" }}
            onFocus={(e) => (e.target.style.borderColor = `${T.blue}66`)}
            onBlur={(e)  => (e.target.style.borderColor = T.border2)}>
            <option value="openai">OpenAI</option>
            <option value="groq">Groq — Free tier</option>
            <option value="nvidia">NVIDIA NIM — Free credits</option>
            <option value="local">Local (LM Studio / Ollama)</option>
          </select>

          {/* Model dropdown */}
          <label style={labelStyle}>Model</label>
          {isLocal ? (
            <input type="text" value={byokModel} onChange={(e) => setByokModel(e.target.value)}
              placeholder="e.g. qwen2.5-coder-7b-instruct"
              style={inputStyle}
              onFocus={(e) => (e.target.style.borderColor = `${T.blue}66`)}
              onBlur={(e)  => (e.target.style.borderColor = T.border2)} />
          ) : (
            <select value={byokModel} onChange={(e) => setByokModel(e.target.value)}
              style={{ ...inputStyle, cursor: "pointer" }}
              onFocus={(e) => (e.target.style.borderColor = `${T.blue}66`)}
              onBlur={(e)  => (e.target.style.borderColor = T.border2)}>
              {models.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
          )}

          {/* API Key input */}
          <label style={labelStyle}>API Key</label>
          <input type="password" value={byokKey} onChange={(e) => setByokKey(e.target.value)}
            placeholder={meta.keyPlaceholder}
            style={inputStyle}
            onFocus={(e) => (e.target.style.borderColor = `${T.blue}66`)}
            onBlur={(e)  => (e.target.style.borderColor = T.border2)}
            onKeyDown={(e) => { if (e.key === "Enter") handleSave(); }} />
          <p style={{ fontSize: "11px", color: T.textMuted, fontFamily: T.fontUI, marginBottom: "18px" }}>
            {meta.keyHint}
          </p>

          {/* Buttons */}
          <div style={{ display: "flex", gap: "8px" }}>
            <button onClick={handleSave} style={{ flex: 1, height: "36px", background: `${T.blue}22`, border: `1px solid ${T.blue}55`, borderRadius: T.r6, color: T.blue, fontSize: "13px", fontWeight: "600", cursor: "pointer", fontFamily: T.fontUI }}>
              Save
            </button>
            {isSaved && (
              <button onClick={handleClear} style={{ height: "36px", padding: "0 16px", background: `${T.red}18`, border: `1px solid ${T.red}44`, borderRadius: T.r6, color: T.red, fontSize: "13px", fontWeight: "600", cursor: "pointer", fontFamily: T.fontUI }}>
                Remove Key
              </button>
            )}
            <button onClick={onClose} style={{ height: "36px", padding: "0 16px", background: "none", border: `1px solid ${T.border2}`, borderRadius: T.r6, color: T.textMuted, fontSize: "13px", cursor: "pointer", fontFamily: T.fontUI }}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};