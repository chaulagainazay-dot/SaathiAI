"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchCeoOs, completeMission, sendChat, login, enrollVoice } from "@/lib/api";
import { useVoice } from "@/lib/useVoice";

const GOLD = "#E8B84B";
const RULE = ["Decide", "Automate", "Learn", "Earn"];

function Card({ icon, title, children }) {
  return (
    <Panel style={{ padding: 18 }}>
      <div style={{ fontSize: 12, opacity: 0.55, marginBottom: 8 }}>{icon} {title}</div>
      {children}
    </Panel>
  );
}

export default function OperatingSystem() {
  const [d, setD] = useState(null);
  const [chat, setChat] = useState([]);      // {role, text}
  const [ask, setAsk] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const t = () => fetchCeoOs().then(setD).catch(() => {});
    t(); const id = setInterval(t, 10000); return () => clearInterval(id);
  }, []);

  const submitAsk = async () => {
    const text = ask.trim();
    if (!text || busy) return;
    setChat((c) => [...c, { role: "you", text }]); setAsk(""); setBusy(true);
    try {
      const r = await sendChat(text);
      setChat((c) => [...c, { role: "saathi", text: r.reply || "…" }]);
    } catch (e) {
      if (String(e).includes("unauthorized")) {
        const pw = typeof window !== "undefined" ? window.prompt("Enter your password to unlock Saathi:") : null;
        if (pw) {
          const r = await login(pw).catch(() => ({ ok: false }));
          if (r.ok) { setBusy(false); return submitAskText(text); }
        }
        setChat((c) => [...c, { role: "saathi", text: "Couldn't sign in — try again." }]);
      } else {
        setChat((c) => [...c, { role: "saathi", text: "Sorry — I couldn't reach my brain just now." }]);
      }
    } finally { setBusy(false); }
  };
  const submitAskText = async (text) => {
    setBusy(true);
    try {
      const r = await sendChat(text);
      setChat((c) => [...c, { role: "saathi", text: r.reply || "…" }]);
    } catch {
      setChat((c) => [...c, { role: "saathi", text: "Sorry — I couldn't reach my brain just now." }]);
    } finally { setBusy(false); }
  };
  if (!d) return <div className="only-desktop" style={{ maxWidth: 1000, margin: "40px auto", opacity: 0.5 }}>loading…</div>;

  const completeMissionItem = (item) =>
    completeMission(item).then((r) => r.mission && setD({ ...d, mission: r.mission })).catch(() => {});
  const voice = useVoice((transcript, reply) =>
    setChat((c) => [...c, ...(transcript ? [{ role: "you", text: transcript }] : []), { role: "saathi", text: reply }]));

  const [enrolling, setEnrolling] = useState(false);
  const [enrollMsg, setEnrollMsg] = useState("");
  const enroll = async () => {
    setEnrollMsg(""); setEnrolling(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      const chunks = [];
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        try {
          await enrollVoice(new Blob(chunks, { type: "audio/webm" }));
          setEnrollMsg("✓ Voice enrolled — Saathi will now recognise you.");
        } catch (e) { setEnrollMsg(`Enroll failed: ${e}`); }
        finally { setEnrolling(false); }
      };
      rec.start();
      setTimeout(() => rec.state !== "inactive" && rec.stop(), 5000); // ~5s sample
    } catch { setEnrollMsg("Microphone permission needed."); setEnrolling(false); }
  };

  const met = d.rule.met || {};
  const f = (d.studio && d.studio.factory) || {};
  const runtime = f.avg_runtime_ms ? `${Math.floor(f.avg_runtime_ms / 60000)}m ${Math.round((f.avg_runtime_ms % 60000) / 1000)}s` : "—";
  return (
    <div className="only-desktop" style={{ maxWidth: 1000, margin: "0 auto" }}>
      <div style={{ fontSize: 30, fontWeight: 600, margin: "6px 0 4px" }}>{d.greeting} 👋</div>
      <div style={{ fontSize: 13, opacity: 0.45, marginBottom: 20 }}>Today's Operating System · what needs your attention</div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 14 }}>
        <Card icon="🎯" title="Dream">
          <div style={{ fontSize: 28, fontWeight: 600 }}>{d.dream.progress_pct}%</div>
          <div style={{ fontSize: 12, color: d.dream.delta >= 0 ? "#4FD07A" : "#FF5A5A" }}>
            {d.dream.delta >= 0 ? "▲" : "▼"} {Math.abs(d.dream.delta)}%
          </div>
        </Card>
        <Card icon="⭐" title="Rule">
          <div style={{ fontSize: 28, fontWeight: 600 }}>{d.rule.score} / {d.rule.of}</div>
          <div style={{ display: "flex", gap: 8, marginTop: 6, fontSize: 12, flexWrap: "wrap" }}>
            {RULE.map((r) => <span key={r} style={{ opacity: met[r] || met[r.toLowerCase()] ? 1 : 0.35 }}>
              {met[r] || met[r.toLowerCase()] ? "☑" : "☐"} {r}</span>)}
          </div>
        </Card>
        <Card icon="🤖" title="Automation">
          <div style={{ fontSize: 28, fontWeight: 600 }}>{d.automation.workflows} <span style={{ fontSize: 14, opacity: .5 }}>workflows</span></div>
          <div style={{ fontSize: 12, opacity: 0.6 }}>health {d.automation.health}% · {d.automation.runs_today} runs · agent {d.automation.agent_online ? "🟢" : "🔴"}</div>
        </Card>
        <Card icon="🧠" title="Learning">
          <div style={{ fontSize: 28, fontWeight: 600 }}>{d.learning.episodes_today} <span style={{ fontSize: 14, opacity: .5 }}>episodes</span></div>
          <div style={{ fontSize: 12, opacity: 0.6 }}>{d.learning.verified_improvements} verified · {d.learning.knowledge_added} taught</div>
        </Card>
        <Card icon="💰" title="Revenue">
          <div style={{ fontSize: 13, lineHeight: 1.9 }}>
            <div>Cafeteria <b>NPR {d.revenue.cafeteria || 0}</b></div>
            <div>AI Studio <b>${d.revenue.ai_studio || 0}</b></div>
            <div>Trading <b style={{ color: "#4FD07A" }}>paper {d.revenue.trading_pct || 0}%</b></div>
          </div>
        </Card>
        <Card icon="⚠️" title="Needs You">
          {d.needs_you.length === 0
            ? <div style={{ opacity: 0.4, fontSize: 13 }}>nothing pending 🎉</div>
            : d.needs_you.map((n, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, padding: "4px 0" }}>
                <span>{n.label}</span><span style={{ color: GOLD }}>{n.cta}</span>
              </div>))}
        </Card>
      </div>

      {d.mission && d.mission.topic && (
        <Panel style={{ padding: 18, marginTop: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
            <div style={{ fontSize: 12, opacity: 0.55 }}>
              🎓 {d.mission.program} — Day {d.mission.day} · {d.mission.episode}
            </div>
            <div style={{ fontSize: 12, opacity: 0.6 }}>🔥 {d.mission.streak}d streak · ~{d.mission.estimated_minutes} min</div>
          </div>
          <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 2 }}>{d.mission.topic}</div>
          <div style={{ fontSize: 12, opacity: 0.5, marginBottom: 14 }}>
            {d.mission.phase} · {d.mission.difficulty} · 🎥 {d.mission.youtube_number} · {d.mission.video_status}
          </div>
          <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
            {(d.mission.checklist || []).map((c) => (
              <button key={c.key} onClick={() => completeMissionItem(c.key)}
                style={{ background: "none", border: "none", color: "inherit", cursor: "pointer",
                  fontSize: 14, opacity: c.done ? 0.9 : 0.6, padding: 0 }}>
                {c.done ? "✅" : "⬜"} {c.label}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 11, opacity: 0.4, marginTop: 12 }}>
            {d.mission.completed}/{d.mission.total} done · reward +1 episode · +1 streak · +{d.mission.reward?.dream_pct}% dream
          </div>
        </Panel>
      )}

      <Panel style={{ padding: 18, marginTop: 14 }}>
        <div style={{ fontSize: 12, opacity: 0.55, marginBottom: 12 }}>🏭 Today's Factory</div>
        {Object.keys(f.latest_stages || {}).length > 0 && (
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 16,
            paddingBottom: 14, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
            {["research", "script", "voice", "assets", "render", "metadata", "gate", "publish", "analytics", "learning"]
              .filter((s) => s in f.latest_stages).map((s) => (
              <span key={s} style={{ fontSize: 12, opacity: 0.85 }}>
                {f.latest_stages[s] ? "✅" : "❌"} {s}
              </span>
            ))}
          </div>
        )}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 14, rowGap: 16 }}>
          {[
            ["Runs", f.runs ?? 0],
            ["Published", f.published ?? 0],
            ["Waiting", f.waiting_approval ?? 0],
            ["Blocked", f.blocked ?? 0, (f.blocked ?? 0) > 0 ? "#FF5A5A" : null],
            ["Avg Confidence", `${Math.round((f.avg_confidence || 0) * 100)}%`],
            ["Avg Cost", `$${(f.avg_cost || 0).toFixed(2)}`],
            ["Avg Runtime", runtime],
            ["Learning Episodes", d.learning.episodes_today],
            ["Verified Insights", d.learning.verified_improvements],
            ["Revenue Today", `$${d.revenue.ai_studio || 0}`],
          ].map(([label, val, col]) => (
            <div key={label}>
              <div style={{ fontSize: 22, fontWeight: 600, color: col || "inherit" }}>{val}</div>
              <div style={{ fontSize: 11, opacity: 0.5 }}>{label}</div>
            </div>
          ))}
        </div>
      </Panel>

      {chat.length > 0 && (
        <div style={{ marginTop: 18, display: "flex", flexDirection: "column", gap: 8 }}>
          {chat.map((m, i) => (
            <div key={i} style={{ alignSelf: m.role === "you" ? "flex-end" : "flex-start",
              maxWidth: "80%", padding: "8px 14px", borderRadius: 14, fontSize: 14,
              background: m.role === "you" ? "rgba(232,184,75,0.15)" : "rgba(255,255,255,0.06)" }}>
              {m.text}
            </div>
          ))}
        </div>
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}>
        <input value={ask} onChange={(e) => setAsk(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submitAsk()} disabled={busy || voice.busy}
          placeholder={voice.recording ? "Listening…" : voice.busy ? "Transcribing…" : busy ? "Saathi is thinking…" : "Ask Saathi… (or hold 🎤)"}
          style={{ flex: 1, padding: "12px 16px",
          borderRadius: 24, border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)",
          color: "inherit", fontSize: 14 }} />
        <button onPointerDown={voice.start} onPointerUp={voice.stop} onPointerLeave={voice.stop}
          disabled={busy || voice.busy} title="Hold to speak"
          style={{ width: 46, height: 46, borderRadius: "50%", border: "none", fontSize: 18, cursor: "pointer",
            background: voice.recording ? "radial-gradient(circle at 38% 35%, #ffd0d0, #ff6b6b)" : "rgba(255,255,255,0.08)",
            color: voice.recording ? "#0A1120" : "inherit",
            boxShadow: voice.recording ? "0 0 20px rgba(255,107,107,0.7)" : "none" }}>🎤</button>
      </div>
      <div style={{ marginTop: 8, display: "flex", gap: 10, alignItems: "center" }}>
        <button onClick={enroll} disabled={enrolling}
          style={{ fontSize: 12, padding: "6px 14px", borderRadius: 20, cursor: "pointer",
            border: "1px solid rgba(232,184,75,0.5)", background: "transparent", color: GOLD,
            opacity: enrolling ? 0.6 : 1 }}>
          {enrolling ? "Recording 5s — keep talking…" : "🔐 Teach Saathi my voice"}</button>
        {enrollMsg && <span style={{ fontSize: 11.5, opacity: 0.7 }}>{enrollMsg}</span>}
      </div>
    </div>
  );
}
