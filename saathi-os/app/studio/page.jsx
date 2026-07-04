"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { color } from "@/lib/departments";
import { fetchAutomation } from "@/lib/api";

const ORANGE = color("AI STUDIO");

// pipeline stages → wiring status (green=wired, amber=needs provider, grey=todo)
const STAGES = [
  ["Discovery", "🟢"], ["Research", "🟢"], ["Script", "🟢"], ["Storyboard", "🟢"],
  ["Assets (image)", "🟡"], ["Voice", "🟡"], ["Music", "⚪"], ["Render", "🟡"],
  ["Quality", "⚪"], ["Thumbnail", "🟢"], ["SEO / GEO", "🟢"], ["Discovery Gate", "🟢"],
  ["Publish", "🟢"], ["Analytics", "🟢"], ["Learning", "🟢"],
];

export default function AIStudio() {
  const [runs, setRuns] = useState([]);
  useEffect(() => {
    const t = () => fetchAutomation().then((d) => setRuns((d.recent_runs || []).filter(
      (r) => r.workflow === "ai_studio" || r.capability === "publish_video"))).catch(() => {});
    t(); const id = setInterval(t, 10000); return () => clearInterval(id);
  }, []);

  return (
    <div className="only-desktop" style={{ maxWidth: 1000, margin: "0 auto" }}>
      <Eyebrow style={{ color: ORANGE }}>AI Studio</Eyebrow>
      <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 6px" }}>Autonomous content pipeline</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 20 }}>
        Topic → AI script + SEO → Discovery Gate → publish via your browser → Episodes → Learning.
        🟢 wired · 🟡 needs a provider · ⚪ planned
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color: ORANGE }}>Pipeline</Eyebrow>
          <div style={{ marginTop: 10 }}>
            {STAGES.map(([name, light], i) => (
              <div key={name} style={{ display: "flex", alignItems: "center", gap: 10,
                fontSize: 13.5, padding: "5px 0" }}>
                <span style={{ fontSize: 11 }}>{light}</span>
                <span>{name}</span>
                {i < STAGES.length - 1 && <span style={{ marginLeft: "auto", opacity: 0.2 }}>↓</span>}
              </div>
            ))}
          </div>
        </Panel>

        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color: ORANGE }}>Recent Publishes (real)</Eyebrow>
          <div style={{ marginTop: 10 }}>
            {runs.length === 0
              ? <div style={{ opacity: 0.4, fontSize: 13, padding: "8px 0" }}>
                  no runs yet — run <code>scripts/ai_studio_run.py</code></div>
              : runs.map((r) => (
                <div key={r.id} style={{ display: "flex", justifyContent: "space-between",
                  fontSize: 13, padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                  <span>{r.ok ? "🟢" : "🔴"} {r.title || "run"}</span>
                  <span style={{ opacity: 0.5 }}>
                    {r.video_url ? "published" : (r.error || "")}{r.duration_ms ? ` · ${(r.duration_ms/1000).toFixed(0)}s` : ""}
                  </span>
                </div>))}
          </div>
          <div style={{ marginTop: 14, fontSize: 12, opacity: 0.5 }}>
            Providers behind the connector layer: images (Flux/Imagen), animation (Hyperframes/HeyGen),
            voice (Kokoro/ElevenLabs), render (FFmpeg/Runway) — wired as each is configured.
          </div>
        </Panel>
      </div>
    </div>
  );
}
