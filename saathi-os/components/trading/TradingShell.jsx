"use client";
// M62.8 — shared Trading Operator Workspace chrome: sub-navigation, proportional
// safety banner, auth gate, and small presentational parts. Read-only presentation;
// all authority stays on the server.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Heading, Text, Badge, StatusBadge, Spinner, EmptyState, ErrorState } from "@/components/ui";
import { SAFETY_BANNER, stateTone } from "@/lib/trading";

const TABS = [
  { href: "/trading", label: "Overview" },
  { href: "/trading/accounts", label: "Accounts" },
  { href: "/trading/orders", label: "Orders" },
  { href: "/trading/positions", label: "Positions" },
  { href: "/trading/strategies", label: "Strategies" },
  { href: "/trading/regime", label: "Regime" },
  { href: "/trading/proposals", label: "Proposals" },
  { href: "/trading/backtests", label: "Backtest Lab" },
  { href: "/trading/research", label: "Research Lab" },
  { href: "/trading/historical", label: "Historical Data" },
  { href: "/trading/monte-carlo", label: "Monte Carlo" },
  { href: "/trading/qualification", label: "Qualification" },
  { href: "/trading/paper-portfolio", label: "Paper Portfolio" },
  { href: "/trading/paper-orders", label: "Paper Orders" },
  { href: "/trading/paper-journal", label: "Paper Journal" },
  { href: "/trading/paper-risk", label: "Paper Risk" },
  { href: "/trading/paper-approvals", label: "Paper Approvals" },
  { href: "/trading/paper-analytics", label: "Paper Analytics" },
  { href: "/trading/paper-reconcile", label: "Paper Reconcile" },
  { href: "/trading/paper-ops", label: "Paper Ops" },
  { href: "/trading/paper-campaigns", label: "Campaigns" },
  { href: "/trading/ops-graduation", label: "Ops Graduation" },
  { href: "/trading/broker-sandbox", label: "Broker Sandbox" },
  { href: "/trading/broker-readiness", label: "Broker Readiness" },
  { href: "/trading/integration-assurance", label: "Integration Assurance" },
  { href: "/trading/paper-ledger", label: "Ledger" },
  { href: "/trading/paper-recovery", label: "Recovery" },
  { href: "/trading/comparison", label: "Comparison" },
  { href: "/trading/journal", label: "Journal" },
  { href: "/trading/policy", label: "Policy" },
  { href: "/trading/reconciliation", label: "Reconciliation" },
  { href: "/trading/safety", label: "Safety" },
  { href: "/trading/approvals", label: "Approvals" },
  { href: "/trading/evidence", label: "Evidence" },
];

const TONE_COLOR = {
  ok: "var(--status-ok, #10C98A)", warn: "var(--status-warn, #F5A623)",
  danger: "var(--status-danger, #FF5A5A)", idle: "var(--text-muted, #8FA0C4)",
  active: "#5B8CFF",
};

export function toneColor(t) { return TONE_COLOR[t] || TONE_COLOR.idle; }

export function SafetyBanner({ severity = "ok" }) {
  // Proportional: neutral rail when healthy, amber/red only for real posture.
  const color = toneColor(severity);
  return (
    <div role="note" aria-label="Paper trading safety notice" data-testid="safety-banner"
      style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center",
        border: `1px solid color-mix(in srgb, ${color} 35%, transparent)`,
        background: `color-mix(in srgb, ${color} 8%, transparent)`,
        borderRadius: 10, padding: "8px 12px", marginBottom: 14 }}>
      {SAFETY_BANNER.map((t) => (
        <span key={t} className="mono" style={{ fontSize: 11, letterSpacing: 0.5, color: "var(--text-secondary)",
          border: "1px solid var(--border-subtle,#2a2f3a)", borderRadius: 6, padding: "2px 7px" }}>{t}</span>
      ))}
    </div>
  );
}

