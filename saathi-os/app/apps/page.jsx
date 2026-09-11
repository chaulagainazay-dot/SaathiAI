"use client";
// M64 — Applications launcher + unified dashboard, driven by the AUTHORITATIVE
// backend module registry (GET /api/v1/platform/modules) via useModuleDiscovery.
// The static mirror is used only as a non-operational loading skeleton. Module
// availability, health, and actionability come from the backend `state` — never
// computed in the browser, never granted by the mirror.
import Link from "next/link";
import { Card, Heading, Text, Button } from "@/components/ui";
import { useModuleDiscoveryContext } from "@/lib/modules/ModuleDiscoveryContext";
import { safeIcon } from "@/lib/modules/icons";
import { BOOT } from "@/lib/modules/bootstrap";

const STATE_META = {
  available: { label: "Available", color: "#22C55E", actionable: true },
  degraded: { label: "Degraded", color: "#F59E0B", actionable: false },
  unavailable: { label: "Unavailable", color: "#EF4444", actionable: false },
  disabled: { label: "Disabled", color: "#64748B", actionable: false },
  not_implemented: { label: "Coming soon", color: "#64748B", actionable: false },
  permission_restricted: { label: "Restricted", color: "#94A3B8", actionable: false },
  unknown: { label: "Loading…", color: "#94A3B8", actionable: false },
};

function StateChip({ state }) {
  const m = STATE_META[state] || STATE_META.unknown;
  return (
    <span
      role="status"
      aria-label={`Status: ${m.label}`}
      style={{ fontSize: 11, padding: "2px 8px", borderRadius: 999, border: `1px solid ${m.color}`, color: m.color }}
    >
      {m.label}
    </span>
  );
}

function ModuleCard({ card }) {
  const meta = STATE_META[card.state] || STATE_META.unknown;
  const actionable = card.actionable === true && meta.actionable && !!card.primary_route;
  const body = (
    <Card style={{ display: "flex", flexDirection: "column", gap: 10, height: "100%", opacity: card.stale ? 0.5 : actionable ? 1 : 0.75 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 22 }} aria-hidden="true">{safeIcon(card.icon)}</span>
          <Heading level={3} style={{ margin: 0 }}>{card.title || card.name}</Heading>
        </div>
        <StateChip state={card.state} />
      </div>
      {card.description && <Text tone="muted" style={{ fontSize: 13 }}>{card.description}</Text>}
      {card.widgets?.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: "auto" }}>
          {card.widgets.map((w) => (
            <span key={w.id} style={{ fontSize: 11, padding: "2px 8px", borderRadius: 6, background: "rgba(148,163,184,0.12)" }}>
              {w.title}
            </span>
          ))}
        </div>
      )}
    </Card>
  );
  return actionable ? (
    <Link href={card.primary_route} style={{ textDecoration: "none", color: "inherit" }}>{body}</Link>
  ) : (
    <div aria-disabled="true" title={meta.label}>{body}</div>
  );
}

function Banner({ tone = "muted", children, action }) {
  const color = tone === "danger" ? "#EF4444" : tone === "warn" ? "#F59E0B" : "#94A3B8";
  return (
    <div style={{ border: `1px solid ${color}`, borderRadius: 8, padding: "12px 16px", marginBottom: 16, display: "flex", gap: 12, alignItems: "center" }}>
      <Text style={{ color }}>{children}</Text>
      {action}
    </div>
  );
}

export default function AppsPage() {
  const disc = useModuleDiscoveryContext();

  // Cards: backend when ready; non-operational skeleton while loading.
  const loading = disc.phase === BOOT.INITIALIZING || disc.phase === BOOT.LOADING_CONTEXT || disc.phase === BOOT.LOADING_MODULES;
  const cards = disc.isReady
    ? disc.cards
    : disc.fallback.map((f) => ({ module_id: f.id, title: f.name, icon: f.icon, state: "unknown", stale: true, actionable: false }));

  return (
    <main style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>
      <header style={{ marginBottom: 20 }}>
        <Heading level={1} style={{ margin: 0 }}>Applications</Heading>
        <Text tone="muted">
          Backend-authoritative module discovery{disc.contractVersion ? ` · ${disc.contractVersion}` : ""}
        </Text>
      </header>

      {disc.phase === BOOT.AUTH_REQUIRED && (
        <Banner tone="warn" action={<Link href="/unlock"><Button>Sign in</Button></Link>}>
          Sign in to load your applications.
        </Banner>
      )}
      {disc.phase === BOOT.SESSION_EXPIRED && (
        <Banner tone="danger" action={<Link href="/unlock"><Button>Sign in</Button></Link>}>
          Your session expired. Module state was cleared.
        </Banner>
      )}
      {disc.phase === BOOT.PERMISSION_RESTRICTED && (
        <Banner tone="warn">You do not have permission to view platform modules.</Banner>
      )}
      {disc.phase === BOOT.OFFLINE && (
        <Banner tone="danger" action={<Button onClick={disc.retry}>Retry</Button>}>
          Platform backend unavailable.
        </Banner>
      )}
      {disc.phase === BOOT.ERROR && (
        <Banner tone="danger" action={<Button onClick={disc.retry}>Retry</Button>}>
          Could not load modules ({disc.errorCategory}).
        </Banner>
      )}
      {disc.phase === BOOT.DEGRADED && (
        <Banner tone="warn">Some modules report degraded health.</Banner>
      )}
      {loading && <Banner tone="muted">Loading applications…</Banner>}

      <section
        aria-label="Installed applications"
        aria-busy={loading}
        style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 16 }}
      >
        {cards.map((card) => (
          <ModuleCard key={card.module_id} card={card} />
        ))}
      </section>

      <footer style={{ marginTop: 28 }}>
        <Text tone="muted" style={{ fontSize: 12 }}>
          Module availability, health, and routes come from the authenticated backend registry.
          The frontend mirror is a non-operational skeleton and grants no capability. Platform
          services (Runtime, Approval Center, Evidence, Notifications, Identity, RBAC) remain centralized.
        </Text>
      </footer>
    </main>
  );
}