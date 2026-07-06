"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { runLearningAnalysis, fetchRecommendations, decideRecommendation } from "@/lib/api";

const PURPLE = "#9B6BFF";
const TEAL = "#00BFA5";
const RED = "#FF5A5A";
const AMBER = "#E8B84B";

const CAT = {
  technical: { label: "Technical", color: "#7CF5E4", note: "how SaathiAI improves" },
  educational: { label: "Educational", color: "#9B6BFF", note: "how Mr. Yeti teaches better" },
  business: { label: "Business", color: "#E8B84B", note: "how each company operates better" },
};
const PRI = { high: RED, medium: AMBER, low: "#5b6478" };

export default function LearningDirectors() {
  const [recs, setRecs] = useState([]);
  const [counts, setCounts] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [filter, setFilter] = useState("");

  const load = () => fetchRecommendations({ category: filter }).then((d) => {
    setRecs(d.recommendations || []); setCounts(d.counts || {});
  }).catch((e) => setErr(String(e)));
  const analyze = () => { setBusy(true); runLearningAnalysis().then(load).catch((e) => setErr(String(e))).finally(() => setBusy(false)); };
  const decide = async (id, accept) => {
    try { await decideRecommendation(id, accept); load(); }
    catch (e) { setErr(`Decision needs login — ${e}`); }
  };
  useEffect(() => { load(); }, [filter]);

  const pct = (x) => `${Math.round((x || 0) * 100)}%`;
  const pending = recs.filter((r) => r.status === "pending");

  return (
    <div className="only-desktop" style={{ maxWidth: 980, margin: "0 auto", paddingBottom: 60 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 6 }}>
        <div>
          <Eyebrow style={{ color: PURPLE }}>SaathiOS · Learning</Eyebrow>
          <div style={{ fontSize: 28, fontWeight: 600, marginTop: 4 }}>Learning Directors</div>
        </div>
        <button onClick={analyze} disabled={busy}
          style={{ padding: "10px 20px", borderRadius: 12, border: "none", cursor: "pointer",
            fontWeight: 600, color: "#fff", background: PURPLE, opacity: busy ? 0.6 : 1 }}>
          {busy ? "Analysing evidence…" : "🔎 Run Analysis"}</button>
      </div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 16 }}>
        Three systems read the Evidence Store and <b>recommend</b> — they never edit. You decide; accepted
        proposals ship through the Prompt Registry. Nothing changes automatically.
      </div>

      {/* category legend / filter */}
      <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <button onClick={() => setFilter("")} style={chip(!filter, "#8FA0C4")}>All</button>
        {Object.entries(CAT).map(([k, c]) => (
          <button key={k} onClick={() => setFilter(k)} style={chip(filter === k, c.color)}>
            {c.label} <span style={{ opacity: 0.6, fontSize: 10.5 }}>· {c.note}</span>
          </button>
        ))}
        <div style={{ marginLeft: "auto", fontSize: 11.5, opacity: 0.55, alignSelf: "center" }} className="mono">
          pending {counts.pending || 0} · accepted {counts.accepted || 0} · rejected {counts.rejected || 0}
        </div>
      </div>

      {err && <div style={{ fontSize: 12, color: RED, marginBottom: 10 }}>{err}</div>}

      {recs.length === 0 && (
        <Panel style={{ padding: 28, textAlign: "center" }}>
          <div style={{ fontSize: 15, opacity: 0.7 }}>No recommendations.</div>
          <div style={{ fontSize: 12.5, opacity: 0.45, marginTop: 6 }}>
            When every Director is above the quality bar, the Learning layer stays silent — that's healthy.
            Run analysis after more production evidence accumulates.
          </div>
        </Panel>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {recs.map((r) => {
          const c = CAT[r.category] || { label: r.category, color: PURPLE };
          const decided = r.status !== "pending";
          return (
            <Panel key={r.id} style={{ padding: 16, opacity: decided ? 0.6 : 1,
              borderLeft: `3px solid ${c.color}` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <span className="mono" style={{ fontSize: 10, padding: "2px 8px", borderRadius: 999,
                  background: `${c.color}22`, color: c.color }}>{c.label}</span>
                <span className="mono" style={{ fontSize: 10, padding: "2px 8px", borderRadius: 999,
                  background: `${PRI[r.priority]}22`, color: PRI[r.priority] }}>{r.priority}</span>
                <span style={{ fontSize: 11.5, opacity: 0.5 }}>{r.department} · {r.affected_director}</span>
                <span className="mono" style={{ marginLeft: "auto", fontSize: 11, color: r.confidence >= 0.8 ? TEAL : AMBER }}>
                  {pct(r.confidence)} confidence</span>
              </div>
              <div style={{ fontSize: 13.5, marginBottom: 4 }}><b>Problem:</b> {r.problem}</div>
              <div style={{ fontSize: 13.5, opacity: 0.85 }}><b>Recommend:</b> {r.recommendation}</div>
              <div style={{ fontSize: 11.5, opacity: 0.5, marginTop: 6, display: "flex", gap: 14, flexWrap: "wrap" }}>
                {r.expected_improvement && <span>📈 {r.expected_improvement}</span>}
                <span>cost {r.estimated_cost}</span><span>risk {r.risk}</span>
                {r.evidence?.length > 0 && <span>{r.evidence.length} evidence rows</span>}
              </div>
              {decided ? (
                <div style={{ marginTop: 10, fontSize: 12, color: r.status === "accepted" ? TEAL : RED }}>
                  ● {r.status}{r.implemented_in ? ` → ${r.implemented_in}` : ""}
                </div>
              ) : (
                <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                  <button onClick={() => decide(r.id, true)} style={btn(TEAL)}>✓ Accept</button>
                  <button onClick={() => decide(r.id, false)} style={btn(RED, true)}>✕ Reject</button>
                </div>
              )}
            </Panel>
          );
        })}
      </div>
      {pending.length > 0 && (
        <div style={{ fontSize: 11.5, opacity: 0.4, marginTop: 14 }}>
          {pending.length} pending · accepted proposals become new prompt versions in the AI Lab (you ship them).
        </div>
      )}
    </div>
  );
}

const chip = (active, color) => ({
  padding: "6px 12px", borderRadius: 999, cursor: "pointer", fontSize: 12, fontWeight: 600,
  border: `1px solid ${color}${active ? "" : "44"}`, background: active ? `${color}22` : "transparent",
  color: active ? color : "inherit",
});
const btn = (color, outline) => ({
  padding: "7px 16px", borderRadius: 10, cursor: "pointer", fontWeight: 600, fontSize: 12.5,
  border: outline ? `1px solid ${color}` : "none", background: outline ? "transparent" : color,
  color: outline ? color : "#fff",
});