export function TradingTabs() {
  const pathname = usePathname() || "/trading";
  return (
    <nav aria-label="Trading workspace" style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 16,
      borderBottom: "1px solid var(--border-subtle,#20242e)", paddingBottom: 6 }}>
      {TABS.map((t) => {
        const active = t.href === "/trading" ? pathname === "/trading" : pathname.startsWith(t.href);
        return (
          <Link key={t.href} href={t.href} aria-current={active ? "page" : undefined}
            className="mono" style={{ fontSize: 12, padding: "6px 12px", borderRadius: 8,
              textDecoration: "none", color: active ? "var(--text-primary)" : "var(--text-muted)",
              background: active ? "color-mix(in srgb, #5B8CFF 16%, transparent)" : "transparent",
              border: active ? "1px solid color-mix(in srgb, #5B8CFF 45%, transparent)" : "1px solid transparent" }}>
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function TradingHeader({ title, subtitle, severity = "ok", right }) {
  return (
    <div className="shell-page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
      <div>
        <Text tone="muted" size="xs" mono>Run the business · Trading · Paper</Text>
        <Heading level={1} size="xl">{title}</Heading>
        {subtitle ? <Text tone="muted" size="sm" as="p" style={{ marginTop: 4, maxWidth: 720 }}>{subtitle}</Text> : null}
      </div>
      {right}
    </div>
  );
}

export function SignInGate({ ready, token, children }) {
  const router = useRouter();
  if (!ready) return <div style={{ padding: 40, textAlign: "center" }}><Spinner size={22} /></div>;
  if (!token) {
    return (
      <div className="glass-frame" style={{ padding: 28, maxWidth: 540, margin: "32px auto" }} role="region" aria-label="Authentication required">
        <div className="eyebrow" style={{ color: "var(--signal-attention,#F5A623)" }}>Authentication required</div>
        <p style={{ color: "var(--text-secondary)", marginTop: 8 }}>
          The Trading Operator Workspace requires an active platform session. Sign in from Home. All
          execution stays governed by PlatformAgentRuntime and ExecutionGateway; paper-only, localhost-only.
        </p>
        <button onClick={() => router.push("/platform")} style={{ marginTop: 14, background: "color-mix(in srgb, #5B8CFF 18%, transparent)",
          border: "1px solid color-mix(in srgb, #5B8CFF 50%, transparent)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 16px", cursor: "pointer" }}>
          Go to Home to sign in →
        </button>
      </div>
    );
  }
  return children;
}

// ── small presentational parts ─────────────────────────────────────────────────
export function StatCard({ label, value, tone = "idle", hint }) {
  return (
    <div className="glass-frame" style={{ padding: "12px 14px", minWidth: 140, flex: "1 1 140px" }}>
      <div className="mono" style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--text-muted)" }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 600, marginTop: 4, color: toneColor(tone) === TONE_COLOR.idle ? "var(--text-primary)" : toneColor(tone) }}>{value}</div>
      {hint ? <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{hint}</div> : null}
    </div>
  );
}

export function StateChip({ state }) {
  const tone = stateTone(state);
  return (
    <span data-testid={`state-${state}`} style={{ display: "inline-block", fontSize: 11, fontWeight: 600, padding: "2px 9px", borderRadius: 999,
      color: toneColor(tone), background: `color-mix(in srgb, ${toneColor(tone)} 14%, transparent)`,
      border: `1px solid color-mix(in srgb, ${toneColor(tone)} 40%, transparent)` }}>{state}</span>
  );
}

export function DataTable({ columns, rows, empty = "No records", onRow, getKey, testId }) {
  if (!rows || rows.length === 0) return <EmptyState title={empty} />;
  return (
    <div style={{ overflowX: "auto" }} data-testid={testId}>
      <table className="mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" style={{ textAlign: c.align || "left", padding: "8px 10px", color: "var(--text-muted)",
                borderBottom: "1px solid var(--border-subtle,#20242e)", fontWeight: 500, whiteSpace: "nowrap" }}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={getKey ? getKey(r) : i} onClick={onRow ? () => onRow(r) : undefined}
              tabIndex={onRow ? 0 : undefined} role={onRow ? "button" : undefined}
              onKeyDown={onRow ? (e) => { if (e.key === "Enter") onRow(r); } : undefined}
              style={{ cursor: onRow ? "pointer" : "default", borderBottom: "1px solid var(--border-subtle,#171b22)" }}>
              {columns.map((c) => (
                <td key={c.key} style={{ textAlign: c.align || "left", padding: "8px 10px", whiteSpace: c.wrap ? "normal" : "nowrap", color: "var(--text-secondary)" }}>
                  {c.render ? c.render(r) : (r[c.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Loading() { return <div style={{ padding: 40, textAlign: "center" }}><Spinner size={20} /></div>; }
export function LoadError({ error }) { return error ? <ErrorState title="Could not load" detail={String(error)} /> : null; }
export { StatusBadge, Badge };
