"use client";
// M62.8 — Strategy & thesis references. Provenance recorded on each order intent
// (immutable strategy version + thesis references from M62.3/M62.4). Read-only.
import { Text } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, DataTable, StateChip, Loading, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe, useResource, fetchers, fmtTs } from "@/lib/trading";

export default function StrategiesPage() {
  const { token, ready } = useAuthMe();
  const data = useResource(async () => {
    if (!token) return [];
    const list = (await fetchers.intents(token, "").then((r) => r?.intents || []).catch(() => []));
    // enrich a bounded head with strategy/thesis references from intent detail
    const head = list.slice(0, 50);
    const out = [];
    for (const it of head) {
      try {
        const d = (await fetchers.intent(token, it.intent_id))?.intent || it;
        out.push({ ...it, symbol: d.payload?.symbol, side: d.payload?.side,
          strategy_ref: d.strategy_ref, thesis_ref: d.thesis_ref, market_data_ref: d.market_data_ref });
      } catch { out.push(it); }
    }
    return out;
  }, [token]);

  return (
    <div className="page shell-page">
      <TradingHeader title="Strategies & Theses"
        subtitle="Strategy version and thesis provenance recorded on each order intent. Immutable references from research (M62.3) and strategy backtesting (M62.4)." />
      <TradingTabs />
      <SignInGate ready={ready} token={token}>
        <SafetyBanner severity="ok" />
        {data.loading ? <Loading /> : null}
        <LoadError error={data.error} />
        <DataTable
          testId="strategies-table"
          columns={[
            { key: "intent_id", label: "Intent" },
            { key: "symbol", label: "Symbol", render: (r) => r.symbol || "—" },
            { key: "side", label: "Side", render: (r) => r.side || "—" },
            { key: "strategy_ref", label: "Strategy version", render: (r) => r.strategy_ref || "—" },
            { key: "thesis_ref", label: "Thesis", render: (r) => r.thesis_ref || "—" },
            { key: "market_data_ref", label: "Market-data ref", render: (r) => r.market_data_ref || "—" },
            { key: "state", label: "State", render: (r) => <StateChip state={String(r.state || "").toUpperCase()} /> },
            { key: "created_at", label: "Created", render: (r) => fmtTs(r.created_at) },
          ]}
          rows={data.data || []} getKey={(r) => r.intent_id} empty="No order intents / strategy references yet" />
        <Text tone="muted" size="xs" as="p" style={{ marginTop: 10 }}>
          Strategies and theses are immutable upstream records; this workspace references them and never mutates them.
        </Text>
      </SignInGate>
    </div>
  );
}
