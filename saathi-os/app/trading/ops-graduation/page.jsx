"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

/** M215 — Operations Dashboard for paper campaign graduation. PAPER ONLY. */
export default function OpsGraduationPage() {
  const d = useAuthMe();
  const [dash, setDash] = useState(null);
  const [health, setHealth] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [recs, setRecs] = useState(null);
  const [error, setError] = useState(null);

  const load = async (path, setter) => {
    if (!d.token) return;
    setError(null);
    try { setter(await plat(path, { token: d.token })); }
    catch (e) { setError(e?.message || String(e)); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Operations Dashboard"
        subtitle="Multi-campaign paper operations, health, graduation, and certification. Never live." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER ONLY</span>
          <span className="mono" data-testid="no-live" style={pill("#FF5A5A")}>NO LIVE TRADING</span>
          <span className="mono" data-testid="no-auto-live" style={pill("#F5A623")}>NO AUTO LIVE PROMOTION</span>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <Button data-testid="load-dashboard" onClick={() => load("/tg/paper/ops/dashboard", setDash)}>
            Campaign Overview
          </Button>
          <Button data-testid="load-health" onClick={() => load("/tg/paper/ops/health", setHealth)}>
            Operational Health
          </Button>
          <Button data-testid="load-verdict" onClick={() => load("/tg/paper/ops/verdict", setVerdict)}>
            Certification Verdict
          </Button>
          <Button data-testid="load-intel" onClick={() => load("/tg/paper/ops/recommendations", setRecs)}>
            Recommendations
          </Button>
        </div>
        {error ? <LoadError error={error} /> : null}

        {verdict ? (
          <Card style={{ marginTop: 12 }} data-testid="ops-verdict">
            <Heading level={2} size="md">Verdict · {verdict.verdict}</Heading>
            <Text mono size="sm">live_trading_authorized={String(verdict.live_trading_authorized)}</Text>
            <ul className="mono" style={{ fontSize: 12 }}>
              {(verdict.statements || []).map((s) => <li key={s}>{s}</li>)}
            </ul>
          </Card>
        ) : null}

        {health ? (
          <Card style={{ marginTop: 12 }} data-testid="ops-health">
            <Heading level={2} size="md">Operational Health · {health.classification}</Heading>
            <Text size="sm">Classes: HEALTHY · WARNING · DEGRADED · CRITICAL · FAILED_SAFE</Text>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 240, overflow: "auto" }}>
              {JSON.stringify(health.components || health, null, 2)}
            </pre>
          </Card>
        ) : null}

        {dash ? (
          <Card style={{ marginTop: 12 }} data-testid="ops-dashboard">
            <Heading level={2} size="md">Dashboard · {dash.labels?.paper_only} · {dash.labels?.no_live}</Heading>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <section data-testid="campaign-overview">
                <Heading level={3} size="sm">Campaign Overview</Heading>
                <Text mono size="sm">total {dash.campaign_overview?.total}</Text>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify(dash.campaign_overview?.by_status || {}, null, 2)}
                </pre>
              </section>
              <section data-testid="graduation-status">
                <Heading level={3} size="sm">Graduation Status</Heading>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify(dash.graduation_status || [], null, 2)}
                </pre>
              </section>
              <section data-testid="strategy-rankings">
                <Heading level={3} size="sm">Strategy Rankings</Heading>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify(dash.strategy_rankings || {}, null, 2)}
                </pre>
              </section>
              <section data-testid="risk-center">
                <Heading level={3} size="sm">Risk Center</Heading>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify(dash.risk_center || {}, null, 2)}
                </pre>
              </section>
              <section data-testid="evidence-center">
                <Heading level={3} size="sm">Evidence Center</Heading>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify(dash.evidence_center || {}, null, 2)}
                </pre>
              </section>
              <section data-testid="incident-center">
                <Heading level={3} size="sm">Incident Center</Heading>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify(dash.incident_center || {}, null, 2)}
                </pre>
              </section>
              <section data-testid="recovery-center">
                <Heading level={3} size="sm">Recovery Center</Heading>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify(dash.recovery_center || {}, null, 2)}
                </pre>
              </section>
              <section data-testid="scheduler-storage-workers">
                <Heading level={3} size="sm">Scheduler · Storage · Workers</Heading>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify({
                    scheduler: dash.scheduler,
                    storage: dash.storage,
                    workers: dash.workers,
                  }, null, 2)}
                </pre>
              </section>
              <section data-testid="campaign-timeline" style={{ gridColumn: "1 / -1" }}>
                <Heading level={3} size="sm">Campaign Timeline</Heading>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify(dash.campaign_timeline || [], null, 2)}
                </pre>
              </section>
            </div>
            <Text size="sm" style={{ marginTop: 8 }}>{dash.disclaimer}</Text>
          </Card>
        ) : null}

        {recs ? (
          <Card style={{ marginTop: 12 }} data-testid="ops-recommendations">
            <Heading level={2} size="md">Recommendations (never auto-applied)</Heading>
            <Text mono size="sm">modifies_portfolios={String(recs.modifies_portfolios ?? false)}</Text>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 240, overflow: "auto" }}>
              {JSON.stringify(recs.recommendations || recs, null, 2)}
            </pre>
          </Card>
        ) : null}
      </SignInGate>
    </div>
  );
}
function pill(c) {
  return { fontSize: 11, border: `1px solid ${c}`, color: c, borderRadius: 6, padding: "2px 8px" };
}
