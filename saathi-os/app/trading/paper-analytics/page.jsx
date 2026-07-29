"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function PaperAnalyticsPage() {
  const d = useAuthMe();
  const [portfolioId, setPortfolioId] = useState("");
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    if (!d.token || !portfolioId) return;
    setError(null);
    try {
      setAnalytics(await plat(`/tg/paper/portfolios/${portfolioId}/analytics`, { token: d.token }));
    } catch (e) { setError(e?.message || String(e)); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Paper Analytics"
        subtitle="Win rate, Sharpe, drawdown, exposure heatmap. Simulated results only." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" style={pill("#F5A623")}>NOT FUTURE RESULTS</span>
        </div>
        <input className="mono" data-testid="analytics-portfolio-id" placeholder="portfolio id"
          value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)}
          style={{ padding: 8, minWidth: 280, marginRight: 8 }} />
        <Button data-testid="load-analytics" onClick={load}>Load analytics</Button>
        {error ? <LoadError error={error} /> : null}
        {analytics ? (
          <Card style={{ marginTop: 16 }} data-testid="analytics-result">
            <Heading level={2} size="md">Analytics</Heading>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 400, overflow: "auto" }}>
              {JSON.stringify(analytics.analytics || analytics, null, 2)}
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
