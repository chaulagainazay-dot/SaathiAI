"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function PaperReconcilePage() {
  const d = useAuthMe();
  const [portfolioId, setPortfolioId] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const run = async () => {
    if (!d.token || !portfolioId) return;
    setError(null);
    try {
      setResult(await plat(`/tg/paper/portfolios/${portfolioId}/reconcile`, {
        method: "POST", token: d.token,
      }));
    } catch (e) { setError(e?.message || String(e)); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Paper Reconciliation"
        subtitle="Cash/position/ledger consistency. Fail closed on mismatch." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" style={pill("#FF5A5A")}>FAIL CLOSED</span>
        </div>
        <input className="mono" data-testid="reconcile-portfolio-id" placeholder="portfolio id"
          value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)}
          style={{ padding: 8, minWidth: 280, marginRight: 8 }} />
        <Button data-testid="run-reconcile" onClick={run}>Reconcile</Button>
        {error ? <LoadError error={error} /> : null}
        {result ? (
          <Card style={{ marginTop: 16 }} data-testid="reconcile-result">
            <Heading level={2} size="md">
              Verdict · {result.reconciliation?.verdict}
            </Heading>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 360, overflow: "auto" }}>
              {JSON.stringify(result.reconciliation || result, null, 2)}
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
