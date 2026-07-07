"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchAutomationCredits, fetchProductionPlan, fetchAutomationSettings, setApprovalMode } from "@/lib/api";

const ORANGE = "#FF8A3D", TEAL = "#00BFA5", AMBER = "#E8B84B", RED = "#FF5A5A", GREY = "#5b6478";

export default function ProductionAutomation() {
  const [creds, setCreds] = useState([]);
  const [plan, setPlan] = useState(null);
  const [settings, setSettings] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const loadFast = () => {
    fetchAutomationCredits().then((d) => setCreds(d.providers || [])).catch((e) => setErr(String(e)));
    fetchAutomationSettings().then(setSettings).catch(() => {});
  };
  useEffect(() => { loadFast(); }, []);
  const runPlan = () => { setBusy(true); fetchProductionPlan().then((d) => setPlan(d.production_plan)).catch((e) => setErr(String(e))).finally(() => setBusy(false)); };
  const setMode = (m) => setApprovalMode(m).then(loadFast).catch((e) => setErr(String(e)));
  const pct = (x) => `${Math.round((x || 0) * 100)}%`;

  return (
    <div className="page" style={{ maxWidth: 1000, margin: "0 auto", paddingBottom: 60 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <Eyebrow style={{ color: ORANGE }}>SaathiOS · Production Automation</Eyebrow>
          <div style={{ fontSize: 28, fontWeight: 600, marginTop: 4 }}>Saathi decides who generates today</div>
        </div>
        <button onClick={runPlan} disabled={busy}
          style={{ padding: "10px 20px", borderRadius: 12, border: "none", cursor: "pointer",
            fontWeight: 600, color: "#fff", background: ORANGE, opacity: busy ? 0.6 : 1 }}>
          {busy ? "Planning…" : "▶ Build Production Plan"}</button>
      </div>
      <div style={{ fontSize: 13, opacity: 0.5, margin: "6px 0 16px" }}>
        Credit-aware, cost-optimised provider choice per scene · character verification · quality gate · approval mode.
      </div>
      {err && <div style={{ fontSize: 12, color: RED, marginBottom: 10 }}>{err}</div>}

      {settings && (
        <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center" }}>
          <span style={{ fontSize: 12, opacity: 0.6 }}>Approval mode:</span>
          {settings.modes.map((m) => (
            <button key={m} onClick={() => setMode(m)} style={{ padding: "6px 14px", borderRadius: 999,
              cursor: "pointer", fontSize: 12, fontWeight: 600, textTransform: "capitalize",
              border: `1px solid ${settings.approval_mode === m ? ORANGE : ORANGE + "44"}`,
              background: settings.approval_mode === m ? ORANGE + "22" : "transparent",
              color: settings.approval_mode === m ? ORANGE : "inherit" }}>{m}</button>
          ))}
        </div>
      )}

      <Panel style={{ padding: 18, marginBottom: 16 }}>
        <Eyebrow style={{ color: ORANGE }}>Credit Manager · today</Eyebrow>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, marginTop: 12 }}>
          {creds.map((p) => {
            const active = p.status === "active";
            return (
              <div key={p.name} className="glass" style={{ padding: 12, borderRadius: 12,
                borderLeft: `3px solid ${active ? TEAL : GREY}`, opacity: active ? 1 : 0.6 }}>
                <div style={{ fontSize: 13, fontWeight: 600, textTransform: "capitalize" }}>{p.name.replace("_", " ")}</div>
                <div className="mono" style={{ fontSize: 11, opacity: 0.6, marginTop: 3 }}>
                  {p.unlimited ? "∞ unlimited" : `${p.remaining}/${p.daily} credits`} · {p.kind}
                </div>
                <div className="mono" style={{ fontSize: 10.5, marginTop: 3,
                  color: active ? TEAL : p.status === "no_key" ? AMBER : GREY }}>
                  {p.status === "no_key" ? "needs API key" : p.status} · Q{p.quality_tier} · ${p.cost}/clip
                </div>
              </div>
            );
          })}
        </div>
      </Panel>

      {plan && (
        <Panel style={{ padding: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <Eyebrow style={{ color: ORANGE }}>Production Plan · {plan.episode}</Eyebrow>
            <span className="mono" style={{ fontSize: 12,
              color: plan.action === "publish" ? TEAL : plan.action.includes("hold") ? AMBER : RED }}>
              ● {plan.action}</span>
          </div>
          <div style={{ display: "flex", gap: 16, marginTop: 10, flexWrap: "wrap", fontSize: 12.5 }}>
            <span>Scenes <b>{plan.scene_count}</b></span>
            <span>Cost <b>${plan.est_cost}</b></span>
            <span>Character <b style={{ color: plan.character.avg_score >= 0.85 ? TEAL : AMBER }}>{pct(plan.character.avg_score)}</b></span>
            <span>Quality <b style={{ color: plan.quality_gate.score >= 0.9 ? TEAL : AMBER }}>{pct(plan.quality_gate.score)}</b></span>
            <span>Providers <b>{Object.entries(plan.providers_used).map(([k, v]) => `${k}×${v}`).join(", ")}</b></span>
          </div>

          <div style={{ fontSize: 11, opacity: 0.5, marginTop: 14 }}>SCENE → PROVIDER</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
            {plan.assignments.map((a) => (
              <span key={a.scene} className="mono" style={{ fontSize: 11, padding: "3px 10px", borderRadius: 999,
                background: "rgba(255,138,61,0.12)" }}>S{a.scene} → {a.provider}</span>
            ))}
          </div>

          <div style={{ fontSize: 11, opacity: 0.5, marginTop: 14 }}>QUALITY GATE</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
            {Object.entries(plan.quality_gate.checks).map(([k, ok]) => (
              <span key={k} style={{ fontSize: 11.5, color: ok ? TEAL : RED }}>{ok ? "✓" : "✗"} {k}</span>
            ))}
          </div>
          {plan.character.rejected_scenes.length > 0 && (
            <div style={{ fontSize: 11.5, color: AMBER, marginTop: 10 }}>
              ⚠ character retry needed on scenes: {plan.character.rejected_scenes.join(", ")}
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}
