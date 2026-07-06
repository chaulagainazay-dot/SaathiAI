"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { color } from "@/lib/departments";
import { fetchControlRoom } from "@/lib/api";

const ORANGE = color("AI STUDIO");
const TEAL = "#00BFA5";
const AMBER = "#E8B84B";
const GREY = "#5b6478";

const DOT = { done: TEAL, pending: GREY, blocked: "#FF5A5A" };
const STAGE_LABEL = {
  curriculum: "Curriculum", research: "Research", creative: "Creative", script: "Script",
  storyboard: "Storyboard", render: "Render", publish: "Publish", memory: "Memory", learning: "Learning",
};

export default function ControlRoom() {
  const [r, setR] = useState(null);
  const [err, setErr] = useState(null);
  const [sel, setSel] = useState("script");
  const [busy, setBusy] = useState(false);
  const load = () => { setBusy(true); fetchControlRoom().then(setR).catch((e) => setErr(String(e))).finally(() => setBusy(false)); };
  useEffect(() => { load(); }, []);

  if (err && !r) return <div className="page" style={{ padding: 40, opacity: 0.6 }}>Control Room offline — {err}</div>;
  if (!r) return <div className="page" style={{ padding: 40, opacity: 0.5 }}>Booting the factory…</div>;

  const stage = r.stages.find((s) => s.stage === sel) || r.stages[0];
  const pct = (x) => `${Math.round((x || 0) * 100)}%`;

  return (
    <div className="page" style={{ maxWidth: 1180, margin: "0 auto", paddingBottom: 60 }}>
      {/* header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 18 }}>
        <div>
          <Eyebrow style={{ color: ORANGE }}>AI Studio OS · Control Room</Eyebrow>
          <div style={{ fontSize: 28, fontWeight: 600, marginTop: 4 }}>Day {r.day}: {r.topic}</div>
          <div className="mono" style={{ fontSize: 12, opacity: 0.5, marginTop: 2 }}>
            {r.episode} · {r.est_seconds}s · <span style={{ color: r.status === "ready" ? TEAL : AMBER }}>● {r.status}</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <a href="/evidence" style={{ fontSize: 12.5, fontWeight: 600, color: "#6E72F0",
            textDecoration: "none", padding: "9px 14px", borderRadius: 12, border: "1px solid #6E72F066" }}>
            🧠 Evidence →</a>
          <button onClick={load} disabled={busy}
            style={{ padding: "10px 20px", borderRadius: 12, border: "none", cursor: "pointer",
              fontWeight: 600, color: "#fff", background: ORANGE, opacity: busy ? 0.6 : 1 }}>
            {busy ? "Producing…" : "▶ Produce Episode"}</button>
        </div>
      </div>

      {/* health strip */}
      <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        {[["Studio Health", pct(r.health.studio)], ["Directors", r.health.directors],
          ["Episodes", r.health.episodes], ["Overall Confidence", pct(r.confidence_overall)],
          ["Total Cost", `$${r.cost_total}`], ["Queue Waiting", r.health.queue_waiting]].map(([k, v]) => (
          <div key={k} className="glass" style={{ padding: "10px 18px", borderRadius: 12, minWidth: 120 }}>
            <div style={{ fontSize: 22, fontWeight: 600, color: ORANGE }}>{v}</div>
            <div style={{ fontSize: 11, opacity: 0.55 }}>{k}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr 260px", gap: 16 }}>
        {/* LEFT: pipeline spine */}
        <Panel style={{ padding: 16 }}>
          <Eyebrow style={{ color: ORANGE }}>Production Pipeline</Eyebrow>
          <div style={{ marginTop: 12 }}>
            {r.stages.map((s, i) => (
              <div key={s.stage}>
                <button onClick={() => setSel(s.stage)}
                  style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", cursor: "pointer",
                    background: sel === s.stage ? "rgba(255,138,61,0.12)" : "transparent",
                    border: "none", borderRadius: 8, padding: "7px 8px", textAlign: "left" }}>
                  <span style={{ width: 10, height: 10, borderRadius: "50%", background: DOT[s.status] || GREY,
                    boxShadow: s.status === "done" ? `0 0 8px ${TEAL}` : "none" }} />
                  <span style={{ fontSize: 13.5, flex: 1, color: sel === s.stage ? "#fff" : "inherit" }}>{STAGE_LABEL[s.stage]}</span>
                  <span className="mono" style={{ fontSize: 10, opacity: 0.5 }}>{s.status === "done" ? pct(s.confidence) : ""}</span>
                </button>
                {i < r.stages.length - 1 && <div style={{ marginLeft: 13, width: 1, height: 8, background: "rgba(255,255,255,0.12)" }} />}
              </div>
            ))}
          </div>
        </Panel>

        {/* CENTER: selected stage + confidence + cost + provider */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Panel style={{ padding: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <Eyebrow style={{ color: ORANGE }}>{STAGE_LABEL[stage.stage]} Director</Eyebrow>
              <span className="mono" style={{ fontSize: 11, color: DOT[stage.status] }}>● {stage.status}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginTop: 14 }}>
              {[["Confidence", stage.status === "done" ? pct(stage.confidence) : "—"],
                ["Cost", `$${stage.cost}`], ["Provider", stage.provider]].map(([k, v]) => (
                <div key={k}>
                  <div style={{ fontSize: 11, opacity: 0.5 }}>{k}</div>
                  <div className="mono" style={{ fontSize: 14, marginTop: 2 }}>{v}</div>
                </div>
              ))}
            </div>
            <div style={{ fontSize: 11.5, opacity: 0.45, marginTop: 12 }}>
              artifact: {stage.has_artifact ? "✓ produced" : "— not yet"}
            </div>
          </Panel>

          {/* per-stage confidence + cost bars */}
          <Panel style={{ padding: 18 }}>
            <Eyebrow style={{ color: ORANGE }}>Confidence & Cost by Department</Eyebrow>
            <div style={{ marginTop: 12 }}>
              {r.stages.filter((s) => s.has_artifact).map((s) => (
                <div key={s.stage} style={{ display: "flex", alignItems: "center", gap: 10, padding: "5px 0", fontSize: 12.5 }}>
                  <span style={{ width: 78, opacity: 0.7 }}>{STAGE_LABEL[s.stage]}</span>
                  <div style={{ flex: 1, height: 6, borderRadius: 4, background: "rgba(255,255,255,0.07)", overflow: "hidden" }}>
                    <div style={{ width: pct(s.confidence), height: "100%", background: s.confidence >= 0.9 ? TEAL : AMBER }} />
                  </div>
                  <span className="mono" style={{ width: 38, textAlign: "right", opacity: 0.6, fontSize: 11 }}>{pct(s.confidence)}</span>
                  <span className="mono" style={{ width: 42, textAlign: "right", opacity: 0.45, fontSize: 11 }}>${s.cost}</span>
                </div>
              ))}
            </div>
          </Panel>

          {/* provider monitor */}
          <Panel style={{ padding: 18 }}>
            <Eyebrow style={{ color: ORANGE }}>Provider Monitor</Eyebrow>
            <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 8 }}>
              {r.stages.filter((s) => s.has_artifact).map((s) => (
                <span key={s.stage} className="mono" style={{ fontSize: 11, padding: "4px 10px", borderRadius: 999,
                  background: "rgba(255,255,255,0.05)" }}>{STAGE_LABEL[s.stage]}: <b style={{ color: TEAL }}>{s.provider}</b></span>
              ))}
            </div>
          </Panel>
        </div>

        {/* RIGHT: directors + queue + memory + artifacts */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Panel style={{ padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <Eyebrow style={{ color: ORANGE }}>Directors</Eyebrow>
              <span className="mono" style={{ fontSize: 11, color: TEAL }}>{r.directors.healthy}/{r.directors.total}</span>
            </div>
            <div style={{ marginTop: 10 }}>
              {r.directors.roster.map((d) => (
                <div key={d.name} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0", fontSize: 12.5 }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: d.healthy ? TEAL : GREY }} />
                  <span style={{ flex: 1, textTransform: "capitalize" }}>{d.name}</span>
                  <span className="mono" style={{ fontSize: 10, opacity: 0.4 }}>{d.source}</span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel style={{ padding: 16 }}>
            <Eyebrow style={{ color: ORANGE }}>Artifacts</Eyebrow>
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 4 }}>
              {Object.entries(r.artifacts).map(([k, ok]) => (
                <div key={k} style={{ fontSize: 12.5, display: "flex", gap: 8 }}>
                  <span style={{ opacity: ok ? 1 : 0.3 }}>{ok ? "📄" : "▫"}</span>
                  <span style={{ textTransform: "capitalize", opacity: ok ? 0.85 : 0.4 }}>{k}</span>
                </div>
              ))}
            </div>
            {r.publish_targets.length > 0 && (
              <div style={{ marginTop: 10, fontSize: 10.5, opacity: 0.5 }}>→ {r.publish_targets.join(" · ")}</div>
            )}
          </Panel>

          <Panel style={{ padding: 16 }}>
            <Eyebrow style={{ color: ORANGE }}>Content Memory</Eyebrow>
            <div className="mono" style={{ fontSize: 11, opacity: 0.5, marginTop: 4 }}>{r.memory.count} published</div>
            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 3 }}>
              {(r.memory.recent || []).slice(0, 6).map((t, i) => (
                <div key={i} style={{ fontSize: 11.5, opacity: 0.6 }}>· {t}</div>
              ))}
              {r.memory.recent?.length === 0 && <div style={{ fontSize: 11.5, opacity: 0.35 }}>nothing published yet</div>}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
