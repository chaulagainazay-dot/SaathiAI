"use client";
// M192–M199 — Paper portfolio fund simulator (PAPER ONLY)
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function PaperPortfolioPage() {
  const d = useAuthMe();
  const [list, setList] = useState(null);
  const [detail, setDetail] = useState(null);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async (fn) => {
    if (!d.token || busy) return;
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError(e?.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Paper Portfolio"
        subtitle="Multi-portfolio simulated fund. Owner-approved PAPER_ACTIVE strategies only. No live broker." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" data-testid="no-live-orders" style={pill("#5B8CFF")}>NO LIVE ORDERS</span>
          <span className="mono" style={pill("#F5A623")}>SIMULATED FUNDS</span>
          <span className="mono" style={pill("#8FA0C4")}>LIVE TRADING NOT AUTHORIZED</span>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Button data-testid="paper-create" disabled={busy} onClick={() => run(async () => {
            const r = await plat("/tg/paper/portfolios", {
              method: "POST", token: d.token,
              body: { name: "Paper Fund", starting_cash: "100000" },
            });
            setDetail(r);
            setList(await plat("/tg/paper/portfolios", { token: d.token }));
          })}>Create portfolio</Button>
          <Button data-testid="paper-list" disabled={busy} onClick={() => run(async () => {
            setList(await plat("/tg/paper/portfolios", { token: d.token }));
          })}>List portfolios</Button>
          <Button data-testid="paper-status" disabled={busy} onClick={() => run(async () => {
            setStatus(await plat("/tg/paper/status", { token: d.token }));
          })}>Status</Button>
        </div>
        {error ? <LoadError error={error} /> : null}
        {detail ? (
          <Card style={{ marginTop: 16 }} data-testid="portfolio-created">
            <Heading level={2} size="md">Created · {detail.portfolio?.name}</Heading>
            <Text mono size="sm">
              id {detail.portfolio?.id} · cash {detail.portfolio?.cash} · equity {detail.portfolio?.equity} ·
              status {detail.portfolio?.status}
            </Text>
          </Card>
        ) : null}
        {list ? (
          <Card style={{ marginTop: 16 }} data-testid="portfolio-list">
            <Heading level={2} size="md">Portfolios · {(list.portfolios || []).length}</Heading>
            <ul>
              {(list.portfolios || []).map((p) => (
                <li key={p.id} className="mono" style={{ fontSize: 12 }}>
                  {p.name} · {p.id.slice(0, 16)}… · equity {p.equity} · {p.status}
                </li>
              ))}
            </ul>
          </Card>
        ) : null}
        {status ? (
          <Card style={{ marginTop: 16 }} data-testid="paper-status-result">
            <Heading level={2} size="md">Governance status</Heading>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 280, overflow: "auto" }}>
              {JSON.stringify(status, null, 2)}
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
