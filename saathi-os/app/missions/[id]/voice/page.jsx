"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchBrand, registerVoice, activateVoice } from "@/lib/api";

const ACCENT = "#9B6BFF", TEAL = "#00BFA5", RED = "#FF5A5A";

export default function VoicePage() {
  const { id } = useParams();
  const [b, setB] = useState(null);
  const [f, setF] = useState({ name: "", purpose: "own_voice", language: "English",
    accent: "Nepali", style: "teacher", emotion: "friendly", speed: "1.05", pitch: "medium", provider: "kokoro" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const load = () => fetchBrand(id).then(setB).catch((e) => setErr(String(e)));
  useEffect(() => { load(); }, [id]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const save = async () => {
    if (!f.name.trim()) { setErr("Voice name required"); return; }
    setBusy(true); setErr(null);
    try { await registerVoice(id, { ...f, speed: Number(f.speed) }); load(); }
    catch (e) { setErr(`${e} — login may be required`); } finally { setBusy(false); }
  };
  const activate = (vid) => activateVoice(id, vid).then(load).catch((e) => setErr(String(e)));

  if (!b) return <div className="page" style={{ padding: 40, opacity: 0.5 }}>{err || "Loading voice identity…"}</div>;
  const inp = { width: "100%", padding: "9px 11px", borderRadius: 9, fontSize: 13,
    border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)", color: "inherit" };
  const av = b.active_voice;

  return (
    <div className="page" style={{ maxWidth: 760, margin: "0 auto", paddingBottom: 60 }}>
      <a href={`/missions/${id}`} style={{ fontSize: 12, opacity: 0.5, textDecoration: "none", color: "inherit" }}>← Mission</a>
      <Eyebrow style={{ color: ACCENT, marginTop: 8 }}>Brand Identity · Voice</Eyebrow>
      <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 4px" }}>Voice Identity</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 16 }}>
        A reusable per-Mission asset every Director reads. Register a profile now; the audio recording +
        clone backend plugs in later behind the provider without changing the pipeline.
      </div>

      {av && <Panel style={{ padding: 14, marginBottom: 14, borderLeft: `3px solid ${TEAL}` }}>
        <div style={{ fontSize: 13 }}>Active voice: <b>{av.name} v{av.version}</b> · {av.provider} · {av.style}/{av.emotion}</div>
        {av.recommendation?.best_for && <div style={{ fontSize: 11.5, opacity: 0.6, marginTop: 3 }}>
          ✓ best for: {av.recommendation.best_for.join(", ")}</div>}
      </Panel>}
      {err && <div style={{ fontSize: 12, color: RED, marginBottom: 10 }}>{err}</div>}

      {/* sample prompts (read these aloud when the audio backend lands) */}
      <Panel style={{ padding: 16, marginBottom: 14 }}>
        <Eyebrow style={{ color: ACCENT }}>Recording prompts (read aloud)</Eyebrow>
        <div style={{ marginTop: 10 }}>
          {(b.sample_prompts || []).map((p) => (
            <div key={p.id} style={{ padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
              <div style={{ fontSize: 11, opacity: 0.5 }}>Sample {p.id} · {p.label}</div>
              <div style={{ fontSize: 12.5 }}>{p.text}</div>
            </div>
          ))}
        </div>
      </Panel>

      {/* register a voice profile */}
      <Panel style={{ padding: 18, marginBottom: 14 }}>
        <Eyebrow style={{ color: ACCENT }}>Register a voice profile</Eyebrow>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 10 }}>
          <input placeholder="Name (e.g. Ajay, Mr. Yeti)" value={f.name} onChange={set("name")} style={inp} />
          <select value={f.purpose} onChange={set("purpose")} style={inp}>
            {(b.purposes || []).map((p) => <option key={p} value={p} style={{ color: "#000" }}>{p}</option>)}
          </select>
          <input placeholder="Language" value={f.language} onChange={set("language")} style={inp} />
          <input placeholder="Accent" value={f.accent} onChange={set("accent")} style={inp} />
          <input placeholder="Style (teacher/narrator/analyst)" value={f.style} onChange={set("style")} style={inp} />
          <input placeholder="Emotion" value={f.emotion} onChange={set("emotion")} style={inp} />
          <input placeholder="Speed (1.05)" value={f.speed} onChange={set("speed")} style={inp} />
          <input placeholder="Pitch" value={f.pitch} onChange={set("pitch")} style={inp} />
          <input placeholder="Provider (kokoro/xtts/elevenlabs)" value={f.provider} onChange={set("provider")} style={inp} />
        </div>
        <button onClick={save} disabled={busy}
          style={{ marginTop: 12, padding: "11px 18px", borderRadius: 11, border: "none", cursor: "pointer",
            fontWeight: 600, color: "#fff", background: ACCENT, opacity: busy ? 0.6 : 1, width: "100%" }}>
          {busy ? "Registering…" : "Register voice (new version)"}</button>
      </Panel>

      {/* voice registry */}
      <Panel style={{ padding: 18 }}>
        <Eyebrow style={{ color: ACCENT }}>Voice Registry</Eyebrow>
        <div style={{ marginTop: 10 }}>
          {(b.voices || []).length === 0 && <div style={{ fontSize: 12.5, opacity: 0.4 }}>no voices yet</div>}
          {(b.voices || []).map((v) => (
            <div key={v.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0",
              borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13 }}><b>{v.name} v{v.version}</b>
                  <span style={{ opacity: 0.5, fontSize: 11.5 }}> · {v.provider} · {v.style}/{v.emotion}</span></div>
                {v.analysis?.wpm && <div style={{ fontSize: 10.5, opacity: 0.45 }}>~{v.analysis.wpm} WPM (estimated)</div>}
              </div>
              {av?.id === v.id
                ? <span className="mono" style={{ fontSize: 10.5, color: TEAL }}>● active</span>
                : <button onClick={() => activate(v.id)} style={{ fontSize: 11, padding: "5px 12px",
                    borderRadius: 8, cursor: "pointer", border: `1px solid ${ACCENT}66`, background: "transparent", color: ACCENT }}>
                    Set active</button>}
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
