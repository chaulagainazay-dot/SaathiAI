"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function PaperApprovalsPage() {
  const d = useAuthMe();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    if (!d.token || busy) return;
    setBusy(true); setError(null);
    try {
      setRows(await plat("/tg/paper/approvals", { token: d.token }));
    } catch (e) { setError(e?.message || String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Paper Approvals"
        subtitle="Owner approval for PAPER_ELIGIBLE strategies. LLM cannot approve. Single-use, reason required." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" style={pill("#5B8CFF")}>OWNER APPROVAL REQUIRED</span>
          <span className="mono" style={pill("#F5A623")}>LLM MAY NOT APPROVE</span>
        </div>
        <Button data-testid="list-paper-approvals" disabled={busy} onClick={load}>List approvals</Button>
        {error ? <LoadError error={error} /> : null}
        {rows ? (
          <Card style={{ marginTop: 16 }} data-testid="paper-approvals-result">
            <Heading level={2} size="md">Approvals · {(rows.approvals || []).length}</Heading>
            <Text size="sm">llm_may_approve={String(rows.llm_may_approve)}</Text>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 360, overflow: "auto" }}>
              {JSON.stringify(rows.approvals || [], null, 2)}
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
