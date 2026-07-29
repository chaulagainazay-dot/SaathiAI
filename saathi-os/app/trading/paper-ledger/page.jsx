"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function PaperLedgerPage() {
  const d = useAuthMe();
  const [events, setEvents] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    if (!d.token) return;
    setError(null);
    try { setEvents(await plat("/tg/paper/events?limit=100", { token: d.token })); }
    catch (e) { setError(e?.message || String(e)); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Durable Ledger Explorer"
        subtitle="Append-only immutable paper operations events. Corrections require compensating events." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" style={pill("#8FA0C4")}>IMMUTABLE EVENTS</span>
        </div>
        <Button data-testid="load-events" onClick={load}>Load events</Button>
        {error ? <LoadError error={error} /> : null}
        {events ? (
          <Card style={{ marginTop: 16 }} data-testid="events-result">
            <Heading level={2} size="md">Events · {(events.events || []).length}</Heading>
            <Text size="sm">immutable={String(events.immutable)}</Text>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 400, overflow: "auto" }}>
              {JSON.stringify(events.events || [], null, 2)}
            </pre>
          </Card>
        ) : null}
      </SignInGate>
    </div>
  );
}
function pill(c) { return { fontSize: 11, border: `1px solid ${c}`, color: c, borderRadius: 6, padding: "2px 8px" }; }
