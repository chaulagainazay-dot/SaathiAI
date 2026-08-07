import Link from "next/link";

const ITEMS = [
  { href: "/trading/operations", label: "Control Center" },
  { href: "/trading/operations/health", label: "System Health" },
  { href: "/trading/operations/metrics", label: "Metrics" },
  { href: "/trading/operations/alerts", label: "Alerts" },
  { href: "/trading/operations/diagnostics", label: "Diagnostics" },
  { href: "/trading/operations/backups", label: "Backups" },
];

export function OperationsNav() {
  return (
    <nav aria-label="Operations views" data-testid="operations-nav"
      style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
      {ITEMS.map((item) => (
        <Link key={item.href} href={item.href} className="mono"
          style={{ fontSize: 12, textDecoration: "none", color: "var(--text-secondary)",
            border: "1px solid var(--border-subtle,#2a2f3a)", borderRadius: 8,
            padding: "6px 10px" }}>
          {item.label}
        </Link>
      ))}
    </nav>
  );
}

/** M328–M335 boundary rail. Every label here is asserted by the browser cert. */
export function OperationsBoundary() {
  return (
    <div data-testid="operations-boundary" role="note"
      style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
      {[
        "OFFLINE OPERATIONS DATA",
        "READ-ONLY DASHBOARD",
        "NO EXECUTION CONTROLS",
        "NO DEPLOYMENT CONTROLS",
        "NO EXTERNAL TELEMETRY",
        "NO CLOUD MONITORING",
        "NO CLOUD BACKUP",
        "NO EMAIL, SMS, OR PUSH ALERTING",
      ].map((label) => (
        <span key={label} className="mono" style={{ fontSize: 10.5, padding: "3px 8px",
          border: "1px solid var(--border-subtle,#2a2f3a)", borderRadius: 999,
          color: label.startsWith("NO ") ? "var(--signal-danger,#FF5A5A)" : "var(--signal-ok,#10C98A)" }}>
          {label}
        </span>
      ))}
    </div>
  );
}

/** The authority boundary. All eleven hard locks must render as false. */
export function OperationsAuthorityBoundary() {
  return (
    <div data-testid="operations-authority-boundary" className="mono"
      style={{ fontSize: 11, lineHeight: 1.7, marginBottom: 16, padding: "10px 12px",
        border: "1px solid var(--border-subtle,#2a2f3a)", borderRadius: 10,
        color: "var(--text-secondary)" }}>
      <div data-testid="operations-maturity">Current maturity: OPERATIONALLY_READY_OFFLINE</div>
      <div data-testid="operations-max-state">Maximum: OPERATIONALLY_READY_OFFLINE</div>
      <div data-testid="operations-authority-locks">
        REAL_CONNECTIVITY_AUTHORIZED=false · BROKER_CONNECTIVITY_AUTHORIZED=false ·
        OAUTH_AUTHORIZED=false · CREDENTIAL_PROVISIONING_AUTHORIZED=false ·
        ACCOUNT_ACCESS_AUTHORIZED=false · BALANCE_READ_AUTHORIZED=false ·
        POSITION_READ_AUTHORIZED=false · ORDER_SUBMISSION_AUTHORIZED=false ·
        ORDER_EXECUTION_AUTHORIZED=false · CANARY_ACTIVATION_AUTHORIZED=false ·
        LIVE_TRADING_AUTHORIZED=false
      </div>
    </div>
  );
}

const HEALTH_TONE = {
  HEALTHY: "var(--signal-ok,#10C98A)",
  MAINTENANCE: "var(--text-secondary)",
  WARNING: "var(--signal-warn,#F5A524)",
  DEGRADED: "var(--signal-warn,#F5A524)",
  FAILED: "var(--signal-danger,#FF5A5A)",
};

export function HealthPill({ state }) {
  return (
    <span className="mono" data-testid={`health-pill-${state}`}
      style={{ fontSize: 10.5, padding: "3px 8px", borderRadius: 999,
        border: "1px solid var(--border-subtle,#2a2f3a)",
        color: HEALTH_TONE[state] || "var(--text-secondary)" }}>
      {state}
    </span>
  );
}
