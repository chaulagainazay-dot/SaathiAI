import Link from "next/link";

const ITEMS = [
  { href: "/trading/provider-contracts", label: "Providers" },
  { href: "/trading/provider-contracts/capabilities", label: "Capabilities" },
  { href: "/trading/provider-contracts/replay", label: "Replay" },
];

export function ProviderContractsNav() {
  return (
    <nav aria-label="Provider contract views" data-testid="provider-contracts-nav"
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

export function OfflineProviderBoundary() {
  return (
    <div data-testid="provider-offline-boundary" role="note"
      style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
      {[
        "MOCK CONNECTIVITY ONLY",
        "NO REAL PROVIDER",
        "NO HTTP / WEBSOCKET",
        "NO CREDENTIALS / OAUTH",
        "NO ACCOUNT ACCESS",
        "NO ORDERS",
        "NO CANARY",
        "NO LIVE TRADING",
      ].map((label) => (
        <span key={label} className="mono" style={{ fontSize: 10.5, padding: "3px 8px",
          border: "1px solid var(--border-subtle,#2a2f3a)", borderRadius: 999,
          color: label.startsWith("MOCK") ? "var(--signal-ok,#10C98A)" : "var(--signal-danger,#FF5A5A)" }}>
          {label}
        </span>
      ))}
    </div>
  );
}
