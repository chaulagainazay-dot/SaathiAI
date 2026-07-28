"use client";
// M63 — Applications launcher + unified, module-driven dashboard.
// Every card and widget here is derived from the platform module registry
// (lib/modules). No application is hard-coded into this page; adding a module
// registration makes it appear here automatically.
import Link from "next/link";
import { Card, Heading, Text } from "@/components/ui";
import { getRegistry } from "@/lib/modules/registry";
import { getDashboard } from "@/lib/modules/shell";

const HEALTH_COLOR = {
  healthy: "#22C55E",
  degraded: "#F59E0B",
  unknown: "#94A3B8",
  not_implemented: "#64748B",
};

function StatusChip({ status, health }) {
  const label = status === "enabled" ? health : status;
  const color = status === "enabled" ? HEALTH_COLOR[health] || "#94A3B8" : "#64748B";
  return (
    <span
      style={{
        fontSize: 11,
        padding: "2px 8px",
        borderRadius: 999,
        border: `1px solid ${color}`,
        color,
        textTransform: "capitalize",
      }}
    >
      {String(label).replace(/_/g, " ")}
    </span>
  );
}

function ModuleCard({ card }) {
  const enabled = card.status === "enabled";
  const inner = (
    <Card style={{ display: "flex", flexDirection: "column", gap: 10, height: "100%", opacity: enabled ? 1 : 0.7 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 22 }}>{card.icon}</span>
          <Heading level={3} style={{ margin: 0 }}>{card.title}</Heading>
        </div>
        <StatusChip status={card.status} health={card.health} />
      </div>
      <Text tone="muted" style={{ fontSize: 13 }}>{card.description}</Text>
      {card.widgets?.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: "auto" }}>
          {card.widgets.map((w) => (
            <span
              key={w.id}
              style={{
                fontSize: 11,
                padding: "2px 8px",
                borderRadius: 6,
                background: "rgba(148,163,184,0.12)",
              }}
            >
              {w.title}
            </span>
          ))}
        </div>
      )}
    </Card>
  );
  return enabled && card.primaryRoute ? (
    <Link href={card.primaryRoute} style={{ textDecoration: "none", color: "inherit" }}>
      {inner}
    </Link>
  ) : (
    <div aria-disabled={!enabled} title={enabled ? "" : "Coming soon"}>{inner}</div>
  );
}

export default function AppsPage() {
  const registry = getRegistry();
  const dash = getDashboard(registry);

  return (
    <main style={{ padding: "24px", maxWidth: 1100, margin: "0 auto" }}>
      <header style={{ marginBottom: 20 }}>
        <Heading level={1} style={{ margin: 0 }}>Applications</Heading>
        <Text tone="muted">
          {dash.enabledCount} enabled · {dash.installedCount} installed · module-driven platform shell
        </Text>
      </header>

      <section
        aria-label="Installed applications"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
          gap: 16,
        }}
      >
        {dash.cards.map((card) => (
          <ModuleCard key={card.moduleId} card={card} />
        ))}
      </section>

      <footer style={{ marginTop: 28 }}>
        <Text tone="muted" style={{ fontSize: 12 }}>
          Trading is the first fully integrated module. Platform services (Runtime, Approval Center,
          Evidence, Notifications, Identity, RBAC) remain centralized; applications extend the
          platform through the module contract.
        </Text>
      </footer>
    </main>
  );
}
