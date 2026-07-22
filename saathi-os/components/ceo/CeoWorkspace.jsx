"use client";
// M14 CEO OS workspace — real /api/v1/ceo/* only. No production mock data.
// Every value shows its evidence tier (observed/calculated/inferred/forecast/
// recommended/unavailable). Missions create + execute through M10; decisions
// require the user; unavailable KPIs say so honestly.
import { useCallback, useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";

const TIER_COLOR = {
  observed: "#4fe3cb", calculated: "#5ea1ff", inferred: "#ffb04f",
  forecast: "#c9b6ff", recommended: "#ffb04f", unavailable: "#8fa0c4",
};
const SEV_COLOR = { critical: "#ff5a5a", warning: "#ffb04f", info: "#8fa0c4" };

const S = {
  wrap: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, padding: 16,
          color: "#e8ecf5", height: "calc(100vh - 60px)", overflowY: "auto" },
  panel: { background: "rgba(255,255,255,.03)", border: "1px solid rgba(255,255,255,.08)",
           borderRadius: 12, padding: 14, overflowY: "auto" },
  head: { fontSize: 11, opacity: .6, letterSpacing: ".12em", marginBottom: 10,
          textTransform: "uppercase" },
  row: { padding: "7px 9px", borderRadius: 8, background: "rgba(255,255,255,.03)",
         marginBottom: 6, fontSize: 13 },
  tier: (t) => ({ display: "inline-block", padding: "1px 7px", borderRadius: 999,
         fontSize: 9, letterSpacing: ".05em", background: `${TIER_COLOR[t] || "#8fa0c4"}22`,
         color: TIER_COLOR[t] || "#8fa0c4", border: `1px solid ${TIER_COLOR[t] || "#8fa0c4"}55`,
         marginRight: 6 }),
  btn: (c = "#4fe3cb") => ({ background: `${c}18`, color: c, border: `1px solid ${c}55`,
         borderRadius: 8, padding: "4px 10px", fontSize: 12, cursor: "pointer" }),
};

