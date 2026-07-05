"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { color } from "@/lib/departments";
import { fetchStudioQueue } from "@/lib/api";

const ORANGE = color("AI STUDIO");
const LANES = [["Awaiting Approval", "awaiting_approval"], ["Published", "published"],
               ["In Progress", "in_progress"], ["Blocked", "blocked"]];

// pipeline stages → wiring status (green=wired, amber=needs provider, grey=todo)
const STAGES = [
  ["Research", "🟢"], ["Script", "🟢"], ["Creative Director", "🟢"],
  ["Voice (Kokoro/say)", "🟢"], ["Assets (Flux/card)", "🟢"], ["Music", "🟢"],
  ["Render (FFmpeg)", "🟢"], ["Thumbnail", "🟢"], ["SEO / GEO", "🟢"], ["Discovery Gate", "🟢"],
  ["Publish", "🟢"], ["Analytics", "🟢"], ["Learning", "🟢"],
];

export default function AIStudio() {
  const [q, setQ] = useState({ counts: {}, recent: [] });
  useEffect(() => {
    const t = () => fetchStudioQueue().then(setQ).catch(() => {});
    t(); const id = setInterval(t, 10000); return () => clearInterval(id);
  }, []);
  const runs = q.recent || [];

  return (
    <div className="only-desktop" style={{ maxWidth: 1000, margin: "0 auto" }}>
      <Eyebrow style={{ color: ORANGE }}>AI Studio</Eyebrow>
      <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 6px" }}>Autonomous content pipeline</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 20 }}>
        Topic → Creative Director → voice + images → FFmpeg render → gate → publish → Episodes → Learning.
        Local-first (draft): Kokoro/say · Flux/card · FFmpeg — swap in premium providers without changing the pipeline.
      </div>

      <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        {LANES.map(([label, key]) => (
          <div key={key} className="glass" style={{ padding: "10px 16px", borderRadius: 12, minWidth: 120 }}>
            <div style={{ fontSize: 24, fontWeight: 600, color: ORANGE }}>{q.counts?.[key] ?? 0}</div>
            <div style={{ fontSize: 11, opacity: 0.55 }}>{label}</div>
          </div>
        ))}
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
          <Eyebrow style={{ color: ORANGE }}>Recent Runs (real)</Eyebrow>
          <div style={{ marginTop: 10 }}>
            {runs.length === 0
              ? <div style={{ opacity: 0.4, fontSize: 13, padding: "8px 0" }}>
                  no runs yet — run <code>scripts/ai_studio_run.py</code></div>
              : runs.map((r) => {
                const dot = r.status === "published" ? "🟢" : r.status === "awaiting_approval" ? "🟡" : "🔴";
                let fail = null; try { fail = r.failure ? JSON.parse(r.failure) : null; } catch {}
                return (
                  <div key={r.id} style={{ padding: "7px 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                      <span>{dot} {r.topic} <span style={{ opacity: 0.4 }}>· {r.mode}</span></span>
                      <span style={{ opacity: 0.55 }}>
                        {Math.round((r.confidence || 0) * 100)}% · ${(r.cost || 0).toFixed(2)} · {((r.duration_ms || 0) / 1000).toFixed(0)}s
                      </span>
                    </div>
                    {fail && <div style={{ fontSize: 11, color: "#FF7A5A", marginTop: 2 }}>
                      ✗ {fail.stage}: {fail.reason} → {fail.recommendation}</div>}
                  </div>);
              })}
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
