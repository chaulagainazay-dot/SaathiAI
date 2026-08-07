"use client";
// M190 — Strategy qualification scorecards (paper research only)
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function TradingQualificationPage() {
  const d = useAuthMe();
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [slug, setSlug] = useState("trend_following");

  const run = async () => {
    if (!d.token || busy) return;
    setBusy(true); setError(null);
    try {
      setResult(await plat("/tg/historical/qualify", {
        method: "POST", token: d.token,
        body: { strategy_slug: slug, dataset_id: "", mc_simulations: 50 },
      }));
    } catch (e) {
      setError(e?.message || String(e));
    } finally { setBusy(false); }
  };

  const q = result?.qualification;

  return (
    <div className="page shell-page">
      <TradingHeader title="Strategy Qualification"
        subtitle="Deterministic evidence gates. Fixture/synthetic data cannot yield PAPER_ELIGIBLE. Owner approval still required." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-research-only" style={pill("#10C98A")}>PAPER RESEARCH ONLY</span>
          <span className="mono" data-testid="no-live-orders" style={pill("#5B8CFF")}>NO LIVE ORDERS</span>
          <span className="mono" style={pill("#F5A623")}>ELIGIBILITY ≠ PROFITABILITY</span>
          <span className="mono" style={pill("#8FA0C4")}>OWNER APPROVAL REQUIRED</span>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          {["trend_following", "kotegawa_mean_reversion", "momentum_rs", "no_trade"].map((s) => (
            <Button key={s} onClick={() => setSlug(s)} data-testid={`qual-select-${s}`}>
              {s === slug ? `● ${s}` : s}
            </Button>
          ))}
        </div>
        <Button onClick={run} disabled={busy} data-testid="run-qualify">Qualify strategy</Button>
        {error ? <LoadError error={error} /> : null}
        {q ? (
          <Card style={{ marginTop: 16 }} data-testid="qualification-result">
            <Heading level={2} size="md">
              {q.strategy} · <span data-testid="qualification-verdict">{q.verdict}</span>
            </Heading>
            <Text mono size="sm">
              classification {q.data_classification} · authoritative={String(q.authoritative)} ·
              live={String(q.live_authorized)} · llm_may_approve={String(q.llm_may_approve)}
            </Text>
            <Heading level={3} size="sm" style={{ marginTop: 12 }}>Gates (failed highlighted)</Heading>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 280 }} data-testid="qualification-gates">
              {JSON.stringify(q.gates, null, 2)}
            </pre>
            <Heading level={3} size="sm" style={{ marginTop: 12 }}>Dimensions (visible)</Heading>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 160 }}>
              {JSON.stringify(q.dimensions, null, 2)}
            </pre>
            <Text size="sm" tone="muted" style={{ marginTop: 8 }}>
              {(q.notes || []).slice(0, 4).join(" · ")}
            </Text>
          </Card>
        ) : null}
      </SignInGate>
    </div>
  );
}

function pill(c) {
  return { fontSize: 11, border: `1px solid ${c}`, color: c, borderRadius: 6, padding: "2px 8px" };
}
