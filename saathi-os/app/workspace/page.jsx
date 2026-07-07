"use client";
import { useEffect, useRef, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { workspaceTurn, fetchMissions } from "@/lib/api";

const ACCENT = "#9B6BFF", TEAL = "#00BFA5", GREY = "#5b6478";
const MODES = [
  ["research", "Research", "read only"],
  ["planning", "Planning", "architecture, no code"],
  ["implementation", "Implementation", "propose steps"],
  ["cowork", "Cowork", "the team answers"],
];

export default function Workspace() {
  const [missions, setMissions] = useState([]);
  const [mission, setMission] = useState("");
  const [mode, setMode] = useState("cowork");
  const [thread, setThread] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);
  useEffect(() => { fetchMissions().then((d) => setMissions(d.missions || [])).catch(() => {}); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [thread, busy]);

  const send = async () => {
    const msg = input.trim();
    if (!msg || busy) return;
    setInput(""); setThread((t) => [...t, { role: "you", text: msg }]); setBusy(true);
    try {
      const r = await workspaceTurn(msg, mission, mode);
      setThread((t) => [...t, { role: "saathi", text: r.reply || "…", mode: r.mode,
        analysis: r.analysis, actions: (r.actions || []).filter(Boolean) }]);
    } catch (e) {
      setThread((t) => [...t, { role: "saathi", text: `Couldn't reach the workspace: ${e}` }]);
    } finally { setBusy(false); }
  };

  const missionName = missions.find((m) => m.key === mission)?.name;

  return (
    <div className="page" style={{ maxWidth: 860, margin: "0 auto", paddingBottom: 40, display: "flex",
      flexDirection: "column", height: "calc(100dvh - 40px)" }}>
      <Eyebrow style={{ color: ACCENT }}>SaathiOS · Workspace</Eyebrow>
      <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 8px" }}>Saathi — CEO Workspace</div>

      {/* mission + mode controls */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10, alignItems: "center" }}>
        <select value={mission} onChange={(e) => setMission(e.target.value)}
          style={{ padding: "7px 12px", borderRadius: 9, fontSize: 12.5, border: "1px solid rgba(255,255,255,0.12)",
            background: "rgba(255,255,255,0.05)", color: "inherit" }}>
          <option value="" style={{ color: "#000" }}>General (no mission)</option>
          {missions.map((m) => <option key={m.id} value={m.key} style={{ color: "#000" }}>{m.name}</option>)}
        </select>
        {MODES.map(([k, label, hint]) => (
          <button key={k} onClick={() => setMode(k)} title={hint}
            style={{ padding: "6px 12px", borderRadius: 999, cursor: "pointer", fontSize: 12, fontWeight: 600,
              border: `1px solid ${mode === k ? ACCENT : ACCENT + "44"}`,
              background: mode === k ? ACCENT + "22" : "transparent", color: mode === k ? ACCENT : "inherit" }}>
            {label}</button>
        ))}
      </div>

      {/* thread */}
      <Panel style={{ padding: 16, flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 12 }}>
        {thread.length === 0 && (
          <div style={{ opacity: 0.5, fontSize: 13, margin: "auto", textAlign: "center", maxWidth: 460 }}>
            One conversation to research, plan, and act on {missionName ? `“${missionName}”` : "any Mission"}.<br />
            Paste a GitHub URL to auto-analyse it · switch modes to change what Saathi may do.
          </div>
        )}
        {thread.map((m, i) => (
          <div key={i} style={{ alignSelf: m.role === "you" ? "flex-end" : "flex-start", maxWidth: "82%" }}>
            <div style={{ fontSize: 9.5, opacity: 0.5, marginBottom: 3, textAlign: m.role === "you" ? "right" : "left" }}>
              {m.role === "you" ? "You" : `Saathi${m.mode ? " · " + m.mode : ""}`}</div>
            <div style={{ fontSize: 13.5, lineHeight: 1.55, whiteSpace: "pre-wrap", padding: "10px 14px",
              borderRadius: 12, background: m.role === "you" ? "rgba(155,107,255,0.16)" : "rgba(255,255,255,0.05)" }}>
              {m.text}
            </div>
            {m.analysis && (
              <div style={{ marginTop: 6, fontSize: 10.5, opacity: 0.6 }}>
                📚 stored in Library · tags: {(m.analysis.tags || []).slice(0, 6).join(", ")}
              </div>
            )}
            {m.actions?.length > 0 && (
              <div style={{ marginTop: 4, fontSize: 10, color: TEAL }}>✓ {m.actions.join(" · ")}</div>
            )}
          </div>
        ))}
        {busy && <div style={{ alignSelf: "flex-start", fontSize: 12.5, opacity: 0.5 }}>Saathi is thinking…</div>}
        <div ref={endRef} />
      </Panel>

      {/* input */}
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <input value={input} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={`Ask, paste a repo, or plan… (${mode} mode)`}
          style={{ flex: 1, padding: "12px 16px", borderRadius: 24, fontSize: 14,
            border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)", color: "inherit" }} />
        <button onClick={send} disabled={busy}
          style={{ padding: "0 22px", borderRadius: 24, border: "none", cursor: "pointer",
            fontWeight: 600, color: "#fff", background: ACCENT, opacity: busy ? 0.6 : 1 }}>Send</button>
      </div>
    </div>
  );
}
