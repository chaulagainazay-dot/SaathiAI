"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function PaperCampaignsPage() {
  const d = useAuthMe();
  const [list, setList] = useState(null);
  const [created, setCreated] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    if (!d.token) return;
    setError(null);
    try { setList(await plat("/tg/paper/campaigns", { token: d.token })); }
    catch (e) { setError(e?.message || String(e)); }
  };
  const create = async () => {
    if (!d.token) return;
    setError(null);
    try {
      setCreated(await plat("/tg/paper/campaigns", {
        method: "POST", token: d.token,
        body: { strategy_slug: "trend_following", initial_cash: "100000", operator_notes: "ui draft" },
      }));
      await load();
    } catch (e) { setError(e?.message || String(e)); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Campaign Manager"
        subtitle="Long-horizon paper campaigns. Completion never authorizes live trading." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" style={pill("#FF5A5A")}>NOT LIVE-ELIGIBLE</span>
        </div>
        <Button data-testid="create-campaign" onClick={create}>Create draft campaign</Button>
        <Button data-testid="list-campaigns" style={{ marginLeft: 8 }} onClick={load}>List campaigns</Button>
        {error ? <LoadError error={error} /> : null}
        {created ? (
          <Card style={{ marginTop: 16 }} data-testid="campaign-created">
            <Heading level={2} size="md">Created · {created.campaign?.status}</Heading>
            <Text mono size="sm">{created.campaign?.id}</Text>
          </Card>
        ) : null}
        {list ? (
          <Card style={{ marginTop: 16 }} data-testid="campaign-list">
            <Heading level={2} size="md">Campaigns · {(list.campaigns || []).length}</Heading>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 320, overflow: "auto" }}>
              {JSON.stringify(list.campaigns || [], null, 2)}
            </pre>
          </Card>
        ) : null}
      </SignInGate>
    </div>
  );
}
function pill(c) { return { fontSize: 11, border: `1px solid ${c}`, color: c, borderRadius: 6, padding: "2px 8px" }; }
