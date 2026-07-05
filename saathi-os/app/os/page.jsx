"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchCeoOs } from "@/lib/api";

const GOLD = "#E8B84B";
const RULE = ["Decide", "Automate", "Learn", "Earn"];

function Card({ icon, title, children }) {
  return (
    <Panel style={{ padding: 18 }}>
      <div style={{ fontSize: 12, opacity: 0.55, marginBottom: 8 }}>{icon} {title}</div>
      {children}
    </Panel>
  );
}

export default function OperatingSystem() {
  const [d, setD] = useState(null);
  useEffect(() => {
    const t = () => fetchCeoOs().then(setD).catch(() => {});
    t(); const id = setInterval(t, 10000); return () => clearInterval(id);
  }, []);
  if (!d) return <div className="only-desktop" style={{ maxWidth: 1000, margin: "40px auto", opacity: 0.5 }}>loading…</div>;

  const met = d.rule.met || {};
  const f = (d.studio && d.studio.factory) || {};
  const runtime = f.avg_runtime_ms ? `${Math.floor(f.avg_runtime_ms / 60000)}m ${Math.round((f.avg_runtime_ms % 60000) / 1000)}s` : "—";
  return (
    <div className="only-desktop" style={{ maxWidth: 1000, margin: "0 auto" }}>
      <div style={{ fontSize: 30, fontWeight: 600, margin: "6px 0 4px" }}>{d.greeting} 👋</div>
      <div style={{ fontSize: 13, opacity: 0.45, marginBottom: 20 }}>Today's Operating System · what needs your attention</div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 14 }}>
        <Card icon="🎯" title="Dream">
          <div style={{ fontSize: 28, fontWeight: 600 }}>{d.dream.progress_pct}%</div>
          <div style={{ fontSize: 12, color: d.dream.delta >= 0 ? "#4FD07A" : "#FF5A5A" }}>
            {d.dream.delta >= 0 ? "▲" : "▼"} {Math.abs(d.dream.delta)}%
          </div>
        </Card>
        <Card icon="⭐" title="Rule">
          <div style={{ fontSize: 28, fontWeight: 600 }}>{d.rule.score} / {d.rule.of}</div>
          <div style={{ display: "flex", gap: 8, marginTop: 6, fontSize: 12, flexWrap: "wrap" }}>
            {RULE.map((r) => <span key={r} style={{ opacity: met[r] || met[r.toLowerCase()] ? 1 : 0.35 }}>
              {met[r] || met[r.toLowerCase()] ? "☑" : "☐"} {r}</span>)}
          </div>
        </Card>
        <Card icon="🤖" title="Automation">
          <div style={{ fontSize: 28, fontWeight: 600 }}>{d.automation.workflows} <span style={{ fontSize: 14, opacity: .5 }}>workflows</span></div>
          <div style={{ fontSize: 12, opacity: 0.6 }}>health {d.automation.health}% · {d.automation.runs_today} runs · agent {d.automation.agent_online ? "🟢" : "🔴"}</div>
        </Card>
        <Card icon="🧠" title="Learning">
          <div style={{ fontSize: 28, fontWeight: 600 }}>{d.learning.episodes_today} <span style={{ fontSize: 14, opacity: .5 }}>episodes</span></div>
          <div style={{ fontSize: 12, opacity: 0.6 }}>{d.learning.verified_improvements} verified · {d.learning.knowledge_added} taught</div>
        </Card>
        <Card icon="💰" title="Revenue">
          <div style={{ fontSize: 13, lineHeight: 1.9 }}>
            <div>Cafeteria <b>NPR {d.revenue.cafeteria || 0}</b></div>
            <div>AI Studio <b>${d.revenue.ai_studio || 0}</b></div>
            <div>Trading <b style={{ color: "#4FD07A" }}>paper {d.revenue.trading_pct || 0}%</b></div>
          </div>
        </Card>
        <Card icon="⚠️" title="Needs You">
          {d.needs_you.length === 0
            ? <div style={{ opacity: 0.4, fontSize: 13 }}>nothing pending 🎉</div>
            : d.needs_you.map((n, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, padding: "4px 0" }}>
                <span>{n.label}</span><span style={{ color: GOLD }}>{n.cta}</span>
              </div>))}
        </Card>
      </div>

      <Panel style={{ padding: 18, marginTop: 14 }}>
        <div style={{ fontSize: 12, opacity: 0.55, marginBottom: 12 }}>🏭 Today's Factory</div>
        {Object.keys(f.latest_stages || {}).length > 0 && (
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 16,
            paddingBottom: 14, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
            {["research", "script", "voice", "assets", "render", "metadata", "gate", "publish", "analytics", "learning"]
              .filter((s) => s in f.latest_stages).map((s) => (
              <span key={s} style={{ fontSize: 12, opacity: 0.85 }}>
                {f.latest_stages[s] ? "✅" : "❌"} {s}
              </span>
            ))}
          </div>
        )}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 14, rowGap: 16 }}>
          {[
            ["Runs", f.runs ?? 0],
            ["Published", f.published ?? 0],
            ["Waiting", f.waiting_approval ?? 0],
            ["Blocked", f.blocked ?? 0, (f.blocked ?? 0) > 0 ? "#FF5A5A" : null],
            ["Avg Confidence", `${Math.round((f.avg_confidence || 0) * 100)}%`],
            ["Avg Cost", `$${(f.avg_cost || 0).toFixed(2)}`],
            ["Avg Runtime", runtime],
            ["Learning Episodes", d.learning.episodes_today],
            ["Verified Insights", d.learning.verified_improvements],
            ["Revenue Today", `$${d.revenue.ai_studio || 0}`],
          ].map(([label, val, col]) => (
            <div key={label}>
              <div style={{ fontSize: 22, fontWeight: 600, color: col || "inherit" }}>{val}</div>
              <div style={{ fontSize: 11, opacity: 0.5 }}>{label}</div>
            </div>
          ))}
        </div>
      </Panel>

      <input placeholder="Ask Saathi…" style={{ width: "100%", marginTop: 18, padding: "12px 16px",
        borderRadius: 24, border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)",
        color: "inherit", fontSize: 14 }} />
    </div>
  );
}
