"use client";
// M174 — Proposal Review (paper only). Approval required; no self-approval.
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useEffect, useState } from "react";

export default function TradingProposalsPage() {
  const d = useAuthMe();
  const [items, setItems] = useState([]);
  const [msg, setMsg] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    if (!d.token) return;
    try {
      const res = await plat("/tg/proposals", { token: d.token });
      setItems(res.proposals || []);
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  useEffect(() => { refresh(); }, [d.token]);

  const create = async () => {
    if (!d.token || busy) return;
    setBusy(true); setMsg(null); setError(null);
    try {
      const res = await plat("/tg/proposals", {
        method: "POST", token: d.token,
        body: { strategy_slug: "trend_following", fixture: "trending" },
      });
      setMsg(res.proposal ? `Proposal ${res.proposal.id} — ${res.proposal.status}` : res.reason || "no signal");
      await refresh();
    } catch (e) {
      setError(e?.message || String(e));
    } finally { setBusy(false); }
  };

  const review = async (id, decision) => {
    if (!d.token || busy) return;
    setBusy(true); setError(null);
    try {
      await plat(`/tg/proposals/${id}/review`, {
        method: "POST", token: d.token,
        body: { decision, notes: "operator UI review" },
      });
      await refresh();
    } catch (e) {
      setError(e?.message || String(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Proposal Review"
        subtitle="Structured trade proposals only. Human approval required. Strategies and LLMs cannot approve themselves." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" style={pill("#5B8CFF")}>NO LIVE ORDERS</span>
          <span className="mono" style={pill("#8FA0C4")}>SIMULATED FUNDS</span>
          <span className="mono" style={pill("#F5A623")}>APPROVAL REQUIRED</span>
        </div>
        <Button onClick={create} disabled={busy} data-testid="create-proposal">
          {busy ? "Working…" : "Generate sample proposal"}
        </Button>
        {msg ? <Text mono size="sm" as="p">{msg}</Text> : null}
        {error ? <LoadError error={error} /> : null}
        <div style={{ marginTop: 16, display: "grid", gap: 12 }}>
          {items.map((p) => (
            <Card key={p.id} data-testid="proposal-card">
              <Heading level={3} size="sm">{p.symbol} · {p.status}</Heading>
              <Text mono size="sm">qty {p.quantity} @ {p.entry_price} · R:R {p.reward_to_risk}</Text>
              <Text tone="muted" size="sm" as="p">{p.explanation}</Text>
              <Text mono size="xs">strategy {p.strategy_version} · policy {p.policy_version} · {p.funds_label}</Text>
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <Button onClick={() => review(p.id, "approve")} disabled={busy}>Approve (paper)</Button>
                <Button onClick={() => review(p.id, "reject")} disabled={busy}>Reject</Button>
              </div>
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
