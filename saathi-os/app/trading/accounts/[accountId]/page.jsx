"use client";
// M62.8 — Paper Account detail: balances, positions, open orders, halt posture,
// breaker states, latest reconciliation. Read-only; server is authoritative.
import { useParams } from "next/navigation";
import Link from "next/link";
import { Card, Heading, Text } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, DataTable, StateChip, Loading, LoadError, StatCard }
  from "@/components/trading/TradingShell";
import { useAuthMe, useResource, fetchers, fmtMoney, fmtTs } from "@/lib/trading";

export default function AccountDetailPage() {
  const { accountId } = useParams();
  const { token, ready } = useAuthMe();
  const acct = useResource(() => (token ? fetchers.account(token, accountId).then((r) => r.account) : Promise.resolve(null)), [token, accountId]);
  const orders = useResource(() => (token ? fetchers.orders(token, accountId).then((r) => r?.orders || []) : Promise.resolve([])), [token, accountId]);
  const states = useResource(() => (token ? fetchers.states(token).then((r) => (r?.states || []).filter((s) => s.scope === "PAPER_ACCOUNT" && s.scope_ref === accountId)) : Promise.resolve([])), [token, accountId]);
  const recon = useResource(() => (token ? fetchers.reconRuns(token, accountId).then((r) => r?.runs || []) : Promise.resolve([])), [token, accountId]);

  const a = acct.data;
  const open = (orders.data || []).filter((o) => !["FILLED", "CANCELLED", "REJECTED", "EXPIRED", "FAILED"].includes(o.broker_state));
  const halted = a?.status === "HALTED";

  return (
    <div className="page shell-page">
      <TradingHeader title={a ? a.name : "Account"} subtitle={<Link href="/trading/accounts" style={{ color: "#5B8CFF", textDecoration: "none" }}>← All accounts</Link>} severity={halted ? "danger" : "ok"} />
      <TradingTabs />
      <SignInGate ready={ready} token={token}>
        <SafetyBanner severity={halted ? "danger" : "ok"} />
        {acct.loading ? <Loading /> : null}
        <LoadError error={acct.error} />
        {a ? (
          <>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
              <StatCard label="State" value={<StateChip state={a.status} />} tone={halted ? "danger" : "ok"} />
              <StatCard label="Starting cash" value={fmtMoney(a.starting_cash)} />
              <StatCard label="Cash" value={fmtMoney(a.current_cash)} />
              <StatCard label="Reserved" value={fmtMoney(a.reserved_cash)} />
              <StatCard label="Available" value={fmtMoney(a.available_cash)} />
              <StatCard label="Equity" value={fmtMoney(a.total_equity)} />
              <StatCard label="Realized P&L" value={fmtMoney(a.realized_pnl)} />
              <StatCard label="Open orders" value={open.length} tone={open.length ? "warn" : "idle"} />
            </div>

            {halted ? (
              <Card style={{ borderColor: "color-mix(in srgb,#FF5A5A 40%,transparent)", marginBottom: 12 }}>
                <Heading level={3} size="sm">Account halted</Heading>
                <dl style={dl}>
                  <Row k="Halt reason" v={a.halt_reason || "—"} />
                  <Row k="Version" v={a.version} />
                  <Row k="Updated" v={fmtTs(a.updated_at)} />
                </dl>
                <Text tone="muted" size="xs" as="p" style={{ marginTop: 6 }}>
                  Resolve via Safety → acknowledge the trip, then request an approval-backed reset. Acknowledgement alone does not remove the halt.
                </Text>
                <Link href="/trading/safety" style={{ color: "#5B8CFF", textDecoration: "none", fontSize: 12 }}>Open Safety →</Link>
              </Card>
            ) : null}

            <Card style={{ marginBottom: 12 }}>
              <Heading level={3} size="sm">Positions <span className="mono" style={fixtureTag}>REPLAY / FIXTURE MARKS</span></Heading>
              <PositionsTable token={token} accountId={accountId} />
            </Card>

            <Card style={{ marginBottom: 12 }}>
              <Heading level={3} size="sm">Open orders</Heading>
              <DataTable
                columns={[
                  { key: "id", label: "Order" },
                  { key: "symbol", label: "Symbol" },
                  { key: "side", label: "Side" },
                  { key: "original_quantity", label: "Qty", align: "right" },
                  { key: "filled_quantity", label: "Filled", align: "right" },
                  { key: "broker_state", label: "State", render: (r) => <StateChip state={r.broker_state} /> },
                ]}
                rows={open} getKey={(r) => r.id} empty="No open orders" />
            </Card>

            <Card style={{ marginBottom: 12 }}>
              <Heading level={3} size="sm">Breaker posture</Heading>
              <DataTable
                columns={[
                  { key: "definition_id", label: "Breaker" },
                  { key: "state", label: "State", render: (r) => <StateChip state={r.state} /> },
                  { key: "trip_count", label: "Trips", align: "right" },
                  { key: "last_evaluated_at", label: "Evaluated", render: (r) => fmtTs(r.last_evaluated_at) },
                ]}
                rows={states.data || []} getKey={(r) => r.definition_id} empty="No breakers provisioned" />
            </Card>

            <Card>
              <Heading level={3} size="sm">Reconciliation history</Heading>
              <DataTable
                columns={[
                  { key: "run_id", label: "Run" },
                  { key: "severity_max", label: "Severity", render: (r) => <StateChip state={r.severity_max} /> },
                  { key: "halted", label: "Halted", render: (r) => (r.halted ? "yes" : "no") },
                  { key: "ts", label: "When", render: (r) => fmtTs(r.ts) },
                ]}
                rows={recon.data || []} getKey={(r) => r.run_id} empty="No reconciliation runs" />
            </Card>
          </>
        ) : (!acct.loading && ready && token ? <Text tone="muted" as="p">Account not found for this tenant.</Text> : null)}
      </SignInGate>
    </div>
  );
}

function PositionsTable({ token, accountId }) {
  const pos = useResource(() => (token ? fetchers.positions(token, accountId).then((r) => r?.positions || []) : Promise.resolve([])), [token, accountId]);
  return (
    <DataTable
      columns={[
        { key: "symbol", label: "Symbol" },
        { key: "quantity", label: "Qty", align: "right" },
        { key: "avg_cost", label: "Avg cost", align: "right", render: (r) => fmtMoney(r.avg_cost) },
        { key: "market_value", label: "Value", align: "right", render: (r) => fmtMoney(r.market_value || r.avg_cost) },
        { key: "unrealized_pnl", label: "Unreal. P&L", align: "right", render: (r) => fmtMoney(r.unrealized_pnl) },
      ]}
      rows={pos.data || []} getKey={(r) => r.symbol} empty="No positions" />
  );
}

const dl = { display: "grid", gap: 4, marginTop: 8, fontSize: 12.5 };
const fixtureTag = { fontSize: 10, marginLeft: 8, color: "#8FA0C4", border: "1px solid #2a2f3a", borderRadius: 5, padding: "1px 6px" };
function Row({ k, v }) {
  return <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><dt style={{ color: "var(--text-muted)" }}>{k}</dt><dd className="mono" style={{ color: "var(--text-secondary)", textAlign: "right" }}>{v}</dd></div>;
}
