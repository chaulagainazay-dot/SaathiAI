"use client";
// M173/M174 — Strategy Comparison
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function TradingComparisonPage() {
  const d = useAuthMe();
  const [cmp, setCmp] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!d.token || busy) return;
    setBusy(true); setError(null);
    try {
      setCmp(await plat("/tg/backtests/compare", { token: d.token }));
    } catch (e) {
      setError(e?.message || String(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Strategy Comparison"
        subtitle="Multi-factor ranking. Return alone never promotes a strategy. No LIVE_APPROVED verdict." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" style={pill("#5B8CFF")}>NO LIVE ORDERS</span>
          <span className="mono" style={pill("#8FA0C4")}>SIMULATED FUNDS</span>
        </div>
        <Button onClick={run} disabled={busy} data-testid="compare-strategies">
          {busy ? "Comparing…" : "Compare catalog strategies"}
        </Button>
        {error ? <LoadError error={error} /> : null}
        {cmp ? (
          <Card style={{ marginTop: 16 }}>
            <Heading level={2} size="md">Ranking</Heading>
            <ol data-testid="strategy-ranking">
              {(cmp.ranking || []).map((s) => (
                <li key={s} className="mono">
                  {s} — {cmp.verdicts?.[s]}
                  {cmp.scorecards?.[s]?.data_classification
                    ? ` · ${cmp.scorecards[s].data_classification}`
                    : ""}
                </li>
              ))}
            </ol>
            <Text tone="muted" size="sm" as="p">{(cmp.notes || []).join(" ")}</Text>
            <Text tone="muted" size="xs" as="p">
              No LIVE_APPROVED verdict. Fixture/synthetic results are not market evidence.
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
