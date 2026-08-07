"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function PaperRiskPage() {
  const d = useAuthMe();
  const [ks, setKs] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    if (!d.token || busy) return;
    setBusy(true); setError(null);
    try { setKs(await plat("/tg/paper/kill-switch", { token: d.token })); }
    catch (e) { setError(e?.message || String(e)); }
    finally { setBusy(false); }
  };

  const trip = async () => {
    if (!d.token || busy) return;
    setBusy(true); setError(null);
    try {
      setKs(await plat("/tg/paper/kill-switch", {
        method: "POST", token: d.token,
        body: { reason: "ui paper risk trip", scope: "GLOBAL" },
      }));
    } catch (e) { setError(e?.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Paper Risk & Kill Switch"
        subtitle="Daily/weekly loss limits, circuit breakers, portfolio halt. Paper only." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" data-testid="no-live-orders" style={pill("#FF5A5A")}>KILL SWITCH PAPER HALT</span>
        </div>
        <Button data-testid="load-kill-switch" disabled={busy} onClick={load}>Kill switch status</Button>
        <Button data-testid="trip-kill-switch" disabled={busy} onClick={trip} style={{ marginLeft: 8 }}>
          Trip kill switch
        </Button>
        {error ? <LoadError error={error} /> : null}
        {ks ? (
          <Card style={{ marginTop: 16 }} data-testid="kill-switch-result">
            <Heading level={2} size="md">Kill switch</Heading>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 320, overflow: "auto" }}>
              {JSON.stringify(ks, null, 2)}
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