export default function CeoWorkspace() {
  const [brief, setBrief] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [kpis, setKpis] = useState([]);
  const [risks, setRisks] = useState([]);
  const [decisions, setDecisions] = useState([]);
  const [finance, setFinance] = useState(null);
  const [recs, setRecs] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [b, p, k, r, d, f, rc] = await Promise.all([
        afetch(`${API_BASE}/api/v1/ceo/brief`, { cache: "no-store" }),
        afetch(`${API_BASE}/api/v1/ceo/portfolio`, { cache: "no-store" }),
        afetch(`${API_BASE}/api/v1/ceo/kpis`, { cache: "no-store" }),
        afetch(`${API_BASE}/api/v1/ceo/risks`, { cache: "no-store" }),
        afetch(`${API_BASE}/api/v1/ceo/decisions`, { cache: "no-store" }),
        afetch(`${API_BASE}/api/v1/ceo/finance/summary`, { cache: "no-store" }),
        afetch(`${API_BASE}/api/v1/ceo/agent/recommendations`, { cache: "no-store" }),
      ]);
      setBrief(await b.json());
      setPortfolio(await p.json());
      setKpis((await k.json()).kpis || []);
      setRisks((await r.json()).risks || []);
      setDecisions((await d.json()).decisions || []);
      setFinance(await f.json());
      setRecs(await rc.json());
      setError("");
    } catch { setError("CEO OS backend unreachable — is the SaathiAI server running?"); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function resolveDecision(did, status) {
    await afetch(`${API_BASE}/api/v1/ceo/decisions/${did}/resolve`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    load();
  }
  async function riskToMission(rid) {
    await afetch(`${API_BASE}/api/v1/ceo/risks/${rid}/to-mission`, { method: "POST" });
    load();
  }

  return (
    <div style={S.wrap} role="region" aria-label="CEO OS">
      {error && <div style={{ gridColumn: "1/3", color: "#ff8c8c" }} role="alert">{error}</div>}

      {/* Daily Brief */}
      <section style={S.panel}>
        <div style={S.head}>Daily Brief {brief && `(${brief.items?.length || 0} items)`}</div>
        {(brief?.items || []).map((it, i) => (
          <div key={i} style={S.row}>
            <span style={S.tier(it.tier)}>{it.tier}</span>
            <b style={{ opacity: .6, fontSize: 11 }}>{it.section}</b><br />
            {it.text}
            {it.evidence?.length > 0 && (
              <div style={{ opacity: .45, fontSize: 11, marginTop: 3 }}>
                evidence: {it.evidence.join(", ")}</div>)}
          </div>))}
        {(brief?.items || []).length === 0 && <div style={{ opacity: .5 }}>No brief items — register goals, KPIs, risks.</div>}
      </section>

      {/* KPIs */}
      <section style={S.panel}>
        <div style={S.head}>KPI Scorecard</div>
        {kpis.map((k) => (
          <div key={k.kpi_id} style={S.row}>
            <span style={S.tier(k.evidence_tier)}>{k.evidence_tier}</span>
            {k.name}: {k.available
              ? <b>{k.value} {k.unit} {k.pct_to_target != null ? `· ${k.pct_to_target}% of target` : ""} · {k.trend}</b>
              : <span style={{ opacity: .6 }}>No verified data source.</span>}
          </div>))}
        {kpis.length === 0 && <div style={{ opacity: .5 }}>No KPIs defined.</div>}
      </section>

      {/* Decisions */}
      <section style={S.panel}>
        <div style={S.head}>Decisions awaiting you</div>
        {decisions.filter((d) => d.status === "awaiting_decision").map((d) => (
          <div key={d.id} style={S.row}>
            {d.question}
            <div style={{ marginTop: 6 }}>
              <button style={{ ...S.btn(), marginRight: 6 }}
                      onClick={() => resolveDecision(d.id, "approved")}>Approve</button>
              <button style={S.btn("#ff5a5a")}
                      onClick={() => resolveDecision(d.id, "rejected")}>Reject</button>
            </div>
          </div>))}
        {decisions.filter((d) => d.status === "awaiting_decision").length === 0 &&
          <div style={{ opacity: .5 }}>No decisions awaiting.</div>}
      </section>

      {/* Risks */}
      <section style={S.panel}>
        <div style={S.head}>Risk Register</div>
        {risks.map((r) => (
          <div key={r.id} style={S.row}>
            <span style={S.tier("inferred")}>score {r.score}</span>
            {r.title} <span style={{ opacity: .5 }}>({r.category})</span>
            <button style={{ ...S.btn("#ffb04f"), marginLeft: 8, padding: "2px 8px", fontSize: 11 }}
                    onClick={() => riskToMission(r.id)}>→ mission</button>
          </div>))}
        {risks.length === 0 && <div style={{ opacity: .5 }}>No open risks.</div>}
      </section>

      {/* Finance */}
      <section style={S.panel}>
        <div style={S.head}>Financial (actuals only)</div>
        {finance ? (
          <>
            <div style={S.row}><span style={S.tier("observed")}>actual</span>
              Revenue ${finance.actual_revenue} · Expense ${finance.actual_expense} · Net ${finance.actual_net}</div>
            <div style={{ opacity: .5, fontSize: 11, marginTop: 4 }}>{finance.note}</div>
          </>) : <div style={{ opacity: .5 }}>—</div>}
      </section>

      {/* System health + CEO agent */}
      <section style={S.panel}>
        <div style={S.head}>System Health</div>
        {portfolio?.system_health && (
          <div style={S.row}>
            storage: {portfolio.system_health.storage} · {portfolio.system_health.active_agent_runs} active runs ·
            {" "}{portfolio.system_health.studio_projects} studio projects
          </div>)}
        <div style={{ ...S.head, marginTop: 14 }}>CEO Agent (bounded)</div>
        {(recs?.recommendations || []).map((r, i) => (
          <div key={i} style={S.row}>
            <span style={S.tier("recommended")}>recommend</span>{r.objective}
          </div>))}
        {recs?.cannot_do && (
          <div style={{ opacity: .45, fontSize: 11, marginTop: 6 }}>
            Agent cannot: {recs.cannot_do.slice(0, 4).join(", ")}…</div>)}
      </section>
    </div>
  );
}
