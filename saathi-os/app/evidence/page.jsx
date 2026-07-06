"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchEvidenceStats, fetchEvidence } from "@/lib/api";

const ACCENT = "#6E72F0";        // Memory colour — Evidence is the company's memory
const TEAL = "#00BFA5";
const AMBER = "#E8B84B";
const RED = "#FF5A5A";

const DEPT_LABEL = {
  ai_studio: "AI Studio", pielts: "PIELTS", hcg: "HCG Signal",
  cafeteria: "Cafeteria", travel: "Travel", telegram: "Telegram",
};
const DEPT_COLOR = {
  ai_studio: "#FF8A3D", pielts: "#6C3FCF", hcg: "#FF5A5A",
  cafeteria: "#4FD07A", travel: "#5FC8FF", telegram: "#5FC8FF",
};

export default function EvidenceDashboard() {
  const [data, setData] = useState(null);
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState(null);
  const load = () => {
    fetchEvidenceStats(30).then(setData).catch((e) => setErr(String(e)));
    fetchEvidence({ limit: 40 }).then((d) => setRows(d.evidence || [])).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  if (err && !data) return <div className="only-desktop" style={{ padding: 40, opacity: 0.6 }}>Evidence Service offline — {err}</div>;
  if (!data) return <div className="only-desktop" style={{ padding: 40, opacity: 0.5 }}>Reading the company's memory…</div>;

  const depts = Object.entries(data.stats.departments || {});
  const pct = (x) => `${Math.round((x || 0) * 100)}%`;
  const eps = data.studio_episodes || [];
  const confColor = (c) => (c >= 0.9 ? TEAL : c >= 0.6 ? AMBER : RED);

  return (
    <div className="only-desktop" style={{ maxWidth: 1120, margin: "0 auto", paddingBottom: 60 }}>
      <Eyebrow style={{ color: ACCENT }}>SaathiOS · Evidence</Eyebrow>
      <div style={{ fontSize: 28, fontWeight: 600, margin: "4px 0 4px" }}>The company's shared memory</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 18 }}>
        Every department writes one schema · the CEO queries one truth · {data.total} records total (last 30 days).
      </div>

      {/* department roll-up */}
      <div style={{ display: "flex", gap: 12, marginBottom: 18, flexWrap: "wrap" }}>
        {depts.length === 0 && <div style={{ opacity: 0.4, fontSize: 13 }}>No evidence yet — run a production.</div>}
        {depts.map(([d, v]) => (
          <div key={d} className="glass" style={{ padding: "12px 18px", borderRadius: 12, minWidth: 150,
            borderLeft: `3px solid ${DEPT_COLOR[d] || ACCENT}` }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: DEPT_COLOR[d] || ACCENT }}>{DEPT_LABEL[d] || d}</div>
            <div style={{ fontSize: 22, fontWeight: 600, marginTop: 4 }}>{v.count}</div>
            <div className="mono" style={{ fontSize: 10.5, opacity: 0.55, marginTop: 2 }}>
              ${v.cost} · conf {pct(v.avg_confidence)}
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* AI Studio episodes — what changed */}
        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color: ACCENT }}>AI Studio · latest episodes</Eyebrow>
          <div style={{ marginTop: 12 }}>
            {eps.length === 0 && <div style={{ opacity: 0.4, fontSize: 13 }}>none yet</div>}
            {eps.map((e) => (
              <div key={e.id} style={{ padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                  <span><b>{e.episode || "—"}</b> <span style={{ opacity: 0.45 }}>· {e.director}</span></span>
                  <span className="mono" style={{ color: confColor(e.confidence) }}>{pct(e.confidence)}</span>
                </div>
                <div className="mono" style={{ fontSize: 10.5, opacity: 0.5, marginTop: 2 }}>
                  {e.provider} · ${e.cost} · {e.status}
                  {e.metrics?.publish_targets?.length > 0 && ` · → ${e.metrics.publish_targets.slice(0, 4).join(" ")}`}
                </div>
                {e.recommendation && <div style={{ fontSize: 11, color: AMBER, marginTop: 3 }}>💡 {e.recommendation}</div>}
              </div>
            ))}
          </div>
          <div style={{ fontSize: 11, opacity: 0.4, marginTop: 12 }}>
            Recommendations arrive once the Learning Director is wired — evidence is being collected now.
          </div>
        </Panel>

        {/* raw evidence stream */}
        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color: ACCENT }}>Evidence stream (all departments)</Eyebrow>
          <div style={{ marginTop: 12, maxHeight: 460, overflowY: "auto" }}>
            {rows.map((e) => (
              <div key={e.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0",
                fontSize: 12, borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: DEPT_COLOR[e.department] || ACCENT }} />
                <span style={{ width: 70, opacity: 0.7 }}>{DEPT_LABEL[e.department] || e.department}</span>
                <span style={{ flex: 1, opacity: 0.55 }}>{e.episode} · {e.director}</span>
                <span className="mono" style={{ opacity: 0.5, fontSize: 10.5 }}>{pct(e.confidence)}</span>
              </div>
            ))}
            {rows.length === 0 && <div style={{ opacity: 0.4, fontSize: 13 }}>empty</div>}
          </div>
        </Panel>
      </div>
    </div>
  );
}
