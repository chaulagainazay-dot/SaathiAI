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
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "8px 0" }}>
              <span className="mono" data-testid="data-classification" style={{ fontSize: 11, border: "1px solid #F5A623", color: "#F5A623", borderRadius: 6, padding: "2px 8px" }}>
                DATA: {result.data_classification || "UNKNOWN"}
              </span>
              <span className="mono" style={{ fontSize: 11, border: "1px solid #8FA0C4", color: "#8FA0C4", borderRadius: 6, padding: "2px 8px" }}>
                AUTHORITATIVE: {String(result.authoritative === true)}
              </span>
              <span className="mono" style={{ fontSize: 11, border: "1px solid #5B8CFF", color: "#5B8CFF", borderRadius: 6, padding: "2px 8px" }}>
                FIXTURE METRICS USED: {String(result.fixture_metrics_used === true)}
              </span>
            </div>
            <Text mono size="sm">status {result.status || result.run?.status} · split {result.run?.split_kind}</Text>
            <Text mono size="xs" as="p">
              strategy v{result.provenance?.strategy_version || "—"} · policy {result.provenance?.policy_version || "—"} ·
              fees {result.provenance?.fee_bps || "—"} bps · slip {result.provenance?.slippage_bps || "—"} bps ·
              range {result.provenance?.date_range_start || "—"} → {result.provenance?.date_range_end || "—"}
            </Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto" }}>
              {JSON.stringify(result.metrics, null, 2)}
            </pre>
            <Text tone="muted" size="sm" as="p">
              {(result.limitations || []).join(" · ")}
            </Text>
            <Text tone="muted" size="xs" as="p">
              Synthetic and fixture results are not market evidence. Historical results do not predict future results.
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
