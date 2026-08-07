"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function PaperOpsPage() {
  const d = useAuthMe();
  const [storage, setStorage] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  const load = async (path, setter) => {
    if (!d.token) return;
    setError(null);
    try { setter(await plat(path, { token: d.token })); }
    catch (e) { setError(e?.message || String(e)); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Paper Operations Overview"
        subtitle="Durable multi-process paper ledger health, reports, and kill-switch posture." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" data-testid="no-live" style={pill("#FF5A5A")}>LIVE TRADING NOT AUTHORIZED</span>
          <span className="mono" style={pill("#5B8CFF")}>DURABLE LEDGER</span>
        </div>
        <Button data-testid="load-storage" onClick={() => load("/tg/paper/storage-status", setStorage)}>Storage status</Button>
        <Button data-testid="load-daily" style={{ marginLeft: 8 }} onClick={() => load("/tg/paper/reports/daily", setReport)}>Daily report</Button>
        {error ? <LoadError error={error} /> : null}
        {storage ? (
          <Card style={{ marginTop: 16 }} data-testid="storage-result">
            <Heading level={2} size="md">Storage · {storage.status}</Heading>
            <Text mono size="sm">schema {storage.schema_version} · events {storage.event_count} · portfolios {storage.portfolio_count}</Text>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 240, overflow: "auto" }}>{JSON.stringify(storage, null, 2)}</pre>
          </Card>
        ) : null}
        {report ? (
          <Card style={{ marginTop: 16 }} data-testid="daily-report">
            <Heading level={2} size="md">Daily report</Heading>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 240, overflow: "auto" }}>{JSON.stringify(report, null, 2)}</pre>
          </Card>
        ) : null}
      </SignInGate>
    </div>
  );
}
function pill(c) { return { fontSize: 11, border: `1px solid ${c}`, color: c, borderRadius: 6, padding: "2px 8px" }; }
