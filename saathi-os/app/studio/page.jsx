"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { color } from "@/lib/departments";
import { fetchStudioQueue, fetchStudioPlan, fetchStudioScript, fetchStudioProduce } from "@/lib/api";

const ORANGE = color("AI STUDIO");
const TEAL = "#00BFA5";
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
  const [plan, setPlan] = useState(null);
  const [script, setScript] = useState(null);
  const [writing, setWriting] = useState(false);
  const genScript = () => { setWriting(true); fetchStudioScript().then((d) => setScript(d.script)).catch(() => {}).finally(() => setWriting(false)); };
  const [prod, setProd] = useState(null);
  const [producing, setProducing] = useState(false);
  const produce = () => { setProducing(true); fetchStudioProduce().then((p) => { setProd(p); setScript(p.script); }).catch(() => {}).finally(() => setProducing(false)); };
  useEffect(() => {
    const t = () => fetchStudioQueue().then(setQ).catch(() => {});
    t(); const id = setInterval(t, 10000);
    fetchStudioPlan().then(setPlan).catch(() => {});
    return () => clearInterval(id);
  }, []);
  const runs = q.recent || [];

  return (
    <div className="only-desktop" style={{ maxWidth: 1000, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <Eyebrow style={{ color: ORANGE }}>AI Studio</Eyebrow>
        <a href="/studio/control-room" style={{ fontSize: 12.5, fontWeight: 600, color: ORANGE,
          textDecoration: "none", padding: "6px 14px", borderRadius: 10, border: `1px solid ${ORANGE}66` }}>
          🎛 Control Room →</a>
      </div>
      <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 6px" }}>Autonomous content pipeline</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 16 }}>
        Topic → Creative Director → voice + images → FFmpeg render → gate → publish → Episodes → Learning.
        Local-first (draft): Kokoro/say · Flux/card · FFmpeg — swap in premium providers without changing the pipeline.
      </div>

      {plan && plan.topic && (
        <Panel style={{ padding: 16, marginBottom: 16, border: "1px solid rgba(255,138,61,0.3)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <Eyebrow style={{ color: ORANGE }}>🎬 Today's Studio Plan (Director)</Eyebrow>
            <span className="mono" style={{ fontSize: 10, opacity: 0.5 }}>{plan.memory_count} made · {plan.episode}</span>
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, marginTop: 8 }}>Day {plan.day}: {plan.topic}</div>
          <div className="mono" style={{ fontSize: 11, opacity: 0.55, marginTop: 2 }}>
            {plan.phase} · {plan.skill} · 🎭 {plan.character?.name || "Mr. Yeti"} · {plan.voice_tone}
          </div>
          <div style={{ fontSize: 12, opacity: 0.6, marginTop: 6 }}>{plan.objective}</div>
          {plan.avoid?.length > 0 && <div style={{ fontSize: 10.5, opacity: 0.4, marginTop: 6 }}>avoiding: {plan.avoid.slice(0, 4).join(", ")}</div>}
          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            <button onClick={produce} disabled={producing}
              style={{ padding: "8px 16px", borderRadius: 10, border: "none", cursor: "pointer",
                fontWeight: 600, color: "#fff", background: ORANGE, opacity: producing ? 0.6 : 1 }}>
              {producing ? "Studio Executive running…" : "🎬 Produce Episode (full pipeline)"}</button>
            <button onClick={genScript} disabled={writing}
              style={{ padding: "8px 16px", borderRadius: 10, cursor: "pointer",
                border: `1px solid ${ORANGE}`, background: "transparent", color: ORANGE, opacity: writing ? 0.6 : 1 }}>
              {writing ? "writing…" : "✍ Script only"}</button>
          </div>

          {prod && (
            <div style={{ marginTop: 12, display: "flex", gap: 6, flexWrap: "wrap", fontSize: 11 }}>
              {[["Research", prod.research?.summary], ["Creative", prod.creative?.story_arc], ["Script", `${prod.script?.scenes?.length} scenes`], ["Storyboard", `${prod.scene_package?.scene_count || 0} scenes`], ["Render", prod.render_plan?.adapter || (prod.plan_check?.ok === false ? "blocked" : "—")], ["Publish", prod.publish_plan?.platform_count ? `${prod.publish_plan.platform_count} platforms` : "—"]].map(([k, v]) => (
                <span key={k} style={{ padding: "4px 10px", borderRadius: 999, background: "rgba(255,138,61,0.12)" }}>✓ {k}</span>
              ))}
              <span style={{ padding: "4px 10px", borderRadius: 999,
                background: prod.status === "ready" ? "rgba(0,191,165,0.18)" : "rgba(232,184,75,0.18)",
                color: prod.status === "ready" ? TEAL : "#E8B84B" }}>● {prod.status}</span>
            </div>
          )}
          {prod?.research?.common_mistakes?.length > 0 && (
            <div style={{ marginTop: 8, fontSize: 11, opacity: 0.55 }}>
              🔎 common mistakes found: {prod.research.common_mistakes.slice(0, 2).join(" · ")}
            </div>
          )}

          {script && (
            <div style={{ marginTop: 14, borderTop: "1px solid rgba(255,255,255,0.08)", paddingTop: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.5 }}>HOOK</div>
              <div style={{ fontSize: 13.5, marginBottom: 10 }}>{script.hook}</div>
              <div style={{ fontSize: 12, opacity: 0.5 }}>SCENES · {script.est_seconds}s</div>
              {(script.scenes || []).map((s) => (
                <div key={s.n} style={{ fontSize: 12.5, padding: "5px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <b>{s.n}. ({s.seconds}s)</b> {s.narration}
                  <div style={{ fontSize: 10.5, opacity: 0.45 }}>🎥 {s.visual} · {s.camera}{s.animation ? ` · ${s.animation}` : ""}</div>
                </div>
              ))}
              <div style={{ fontSize: 12, opacity: 0.5, marginTop: 10 }}>SEO</div>
              <div style={{ fontSize: 12.5 }}>{script.seo?.title}</div>
              <div style={{ fontSize: 11, opacity: 0.5, marginTop: 2 }}>{(script.seo?.tags || []).slice(0, 8).join(" · ")}</div>
              {script.thumbnail_ideas?.length > 0 && <>
                <div style={{ fontSize: 12, opacity: 0.5, marginTop: 10 }}>THUMBNAIL IDEAS</div>
                {script.thumbnail_ideas.slice(0, 3).map((t, i) => <div key={i} style={{ fontSize: 11.5, opacity: 0.7, padding: "2px 0" }}>🖼 {t}</div>)}
              </>}
            </div>
          )}
        </Panel>
      )}

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
