"use client";
// M189 — Monte Carlo robustness lab (paper research only)
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function TradingMonteCarloPage() {
  const d = useAuthMe();
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [slug, setSlug] = useState("trend_following");

  const run = async () => {
    if (!d.token || busy) return;
    setBusy(true); setError(null);
    try {
      setResult(await plat("/tg/historical/monte-carlo", {
        method: "POST", token: d.token,
        body: { strategy_slug: slug, dataset: "TRENDING", n: 40, n_simulations: 50, seed: 42 },
      }));
    } catch (e) {
      setError(e?.message || String(e));
    } finally { setBusy(false); }
  };

  const mc = result?.monte_carlo;

  return (
    <div className="page shell-page">
      <TradingHeader title="Monte Carlo"
        subtitle="Trade-sequence and cost stress simulations. Does not invent alternative real market histories. Paper only." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-research-only" style={pill("#10C98A")}>PAPER RESEARCH ONLY</span>
          <span className="mono" style={pill("#5B8CFF")}>NO LIVE ORDERS</span>
          <span className="mono" style={pill("#F5A623")}>TAIL RISK REQUIRED</span>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          {["trend_following", "kotegawa_mean_reversion", "momentum_rs", "no_trade"].map((s) => (
            <Button key={s} onClick={() => setSlug(s)} data-testid={`mc-select-${s}`}>
              {s === slug ? `● ${s}` : s}
            </Button>
          ))}
        </div>
        <Button onClick={run} disabled={busy} data-testid="run-monte-carlo">Run Monte Carlo</Button>
        {error ? <LoadError error={error} /> : null}
        {mc ? (
          <Card style={{ marginTop: 16 }} data-testid="monte-carlo-result">
            <Heading level={2} size="md">Verdict · {mc.monte_carlo_verdict}</Heading>
            <Text mono size="sm">
              sims {mc.simulation_count} · seed {mc.seed} · trades {mc.trade_count} ·
              median ret {mc.median_return} · p05 {mc.return_p05} ·
              median DD {mc.median_drawdown} · worst DD {mc.worst_percentile_drawdown} ·
              RoR {mc.risk_of_ruin}
            </Text>
            <Text size="sm" tone="muted" style={{ marginTop: 8 }}>{mc.disclaimer}</Text>
            {result?.note ? <Text size="sm" style={{ marginTop: 4 }}>{result.note}</Text> : null}
          </Card>
        ) : null}
      </SignInGate>
    </div>
  );
}

function pill(c) {
  return { fontSize: 11, border: `1px solid ${c}`, color: c, borderRadius: 6, padding: "2px 8px" };
}
