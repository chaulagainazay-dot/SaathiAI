"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Panel, Eyebrow } from "@/components/ui";
import { enrollVoice, fetchMissions } from "@/lib/api";

const ACCENT = "var(--accent)", TEAL = "#00BFA5", RED = "#FF5A5A";

export default function VoiceHub() {
  const router = useRouter();
  const [missions, setMissions] = useState([]);
  const [enrolling, setEnrolling] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => { fetchMissions().then((d) => setMissions(d.missions || [])).catch(() => {}); }, []);

  const enroll = async () => {
    setMsg(""); setEnrolling(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      const chunks = [];
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        try {
          await enrollVoice(new Blob(chunks, { type: "audio/webm" }));
          setMsg("✓ Voice enrolled — Saathi will now recognise you when you speak.");
        } catch (e) { setMsg(`Enroll failed: ${e}. Voice enrollment only works on the Mac app (localhost).`); }
        finally { setEnrolling(false); }
      };
      rec.start();
      setTimeout(() => rec.state !== "inactive" && rec.stop(), 5000);
    } catch { setMsg("Microphone permission needed."); setEnrolling(false); }
  };

  return (
    <div className="page" style={{ maxWidth: 760, margin: "0 auto", paddingBottom: 60 }}>
      <Eyebrow style={{ color: ACCENT }}>SaathiOS · Voice</Eyebrow>
      <div style={{ fontSize: 28, fontWeight: 600, margin: "4px 0 4px" }}>Voice</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 18 }}>
        Two things: teach Saathi to recognise <b>your</b> voice, and configure each brand's speaking voice.
      </div>

      {/* 1. speaker enrollment */}
      <Panel style={{ padding: 20, marginBottom: 16, borderLeft: `3px solid ${TEAL}` }}>
        <Eyebrow style={{ color: TEAL }}>1 · Recognise my voice (speaker enrollment)</Eyebrow>
        <div style={{ fontSize: 12.5, opacity: 0.7, margin: "8px 0 14px" }}>
          Records ~5 seconds and saves your voice profile, so Saathi knows it's you and unlocks owner actions.
          Works on the Mac app (localhost:3000).
        </div>
        <button onClick={enroll} disabled={enrolling}
          style={{ padding: "12px 22px", borderRadius: 12, border: "none", cursor: "pointer",
            fontWeight: 600, color: "#fff", background: enrolling ? "#E8B84B" : TEAL, fontSize: 14 }}>
          {enrolling ? "🎙 Recording 5s — keep talking…" : "🔐 Teach Saathi my voice"}</button>
        {msg && <div style={{ fontSize: 12.5, marginTop: 12, color: msg.startsWith("✓") ? TEAL : RED }}>{msg}</div>}
      </Panel>

      {/* 2. per-mission voice studios */}
      <Panel style={{ padding: 20 }}>
        <Eyebrow style={{ color: ACCENT }}>2 · Brand voices (Voice Studio per Mission)</Eyebrow>
        <div style={{ fontSize: 12.5, opacity: 0.7, margin: "8px 0 12px" }}>
          Each business has its own voice identity — Mr. Yeti patient/encouraging, Surmount warm/adventurous.
          Open a Mission's Voice Studio to register, version, and A/B voices.
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {missions.map((m) => (
            <button key={m.id} onClick={() => router.push(`/missions/${m.id}/voice`)}
              style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "12px 16px", borderRadius: 10, cursor: "pointer", textAlign: "left",
                border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.03)", color: "inherit" }}>
              <span style={{ fontSize: 13.5, fontWeight: 600 }}>{m.name}</span>
              <span style={{ color: ACCENT, fontSize: 12.5 }}>🎙 Voice Studio →</span>
            </button>
          ))}
          {missions.length === 0 && <div style={{ fontSize: 12.5, opacity: 0.4 }}>loading missions…</div>}
        </div>
      </Panel>
    </div>
  );
}
