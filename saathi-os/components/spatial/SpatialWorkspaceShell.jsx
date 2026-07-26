"use client";
// M59 — shared spatial workspace shell for every Glass Frame platform route.
//
// Provides: deep spatial canvas, compact system-status strip, floating nav
// dock, breadcrumb, route title + compact state, command palette (⌘K), a
// route-level error boundary, and loading/unavailable states. Reduced-motion
// safe and responsive. Pages compose their content as children and pass a
// `commands` list built from their own already-fetched authorized data.
import { Component, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { SystemStatusStrip, StatusPulse, SafetyBoundaryBadge, useReducedMotion } from "./frame";
import { SpatialCommandPalette } from "./SpatialCommandPalette";
import { buildCommands } from "@/lib/workspace";

const NAV = [
  { id: "home", label: "Home", route: "/platform", glyph: "◈" },
  { id: "workflows", label: "Workflows", route: "/platform/workflows", glyph: "❖" },
  { id: "missions", label: "Missions", route: "/platform/missions", glyph: "◎" },
  { id: "agents", label: "Agents", route: "/platform/agents", glyph: "✦" },
  { id: "approvals", label: "Approvals", route: "/platform/approvals", glyph: "⎈" },
  { id: "attention", label: "Attention", route: "/platform/attention", glyph: "△" },
  { id: "actions", label: "Actions", route: "/platform/actions", glyph: "◇" },
  { id: "notifications", label: "Notifications", route: "/platform/notifications", glyph: "◐" },
  { id: "evidence", label: "Evidence", route: "/platform/evidence", glyph: "❑" },
  { id: "operations", label: "Operations", route: "/platform/ops", glyph: "▤" },
  { id: "settings", label: "Settings", route: "/settings", glyph: "⚙" },
];

/* --- route-level error boundary: never leaks a stack trace to the operator --- */
class WorkspaceErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="glass-frame glass-frame--danger" style={{ padding: "var(--space-5)", margin: "var(--space-6) auto", maxWidth: 620 }} role="alert">
          <div className="eyebrow" style={{ color: "var(--signal-danger)" }}>Unknown error</div>
          <p style={{ color: "var(--text-secondary)", marginTop: 8 }}>
            This workspace hit an unexpected client error and stopped rendering to stay safe.
          </p>
          <p className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginTop: 8 }}>
            {String(this.state.error?.message || this.state.error).slice(0, 200)}
          </p>
          <button
            onClick={() => this.setState({ error: null })}
            style={{ marginTop: 14, background: "transparent", border: "1px solid var(--glass-frame-border)", color: "var(--text-primary)", borderRadius: 8, padding: "6px 14px", cursor: "pointer" }}
          >
            Retry render
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function NavDock({ pathname }) {
  const router = useRouter();
  const currentId = useMemo(() => {
    const hit = [...NAV]
      .sort((a, b) => b.route.length - a.route.length)
      .find((n) => pathname === n.route || pathname.startsWith(`${n.route}/`));
    return hit?.id;
  }, [pathname]);
  return (
    <nav className="spatial-dock spatial-dock--fixed" aria-label="Workspace navigation">
      {NAV.map((n) => {
        const active = n.id === currentId;
        return (
          <button
            key={n.id}
            className="dock-item"
            aria-current={active ? "page" : undefined}
            aria-label={n.label}
            title={n.label}
            onClick={() => router.push(n.route)}
          >
            <span aria-hidden="true" className="dock-item__glyph">{n.glyph}</span>
            <span className="dock-item__label">{n.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

export function SpatialWorkspaceShell({
  title,
  subtitle,
  breadcrumb = [],
  signal = "idle",
  health,
  loading = false,
  error = null,
  commands: extraCommands,
  paletteData,
  children,
  onToggleMotion,
}) {
  const router = useRouter();
  const pathname = usePathname() || "/platform";
  const reduced = useReducedMotion();
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    // Capture phase + stopImmediatePropagation so the SPATIAL palette wins ⌘K
    // and the pre-existing global app-shell palette does NOT also open on these
    // workspace routes (avoids a double-palette conflict and keeps the surface
    // axe-clean).
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        e.stopImmediatePropagation();
        setPaletteOpen((v) => !v);
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, []);

  const commands = useMemo(() => {
    if (extraCommands) return extraCommands;
    const actions = [];
    if (onToggleMotion) actions.push({ id: "toggle-motion", label: "Toggle reduced motion preference", group: "Preferences", type: "action" });
    return buildCommands({ ...(paletteData || {}), actions });
  }, [extraCommands, paletteData, onToggleMotion]);

  const onRun = useCallback(
    (cmd) => {
      if (cmd.type === "action" && cmd.id === "toggle-motion") {
        onToggleMotion?.();
        return true;
      }
      if (cmd.type === "help") {
        router.push("/platform");
        return true;
      }
      return false;
    },
    [onToggleMotion, router]
  );

  return (
    <div className="spatial-scope">
      <div className="spatial-canvas" style={{ padding: "var(--space-6) var(--space-5) var(--space-8)" }}>
        {!reduced && <div className="spatial-particles" aria-hidden="true" />}

        <NavDock pathname={pathname} />

        <button
          className="cmdk-fab"
          aria-label="Open command palette"
          onClick={() => setPaletteOpen(true)}
        >
          ⌘K
        </button>

        <div className="workspace-main" style={{ position: "relative", zIndex: 1, maxWidth: 1160, margin: "0 auto", display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
          {/* ---- system status strip ---- */}
          <SystemStatusStrip>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <StatusPulse signal={signal} size={9} />
              <span className="mono" style={{ fontSize: "var(--fs-xs)", letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--text-primary)" }}>
                SaathiOS
              </span>
            </span>
            {health ? (
              <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>
                Identity {health.identity} · RBAC {health.rbac} · Gateway {health.runtime?.gateway}
              </span>
            ) : (
              <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>Health unavailable</span>
            )}
            <div style={{ display: "flex", gap: 8, marginLeft: "auto", flexWrap: "wrap" }}>
              <SafetyBoundaryBadge label="Private Alpha" tone="active" />
              <SafetyBoundaryBadge label="Non-production" tone="attention" />
              <SafetyBoundaryBadge label="Trading disabled" tone="idle" />
            </div>
          </SystemStatusStrip>

          {/* ---- breadcrumb + title ---- */}
          <div>
            {breadcrumb.length > 0 && (
              <nav aria-label="Breadcrumb" style={{ marginBottom: 6 }}>
                <ol style={{ display: "flex", flexWrap: "wrap", gap: 6, listStyle: "none", margin: 0, padding: 0, fontSize: "var(--fs-2xs)" }}>
                  {breadcrumb.map((b, i) => (
                    <li key={`${b.label}-${i}`} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                      {b.href ? (
                        <button onClick={() => router.push(b.href)} className="crumb-link" style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", padding: 0, font: "inherit" }}>
                          {b.label}
                        </button>
                      ) : (
                        <span style={{ color: "var(--text-secondary)" }}>{b.label}</span>
                      )}
                      {i < breadcrumb.length - 1 && <span aria-hidden="true" style={{ color: "var(--text-muted)" }}>/</span>}
                    </li>
                  ))}
                </ol>
              </nav>
            )}
            {title && (
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <StatusPulse signal={signal} size={10} label={`${title} status`} />
                <h1 className="display" style={{ fontSize: "var(--fs-2xl)", margin: 0, letterSpacing: "0.01em" }}>{title}</h1>
                {loading && <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }} role="status">Loading…</span>}
              </div>
            )}
            {subtitle && <p style={{ color: "var(--text-muted)", marginTop: 6, maxWidth: 720 }}>{subtitle}</p>}
          </div>

          {error && (
            <div className="glass-frame glass-frame--danger" style={{ padding: "var(--space-4)" }} role="alert">
              <span className="eyebrow" style={{ color: "var(--signal-danger)" }}>Workspace error</span>
              <p style={{ color: "var(--text-secondary)", marginTop: 6 }}>{String(error)}</p>
            </div>
          )}

          <WorkspaceErrorBoundary>{children}</WorkspaceErrorBoundary>
        </div>
      </div>

      <SpatialCommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} onRun={onRun} />
    </div>
  );
}

export { NAV as WORKSPACE_NAV };
