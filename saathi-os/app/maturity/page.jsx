"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchMaturity } from "@/lib/api";

const GOLD = "#E8B84B";

function Bar({ label, pct, hint }) {
  const c = pct >= 80 ? "#4FD07A" : pct >= 40 ? GOLD : "#FF7A5A";
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14, marginBottom: 6 }}>
        <span>{label}</span><span style={{ color: c, fontWeight: 600 }}>{pct}%</span>
      </div>
      <div style={{ height: 8, borderRadius: 6, background: "rgba(255,255,255,0.06)" }}>
        <div style={{ width: `${pct}%`, height: "100%", borderRadius: 6, background: c,
          transition: "width .6s ease" }} />
      </div>
      {hint && <div style={{ fontSize: 11, opacity: 0.4, marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div style={{ flex: "1 1 120px", padding: "12px 14px", borderRadius: 12,
      background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
      <div style={{ fontSize: 12, opacity: 0.55 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 600, marginTop: 2 }}>{value}</div>
    </div>
  );
}

export default function Maturity() {
  const [m, setM] = useState(null);
  useEffect(() => {
    const tick = () => fetchMaturity().then(setM).catch(() => {});
    tick(); const id = setInterval(tick, 15000); return () => clearInterval(id);
  }, []);
  if (!m) return <div className="only-desktop" style={{ maxWidth: 900, margin: "40px auto", opacity: 0.5 }}>loading…</div>;

  return (
    <div className="only-desktop" style={{ maxWidth: 900, margin: "0 auto" }}>
      <Eyebrow style={{ color: GOLD }}>Platform Maturity</Eyebrow>
      <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 6px" }}>Where SaathiAI actually is</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 22 }}>{m.note}</div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <Panel style={{ padding: 20 }}>
          <Bar label="Infrastructure" pct={m.infrastructure} hint="built + deployed" />
          <Bar label="Applications" pct={m.applications} hint="apps actually using the platform" />
          <Bar label="Real Data" pct={m.real_data} hint="authenticated connectors, not mock" />
          <Bar label="Learning Confidence" pct={m.learning_confidence} hint="verified selectors / patterns" />
          <Bar label="Automation Success" pct={m.automation_success} hint="flight-recorder success rate (24h)" />
        </Panel>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignContent: "flex-start" }}>
          <Stat label="Revenue Today" value={m.revenue_today ? `$${m.revenue_today}` : "$0"} />
          <Stat label="Episodes Today" value={m.episodes_today} />
          <Stat label="Runs Today" value={m.runs_today} />
          <Stat label="Knowledge Added" value={m.knowledge_added} />
          <Stat label="Human Overrides" value={m.human_overrides} />
        </div>
      </div>

      <div style={{ marginTop: 22, padding: "14px 18px", borderRadius: 12,
        background: "rgba(232,184,75,0.08)", border: `1px solid ${GOLD}44`, fontSize: 13, opacity: 0.85 }}>
        <b style={{ color: GOLD }}>Operating rule:</b> before adding new infrastructure, prove at least one
        application improved from real data. Decide ≥1 · Automate ≥1 · Learn ≥1 · Earn ≥1.
      </div>
    </div>
  );
}
