"use client";
// M62.8 — Orders list (tenant-scoped). No manual live-order entry.
import { useRouter } from "next/navigation";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, DataTable, StateChip, Loading, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe, useResource, fetchers, fmtNum } from "@/lib/trading";

export default function OrdersPage() {
  const { token, ready } = useAuthMe();
  const router = useRouter();
  const orders = useResource(() => (token ? fetchers.orders(token, "").then((r) => r?.orders || []) : Promise.resolve([])), [token]);

  return (
    <div className="page shell-page">
      <TradingHeader title="Orders" subtitle="Durable paper orders and their lifecycle. No live-order entry; paper fills are simulation events." />
      <TradingTabs />
      <SignInGate ready={ready} token={token}>
        <SafetyBanner severity="ok" />
        {orders.loading ? <Loading /> : null}
        <LoadError error={orders.error} />
        <DataTable
          testId="orders-table"
          columns={[
            { key: "id", label: "Order" },
            { key: "symbol", label: "Symbol" },
            { key: "side", label: "Side" },
            { key: "original_quantity", label: "Qty", align: "right", render: (r) => fmtNum(r.original_quantity, 4) },
            { key: "filled_quantity", label: "Filled", align: "right", render: (r) => fmtNum(r.filled_quantity, 4) },
            { key: "remaining_quantity", label: "Remaining", align: "right", render: (r) => fmtNum(r.remaining_quantity, 4) },
            { key: "broker_state", label: "State", render: (r) => <StateChip state={r.broker_state} /> },
            { key: "paper_account_id", label: "Account" },
          ]}
          rows={orders.data || []} getKey={(r) => r.id}
          onRow={(r) => router.push(`/trading/orders/${r.id}`)}
          empty="No orders yet"
        />
      </SignInGate>
    </div>
  );
}
