/**
 * M63 — Shell composition.
 *
 * Composes the platform shell's data-driven surfaces from (a) the platform's own
 * navigation groups (navigation.js — Operate/Work/Business/System, owned by the
 * platform core) and (b) the module registry's Applications group + Administration.
 *
 * The shell never hard-codes an application: the Applications group is derived
 * entirely from module registrations.
 */
import { NAV_GROUPS } from "../navigation.js";
import { getRegistry } from "./registry.js";

/** Administration group (platform-owned; centralized services). */
export const ADMIN_GROUP = {
  id: "administration",
  label: "Administration",
  items: [
    { id: "settings", label: "Settings", href: "/settings", icon: "⚙" },
    { id: "identity", label: "Identity", href: "/me", icon: "👤" },
    { id: "organizations", label: "Organizations", href: "/settings", icon: "▢" },
    { id: "permissions", label: "Permissions", href: "/security", icon: "▤" },
    { id: "health", label: "Health", href: "/monitoring", icon: "♥" },
    { id: "diagnostics", label: "Diagnostics", href: "/infrastructure", icon: "⚑" },
  ],
};

/**
 * The full shell navigation: platform groups + a data-driven Applications group
 * + Administration. Applications come from the registry, not from a hard-coded list.
 * @param {import('./registry.js').ModuleRegistry} [registry]
 */
export function getShellNavigation(registry = getRegistry()) {
  const appsNav = registry.navigation();
  const applicationsGroup = {
    id: "applications",
    label: "Applications",
    items: appsNav.modules.map((m) => ({
      id: m.id,
      label: m.label,
      href: (m.items && m.items[0] && m.items[0].href) || `/${m.id}`,
      icon: m.icon,
      status: m.status,
      badge: m.status === "placeholder" ? "soon" : undefined,
    })),
  };
  return {
    platform: NAV_GROUPS,
    applications: applicationsGroup,
    administration: ADMIN_GROUP,
    groups: [...NAV_GROUPS, applicationsGroup, ADMIN_GROUP],
  };
}

/** Module-driven unified dashboard payload. */
export function getDashboard(registry = getRegistry()) {
  return {
    cards: registry.dashboardCards(),
    widgets: registry.widgets(),
    health: registry.healthReport(),
    enabledCount: registry.listEnabled().length,
    installedCount: registry.listInstalled().length,
  };
}

/** Aggregate search providers contributed by modules (interface only). */
export function getSearchProviders(registry = getRegistry()) {
  return registry.searchProviders();
}

/** Aggregate workspace views contributed by modules. */
export function getWorkspaceViews(registry = getRegistry()) {
  return registry.workspaceViews();
}
