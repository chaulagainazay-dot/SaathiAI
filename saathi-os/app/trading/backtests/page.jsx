"use client";
// M171/M174 — Backtest Lab
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function TradingBacktestsPage() {
  const d = useAuthMe();
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async (slug) => {
    if (!d.token || busy) return;
    setBusy(true); setError(null);
    try {
      const res = await plat("/tg/backtests", {
        method: "POST", token: d.token,
        body: { strategy_slug: slug, dataset: "TRENDING", n: 40 },
      });
      setResult(res);
    } catch (e) {
      setError(e?.message || String(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Backtest Lab"
        subtitle="Deterministic research backtests with fees and slippage. Not investment advice. Not live authorization." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" style={pill("#5B8CFF")}>NO LIVE ORDERS</span>
          <span className="mono" style={pill("#8FA0C4")}>SIMULATED FUNDS</span>
          <span className="mono" style={pill("#F5A623")}>NO PROFITABILITY CLAIM</span>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {["trend_following", "kotegawa_mean_reversion", "momentum_rs", "no_trade"].map((s) => (
            <Button key={s} onClick={() => run(s)} disabled={busy} data-testid={`bt-${s}`}>{s}</Button>
          ))}
        </div>
        {error ? <LoadError error={error} /> : null}
        {result ? (
          <Card style={{ marginTop: 16 }}>
            <Heading level={2} size="md">Result · {result.evaluation_verdict}</Heading>
            <Text mono size="sm">status {result.run?.status} · split {result.run?.split_kind}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto" }}>
              {JSON.stringify(result.metrics, null, 2)}
            </pre>
            <Text tone="muted" size="sm" as="p">
              {(result.limitations || []).join(" · ")}
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
