"use client";
// M62.8 — Order detail: lifecycle (intent → Guardian → approval → Runtime → Gateway
// → broker → fills → accounting → audit) + immutable fills. Read-only.
import { useParams } from "next/navigation";
import Link from "next/link";
import { Card, Heading, Text } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, DataTable, StateChip, Loading, LoadError, StatCard }
  from "@/components/trading/TradingShell";
import { useAuthMe, useResource, fetchers, fmtMoney, fmtNum, fmtTs } from "@/lib/trading";

const LIFECYCLE = ["intent", "Guardian", "approval", "Runtime", "ExecutionGateway", "paper broker", "fills", "accounting", "audit"];

export default function OrderDetailPage() {
  const { orderId } = useParams();
  const { token, ready } = useAuthMe();
  const ord = useResource(() => (token ? fetchers.order(token, orderId).then((r) => r.order) : Promise.resolve(null)), [token, orderId]);
  const fills = useResource(() => (token ? fetchers.fills(token, orderId).then((r) => r?.fills || []) : Promise.resolve([])), [token, orderId]);
  const o = ord.data;

  return (
    <div className="page shell-page">
      <TradingHeader title="Order" subtitle={<Link href="/trading/orders" style={{ color: "#5B8CFF", textDecoration: "none" }}>← All orders</Link>} />
      <TradingTabs />
      <SignInGate ready={ready} token={token}>
        <SafetyBanner severity="ok" />
        {ord.loading ? <Loading /> : null}
        <LoadError error={ord.error} />
        {o ? (
          <>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
              <StatCard label="Symbol" value={o.symbol} />
              <StatCard label="Side" value={o.side} />
              <StatCard label="State" value={<StateChip state={o.broker_state} />} />
              <StatCard label="Quantity" value={fmtNum(o.original_quantity, 4)} />
              <StatCard label="Filled" value={fmtNum(o.filled_quantity, 4)} />
              <StatCard label="Remaining" value={fmtNum(o.remaining_quantity, 4)} />
            </div>

            <Card style={{ marginBottom: 12 }}>
              <Heading level={3} size="sm">Order facts</Heading>
              <dl style={dl}>
                <Row k="Order ID" v={o.id} />
                <Row k="Intent" v={o.order_intent_id} />
                <Row k="Account" v={o.paper_account_id} />
                <Row k="Type" v={o.order_type} />
                <Row k="Limit price" v={o.limit_price ? fmtMoney(o.limit_price) : "—"} />
                <Row k="Idempotency key" v={o.idempotency_key || "—"} />
                <Row k="Correlation" v={o.correlation_id || "—"} />
                <Row k="Market data ref" v={o.market_data_ref || "—"} />
                <Row k="Rejection reason" v={o.rejection_reason || "—"} />
                <Row k="Submitted" v={fmtTs(o.submitted_at)} />
                <Row k="Completed" v={o.completed_at ? fmtTs(o.completed_at) : "—"} />
              </dl>
            </Card>

            <Card style={{ marginBottom: 12 }}>
              <Heading level={3} size="sm">Authority lifecycle</Heading>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                {LIFECYCLE.map((s, i) => (
                  <span key={s} className="mono" style={{ fontSize: 11, color: "var(--text-secondary)", border: "1px solid var(--border-subtle,#20242e)", borderRadius: 6, padding: "3px 8px" }}>
                    {i + 1}. {s}
                  </span>
                ))}
              </div>
              <Text tone="muted" size="xs" as="p" style={{ marginTop: 8 }}>
                Every paper mutation traverses this chain server-side. The browser never reaches the broker directly.
              </Text>
            </Card>

            <Card style={{ marginBottom: 12 }}>
              <Heading level={3} size="sm">State transitions</Heading>
              <DataTable
                columns={[
                  { key: "from_state", label: "From" },
                  { key: "to_state", label: "To", render: (r) => <StateChip state={r.to_state} /> },
                  { key: "reason", label: "Reason" },
                  { key: "ts", label: "When", render: (r) => fmtTs(r.ts) },
                ]}
                rows={o.transitions || []} getKey={(r, i) => `${r.ts}-${r.to_state}`} empty="No transitions" />
            </Card>

            <Card>
              <Heading level={3} size="sm">Immutable fills</Heading>
              <DataTable
                columns={[
                  { key: "seq", label: "#" },
                  { key: "quantity", label: "Qty", align: "right", render: (r) => fmtNum(r.quantity, 4) },
                  { key: "price", label: "Price", align: "right", render: (r) => fmtMoney(r.price) },
                  { key: "gross_amount", label: "Gross", align: "right", render: (r) => fmtMoney(r.gross_amount) },
                  { key: "fee", label: "Fee", align: "right", render: (r) => fmtMoney(r.fee) },
                  { key: "result_hash", label: "Result hash", render: (r) => (r.result_hash || "").slice(0, 10) || "—" },
                ]}
                rows={fills.data || []} getKey={(r) => r.id} empty="No fills" />
            </Card>
          </>
        ) : (!ord.loading && ready && token ? <Text tone="muted" as="p">Order not found for this tenant.</Text> : null)}
      </SignInGate>
    </div>
  );
}

const dl = { display: "grid", gap: 4, marginTop: 8, fontSize: 12.5 };
function Row({ k, v }) {
  return <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><dt style={{ color: "var(--text-muted)" }}>{k}</dt><dd className="mono" style={{ color: "var(--text-secondary)", textAlign: "right", wordBreak: "break-all" }}>{v}</dd></div>;
}
