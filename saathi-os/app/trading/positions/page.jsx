"use client";
// M62.8 — Positions across paper accounts. Marks are fixture/replay (avg cost), never live.
import { Text } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, DataTable, Loading, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe, useResource, fetchers, fmtMoney, fmtNum } from "@/lib/trading";

export default function PositionsPage() {
  const { token, ready } = useAuthMe();
  const data = useResource(async () => {
    if (!token) return [];
    const accts = (await fetchers.accounts(token))?.accounts || [];
    const all = [];
    for (const a of accts) {
      const ps = (await fetchers.positions(token, a.id))?.positions || [];
      ps.forEach((p) => all.push({ ...p, account: a.name, account_id: a.id }));
    }
    return all;
  }, [token]);

  return (
    <div className="page shell-page">
      <TradingHeader title="Positions" subtitle="Long-only paper positions. Marks derive from fixture / replay data — not a live price feed." />
      <TradingTabs />
      <SignInGate ready={ready} token={token}>
        <SafetyBanner severity="ok" />
        <div style={{ marginBottom: 10 }}>
          <span className="mono" style={{ fontSize: 11, color: "#8FA0C4", border: "1px solid #2a2f3a", borderRadius: 6, padding: "3px 9px" }}>REPLAY / FIXTURE DATA — NOT LIVE PRICES</span>
        </div>
        {data.loading ? <Loading /> : null}
        <LoadError error={data.error} />
        <DataTable
          testId="positions-table"
          columns={[
            { key: "account", label: "Account" },
            { key: "symbol", label: "Symbol" },
            { key: "quantity", label: "Qty", align: "right", render: (r) => fmtNum(r.quantity, 4) },
            { key: "avg_cost", label: "Avg cost", align: "right", render: (r) => fmtMoney(r.avg_cost) },
            { key: "market_value", label: "Value (fixture)", align: "right", render: (r) => fmtMoney(r.market_value || r.avg_cost) },
            { key: "unrealized_pnl", label: "Unreal. P&L", align: "right", render: (r) => fmtMoney(r.unrealized_pnl) },
            { key: "realized_pnl", label: "Realized", align: "right", render: (r) => fmtMoney(r.realized_pnl) },
          ]}
          rows={data.data || []} getKey={(r) => `${r.account_id}-${r.symbol}`}
          empty="No positions across paper accounts"
        />
        <Text tone="muted" size="xs" as="p" style={{ marginTop: 10 }}>
          Concentration and exposure limits are enforced server-side by the M62.7 breakers; see Safety.
        </Text>
      </SignInGate>
    </div>
  );
}
