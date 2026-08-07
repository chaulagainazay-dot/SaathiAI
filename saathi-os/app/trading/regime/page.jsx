"use client";
// M168/M174 — Market Regime surface (read + evaluate via authenticated TG API).
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, Loading, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe, hasPerm, PERM } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function TradingRegimePage() {
  const d = useAuthMe();
  const [regime, setRegime] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const evaluate = async () => {
    if (!d.token || busy) return;
    setBusy(true); setError(null);
    try {
      const res = await plat("/tg/regime/evaluate", { method: "POST", token: d.token, body: {} });
      setRegime(res.regime || res);
    } catch (e) {
      setError(e?.message || String(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Market Regime"
        subtitle="Deterministic regime classification. LLM may summarize but never determines regime." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" style={pill("#5B8CFF")}>NO LIVE ORDERS</span>
          <span className="mono" style={pill("#8FA0C4")}>SIMULATED FUNDS</span>
          <span className="mono" style={pill("#F5A623")}>LLM DOES NOT DETERMINE REGIME</span>
        </div>
        {hasPerm(d.perms, PERM.READ) || d.token ? (
          <Button onClick={evaluate} disabled={busy} data-testid="evaluate-regime">
            {busy ? "Evaluating…" : "Evaluate fixture regime"}
          </Button>
        ) : null}
        {error ? <LoadError error={error} /> : null}
        {regime ? (
          <Card style={{ marginTop: 16 }}>
            <Heading level={2} size="md">Primary: {regime.primary}</Heading>
            <Text mono size="sm">Labels: {(regime.labels || []).join(", ")}</Text>
            <Text tone="muted" size="sm" as="p">{regime.explanation}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto" }}>
              {JSON.stringify(regime.factors || {}, null, 2)}
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
