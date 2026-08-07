"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function PaperOrdersPage() {
  const d = useAuthMe();
  const [portfolioId, setPortfolioId] = useState("");
  const [orders, setOrders] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    if (!d.token || !portfolioId || busy) return;
    setBusy(true); setError(null);
    try {
      setOrders(await plat(`/tg/paper/portfolios/${portfolioId}/orders`, { token: d.token }));
    } catch (e) { setError(e?.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Paper Orders"
        subtitle="Simulated market/limit/stop orders. No exchange connectivity." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" data-testid="no-live-orders" style={pill("#5B8CFF")}>NO LIVE ORDERS</span>
        </div>
        <input className="mono" data-testid="portfolio-id-input" placeholder="portfolio id"
          value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)}
          style={{ padding: 8, minWidth: 280, marginRight: 8 }} />
        <Button data-testid="load-orders" disabled={busy || !portfolioId} onClick={load}>Load orders</Button>
        {error ? <LoadError error={error} /> : null}
        {orders ? (
          <Card style={{ marginTop: 16 }} data-testid="orders-result">
            <Heading level={2} size="md">Orders · {(orders.orders || []).length}</Heading>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 360, overflow: "auto" }}>
              {JSON.stringify(orders.orders || [], null, 2)}
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
