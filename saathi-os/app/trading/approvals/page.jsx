"use client";
// M62.8 — Trading approvals view over the existing Approval Center (no trading-specific
// approval store). Surfaces reset approvals and their scope binding. Approval alone
// never removes a halt and never overrides failing technical checks.
import { useMemo, useState } from "react";
import { Card, Heading, Text } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, DataTable, StateChip, Loading, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe, useResource, fmtTs, shortHash, PERM, hasPerm } from "@/lib/trading";
import { plat } from "@/lib/platform-client";

const TRADING_TOOLS = ["paper_safety.reset", "paper.order.submit", "paper.order.cancel"];
const isTrading = (a) =>
  TRADING_TOOLS.includes(a.tool_id) || String(a.capability || "").startsWith("paper_") ||
  String(a.action || "").includes("paper");

export default function TradingApprovalsPage() {
  const { token, perms, ready } = useAuthMe();
  const canRead = hasPerm(perms, PERM.APPROVAL_READ) || hasPerm(perms, "approval.read");
  const appr = useResource(async () => {
    if (!token) return { rows: [], unavailable: false, denied: false };
    try {
      const r = await plat("/approvals?status=", { token });
      return { rows: r?.approvals || [], unavailable: false, denied: false };
    } catch (e) {
      if (e?.status === 403) return { rows: [], unavailable: false, denied: true };
      if (e?.status === 404) return { rows: [], unavailable: true, denied: false };
      throw e;
    }
  }, [token]);

  const data = appr.data || { rows: [], unavailable: false, denied: false };
  const [onlyTrading, setOnlyTrading] = useState(true);
  const rows = useMemo(() => {
    const all = data.rows || [];
    return (onlyTrading ? all.filter(isTrading) : all);
  }, [data.rows, onlyTrading]);

  return (
    <div className="page shell-page">
      <TradingHeader title="Approvals"
        subtitle="Server-authorized approvals from the Approval Center. Reset approvals are single-use and scope-bound." />
      <TradingTabs />
      <SignInGate ready={ready} token={token}>
        <SafetyBanner severity="ok" />

        <Card style={{ marginBottom: 12 }}>
          <Text size="sm" as="p" style={{ margin: 0 }}>
            <strong>Approval does not remove a halt.</strong> A reset approval only authorizes the reset
            <em> attempt</em>; the server re-runs reconciliation, market-data, accounting, threshold,
            broader-breaker and version checks at execution time. Approval cannot override a failing check.
            Paper approval never grants live-trading authority. Approved reset authorization is single-use and scope-bound.
          </Text>
        </Card>

        {appr.loading ? <Loading /> : null}
        <LoadError error={appr.error} />

        {data.denied || !canRead ? (
          <Card><Heading level={3} size="sm">Permission restricted</Heading>
            <Text tone="muted" size="sm" as="p">Your role cannot read approvals. Backend denial is authoritative.</Text></Card>
        ) : data.unavailable ? (
          <Card><Heading level={3} size="sm">Approvals unavailable</Heading>
            <Text tone="muted" size="sm" as="p">The Approval Center did not return data.</Text></Card>
        ) : (
          <>
            <div style={{ display: "flex", gap: 8, marginBottom: 10, alignItems: "center" }}>
              <button className="mono" data-testid="filter-trading" aria-pressed={onlyTrading}
                onClick={() => setOnlyTrading((v) => !v)}
                style={chip(onlyTrading)}>Trading-related only</button>
              <Text tone="muted" size="xs">{rows.length} shown</Text>
            </div>
            <DataTable
              testId="approvals-table"
              columns={[
                { key: "status", label: "Status", render: (r) => <StateChip state={String(r.status || "").toUpperCase()} /> },
                { key: "tool_id", label: "Tool / action", render: (r) => r.tool_id || r.action || "—" },
                { key: "capability", label: "Capability", render: (r) => r.capability || "—" },
                { key: "target_resource", label: "Scope binding (payload hash)", render: (r) => shortHash(r.target_resource, 12) },
                { key: "requested_by", label: "Requester", render: (r) => r.requested_by || r.user_id || "—" },
                { key: "decided_by", label: "Approver", render: (r) => r.decided_by || "—" },
                { key: "expires_at", label: "Expiry", render: (r) => fmtTs(r.expires_at) },
                { key: "consumed", label: "Single-use", render: (r) => (r.status === "consumed" || r.consumed_at ? "CONSUMED" : "unused") },
              ]}
              rows={rows} getKey={(r) => r.approval_id} empty="No approvals" />
            <Text tone="muted" size="xs" as="p" style={{ marginTop: 10 }}>
              Reset approvals bind to a specific breaker/trip/scope via the payload hash. A consumed approval is terminal and cannot be reused.
            </Text>
          </>
        )}
      </SignInGate>
    </div>
  );
}

function chip(active) {
  return { fontSize: 11, padding: "5px 10px", borderRadius: 8, cursor: "pointer",
    color: active ? "var(--text-primary)" : "var(--text-muted)",
    background: active ? "color-mix(in srgb,#5B8CFF 16%,transparent)" : "transparent",
    border: active ? "1px solid color-mix(in srgb,#5B8CFF 45%,transparent)" : "1px solid var(--border-subtle,#20242e)" };
}
