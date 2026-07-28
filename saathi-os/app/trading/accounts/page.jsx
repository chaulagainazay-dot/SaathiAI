"use client";
// M62.8 — Paper Accounts list.
import { useRouter } from "next/navigation";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, DataTable, StateChip, Loading, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe, useResource, fetchers, fmtMoney } from "@/lib/trading";

export default function AccountsPage() {
  const { token, ready } = useAuthMe();
  const router = useRouter();
  const acc = useResource(() => (token ? fetchers.accounts(token).then((r) => r?.accounts || []) : Promise.resolve([])), [token]);
  const rows = acc.data || [];

  return (
    <div className="page shell-page">
      <TradingHeader title="Paper Accounts" subtitle="Simulation accounts, cash, equity and state. Server-provided decimals; the browser never recomputes accounting." />
      <TradingTabs />
      <SignInGate ready={ready} token={token}>
        <SafetyBanner severity={rows.some((a) => a.status === "HALTED") ? "danger" : "ok"} />
        {acc.loading ? <Loading /> : null}
        <LoadError error={acc.error} />
        <DataTable
          testId="accounts-table"
          columns={[
            { key: "name", label: "Account" },
            { key: "status", label: "State", render: (r) => <StateChip state={r.status} /> },
            { key: "current_cash", label: "Cash", align: "right", render: (r) => fmtMoney(r.current_cash) },
            { key: "reserved_cash", label: "Reserved", align: "right", render: (r) => fmtMoney(r.reserved_cash) },
            { key: "total_equity", label: "Equity", align: "right", render: (r) => fmtMoney(r.total_equity) },
            { key: "realized_pnl", label: "Realized P&L", align: "right", render: (r) => fmtMoney(r.realized_pnl) },
            { key: "id", label: "ID", render: (r) => r.id },
          ]}
          rows={rows}
          getKey={(r) => r.id}
          onRow={(r) => router.push(`/trading/accounts/${r.id}`)}
          empty="No paper accounts yet"
        />
      </SignInGate>
    </div>
  );
}
