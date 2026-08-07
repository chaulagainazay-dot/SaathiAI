"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function PaperJournalPage() {
  const d = useAuthMe();
  const [portfolioId, setPortfolioId] = useState("");
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    if (!d.token || !portfolioId) return;
    setError(null);
    try {
      setEntries(await plat(`/tg/paper/portfolios/${portfolioId}/journal`, { token: d.token }));
    } catch (e) { setError(e?.message || String(e)); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Paper Journal" subtitle="Immutable paper trade journal. LLM notes are advisory only." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" style={pill("#8FA0C4")}>IMMUTABLE JOURNAL</span>
        </div>
        <input className="mono" data-testid="journal-portfolio-id" placeholder="portfolio id"
          value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)}
          style={{ padding: 8, minWidth: 280, marginRight: 8 }} />
        <Button data-testid="load-journal" onClick={load}>Load journal</Button>
        {error ? <LoadError error={error} /> : null}
        {entries ? (
          <Card style={{ marginTop: 16 }} data-testid="journal-result">
            <Heading level={2} size="md">Entries · {(entries.entries || []).length}</Heading>
            <Text size="sm">immutable={String(entries.immutable)}</Text>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 360, overflow: "auto" }}>
              {JSON.stringify(entries.entries || [], null, 2)}
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
