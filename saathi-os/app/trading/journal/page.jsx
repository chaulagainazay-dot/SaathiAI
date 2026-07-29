"use client";
// M173/M174 — Trade Journal (immutable append-only evidence)
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useEffect, useState } from "react";

export default function TradingJournalPage() {
  const d = useAuthMe();
  const [entries, setEntries] = useState([]);
  const [error, setError] = useState(null);

  const refresh = async () => {
    if (!d.token) return;
    try {
      const res = await plat("/tg/journal", { token: d.token });
      setEntries(res.entries || []);
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  useEffect(() => { refresh(); }, [d.token]);

  return (
    <div className="page shell-page">
      <TradingHeader title="Trade Journal"
        subtitle="Append-only lifecycle evidence. Simulated P&L is not real money." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" style={pill("#5B8CFF")}>NO LIVE ORDERS</span>
          <span className="mono" style={pill("#8FA0C4")}>SIMULATED FUNDS</span>
          <span className="mono" style={pill("#F5A623")}>IMMUTABLE</span>
        </div>
        <Button onClick={refresh} data-testid="refresh-journal">Refresh</Button>
        {error ? <LoadError error={error} /> : null}
        <div style={{ marginTop: 16, display: "grid", gap: 10 }}>
          {entries.length === 0 ? <Text tone="muted">No journal entries yet.</Text> : null}
          {entries.map((e) => (
            <Card key={e.id}>
              <Heading level={3} size="sm">{e.proposal_id || e.id}</Heading>
              <Text mono size="xs">
                {e.strategy_id}@{e.strategy_version} · regime {(e.regime || []).join(",")} · {e.funds_label}
              </Text>
              <Text tone="muted" size="sm" as="p">{e.operator_notes || e.exit_reason || "—"}</Text>
            </Card>
          ))}
        </div>
      </SignInGate>
    </div>
  );
}

function pill(c) {
  return { fontSize: 11, border: `1px solid ${c}`, color: c, borderRadius: 6, padding: "2px 8px" };
}
