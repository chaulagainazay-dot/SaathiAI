"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Panel, Eyebrow } from "@/components/ui";
import MissionNav from "@/components/MissionNav";
import { fetchBrand, registerVoice, activateVoice, fetchVoicePackage,
  fetchVoiceExperiments, createVoiceExperiment } from "@/lib/api";

const ACCENT = "#9B6BFF", TEAL = "#00BFA5", RED = "#FF5A5A";

export default function VoicePage() {
  const { id } = useParams();
  const [b, setB] = useState(null);
  const [f, setF] = useState({ name: "", purpose: "own_voice", language: "English",
    accent: "Nepali", style: "teacher", emotion: "friendly", speed: "1.05", pitch: "medium", provider: "kokoro" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [pkg, setPkg] = useState(null);
  const [emotion, setEmotion] = useState("encouraging");
  const [exps, setExps] = useState([]);
  const [exp, setExp] = useState({ episode: "", voice_a: "", voice_b: "" });
  const load = () => {
    fetchBrand(id).then(setB).catch((e) => setErr(String(e)));
    fetchVoiceExperiments(id).then((d) => setExps(d.experiments || [])).catch(() => {});
  };
  useEffect(() => { load(); }, [id]);
  useEffect(() => { fetchVoicePackage(id, emotion, "hook").then((d) => setPkg(d.voice_package)).catch(() => {}); }, [id, emotion, b]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const startExp = async () => {
    if (!exp.voice_a || !exp.voice_b) { setErr("Pick two voices for the A/B"); return; }
    try { await createVoiceExperiment(id, exp); setExp({ episode: "", voice_a: "", voice_b: "" }); load(); }
    catch (e) { setErr(String(e)); }
  };

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
    <div>
      <MissionNav />
      <div className="page" style={{ maxWidth: 760, margin: "0 auto", paddingBottom: 60 }}>
        <Eyebrow style={{ color: ACCENT, marginTop: 8 }}>Brand Identity · Voice Studio</Eyebrow>
      <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 4px" }}>Voice Studio</div>
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

      {/* Voice Director — provider-agnostic Voice Package preview */}
      {pkg && <Panel style={{ padding: 18, marginBottom: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <Eyebrow style={{ color: ACCENT }}>Voice Director · Voice Package</Eyebrow>
          <select value={emotion} onChange={(e) => setEmotion(e.target.value)} style={{ ...inp, width: "auto", padding: "4px 8px" }}>
            {["encouraging", "excited", "calm", "serious", "warm"].map((x) => <option key={x} value={x} style={{ color: "#000" }}>{x}</option>)}
          </select>
        </div>
        <div className="mono" style={{ fontSize: 11.5, opacity: 0.75, marginTop: 8, lineHeight: 1.7 }}>
          voice: {pkg.voice_name || "—"} v{pkg.version} · provider <b style={{ color: TEAL }}>{pkg.provider}</b>
          {" · "}scene emotion: {pkg.scene_emotion}<br />
          delivery: rate {pkg.delivery?.rate} · pitch {pkg.delivery?.pitch} · emphasis {pkg.delivery?.emphasis}<br />
          providers available: {(pkg.providers_available || []).join(", ")}
        </div>
        <div style={{ fontSize: 10.5, opacity: 0.4, marginTop: 6 }}>
          Director emits this provider-agnostic package; TTS adapters consume it. Swap engine = swap adapter.
        </div>
      </Panel>}

      {/* Voice Experiments — A/B by evidence */}
      <Panel style={{ padding: 18, marginBottom: 14 }}>
        <Eyebrow style={{ color: ACCENT }}>Voice Experiments · A/B by evidence</Eyebrow>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto", gap: 8, marginTop: 10 }}>
          <input placeholder="Episode" value={exp.episode} onChange={(e) => setExp({ ...exp, episode: e.target.value })} style={inp} />
          <input placeholder="Voice A" value={exp.voice_a} onChange={(e) => setExp({ ...exp, voice_a: e.target.value })} style={inp} />
          <input placeholder="Voice B" value={exp.voice_b} onChange={(e) => setExp({ ...exp, voice_b: e.target.value })} style={inp} />
          <button onClick={startExp} style={{ padding: "0 16px", borderRadius: 9, border: "none",
            cursor: "pointer", fontWeight: 600, color: "#fff", background: ACCENT }}>Start</button>
        </div>
        <div style={{ marginTop: 10 }}>
          {exps.length === 0 && <div style={{ fontSize: 12, opacity: 0.4 }}>no experiments yet</div>}
          {exps.map((e) => (
            <div key={e.id} style={{ fontSize: 12.5, padding: "5px 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
              <b>{e.episode || "—"}</b> · {e.voice_a} vs {e.voice_b} · split {e.split}%
              {e.status === "done"
                ? <span style={{ color: TEAL }}> · winner {e.winner} {e.metrics?.retention ? `(${e.metrics.retention})` : ""}</span>
                : <span style={{ color: AMBER }}> · running</span>}
            </div>
          ))}
        </div>
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
  </div>
  );
}
