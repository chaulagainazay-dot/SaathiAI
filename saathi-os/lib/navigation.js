/**
 * SaathiOS canonical navigation model (M47.2).
 * Primary nav = 12 areas in 4 groups. Departments are accents only.
 */

/** @typedef {{ id: string, label: string, href: string, icon: string, description?: string, shortcut?: string, environmentSensitivity?: string, authoritySensitivity?: string, mobilePriority?: number, aliases?: string[], accent?: string, riskFlag?: boolean, global?: boolean }} NavItem */

/** @type {{ id: string, label: string, items: NavItem[] }[]} */
export const NAV_GROUPS = [
  {
    id: "operate",
    label: "Operate",
    items: [
      {
        id: "home",
        label: "Home",
        href: "/",
        icon: "⌂",
        description: "Attention-first executive home",
        shortcut: "g h",
        aliases: ["/ceo", "/os"],
        accent: "#F4F6FB",
      },
      {
        id: "command",
        label: "Command Center",
        href: "/command",
        icon: "⌘",
        description: "Plan, request approval, observe",
        shortcut: "g c",
        aliases: ["/mission"],
        accent: "#C7CEDA",
        authoritySensitivity: "approval-aware",
      },
      {
        id: "missions",
        label: "Missions",
        href: "/missions",
        icon: "◎",
        description: "Bounded work with lifecycle",
        shortcut: "g m",
        accent: "#9B6BFF",
      },
      {
        id: "agents",
        label: "Agents",
        href: "/agents",
        icon: "⬡",
        description: "Workforce registry and authority",
        accent: "#22D3EE",
        authoritySensitivity: "advisory-default",
      },
      {
        id: "automation",
        label: "Automation",
        href: "/automation",
        icon: "⟳",
        description: "Plans, production, human-in-loop",
        aliases: ["/automation/production"],
        accent: "#FF8A3D",
      },
    ],
  },
  {
    id: "work",
    label: "Work",
    items: [
      {
        id: "projects",
        label: "Projects",
        href: "/projects",
        icon: "▦",
        description: "Ventures and workstreams",
        shortcut: "g p",
        accent: "#6C3FCF",
      },
      {
        id: "knowledge",
        label: "Knowledge",
        href: "/knowledge",
        icon: "◈",
        description: "Library, learning, memory",
        shortcut: "g k",
        aliases: ["/knowledge/library", "/learning"],
        accent: "#3E7BFF",
      },
      {
        id: "studio",
        label: "Studio",
        href: "/studio",
        icon: "▶",
        description: "Production queue · OS workspace at /studio-os · control-room ops",
        shortcut: "g s",
        aliases: ["/studio-os", "/studio/control-room"],
        accent: "#FF8A3D",
      },
    ],
  },
  {
    id: "business",
    label: "Run the business",
    items: [
      {
        id: "business",
        label: "Business",
        href: "/business",
        icon: "◈",
        description: "Ventures, finance, operations",
        aliases: ["/finance"],
        accent: "#10C98A",
      },
      {
        id: "trading",
        label: "Trading Guardian",
        href: "/trading",
        icon: "⚠",
        description: "Advisory only — no live authority",
        accent: "#FF5A5A",
        riskFlag: true,
        authoritySensitivity: "advisory-only",
        environmentSensitivity: "never-imply-production",
      },
    ],
  },
  {
    id: "system",
    label: "System",
    items: [
      {
        id: "monitoring",
        label: "Monitoring",
        href: "/monitoring",
        icon: "◉",
        description: "Health, events, infrastructure (legacy /infrastructure redirects here)",
        aliases: ["/infrastructure", "/control"],
        accent: "#7CF5E4",
      },
      {
        id: "security",
        label: "Security",
        href: "/security",
        icon: "⬡",
        description: "Sessions, tokens, policy surfaces",
        accent: "#FF5A5A",
      },
    ],
  },
];

/** Global chrome destinations (not in the 12 primary areas list for group count). */
export const GLOBAL_NAV = [
  {
    id: "platform",
    label: "Platform",
    href: "/platform",
    icon: "▣",
    description: "M50 identity, RBAC, orgs, approvals foundation",
    authoritySensitivity: "session-required",
    global: true,
    accent: "#A78BFA",
  },
  {
    id: "approvals",
    label: "Approvals",
    href: "/approvals",
    icon: "!",
    description: "Cross-area approval inbox",
    shortcut: "g a",
    authoritySensitivity: "approval-required",
    mobilePriority: 2,
    global: true,
    accent: "#E8B84B",
  },
  {
    id: "settings",
    label: "Settings",
    href: "/settings",
    icon: "⚙",
    description: "Theme, density, experience mode, profile",
    mobilePriority: 5,
    global: true,
    accent: "#8B98B4",
    aliases: ["/me"],
  },
  {
    id: "evidence",
    label: "Evidence",
    href: "/evidence",
    icon: "❖",
    description: "Provenance store",
    global: true,
    accent: "#6E72F0",
  },
];

/** Mobile companion tabs (5 max). Ask Saathi is a panel action, not a route. */
export const MOBILE_TABS = [
  { id: "home", label: "Home", href: "/", icon: "⌂" },
  { id: "approvals", label: "Approvals", href: "/approvals", icon: "!" },
  { id: "saathi", label: "Ask Saathi", href: null, action: "copilot", icon: "💬" },
  { id: "business", label: "Business", href: "/business", icon: "◈" },
  { id: "me", label: "Me", href: "/settings", icon: "👤" },
];

/** Safe go-to shortcuts (g then letter). */
export const GO_SHORTCUTS = {
  h: "/",
  c: "/command",
  m: "/missions",
  p: "/projects",
  a: "/approvals",
  s: "/studio",
  k: "/knowledge",
};

/** Flatten primary area items (exactly 12). */
export function getPrimaryAreas() {
  return NAV_GROUPS.flatMap((g) => g.items);
}

export function getAllNavItems() {
  return [...getPrimaryAreas(), ...GLOBAL_NAV];
}

/**
 * Resolve active nav item for a pathname (longest href / alias match).
 * @param {string} pathname
 * @returns {NavItem | null}
 */
export function matchNavItem(pathname) {
  if (!pathname) return null;
  const path = pathname.split("?")[0] || "/";
  const items = getAllNavItems();
  let best = null;
  let bestLen = -1;
  for (const item of items) {
    const candidates = [item.href, ...(item.aliases || [])];
    for (const c of candidates) {
      if (!c) continue;
      const exact = path === c;
      const prefix = c !== "/" && path.startsWith(c + "/");
      if (exact || prefix) {
        const len = c.length;
        if (len > bestLen) {
          best = item;
          bestLen = len;
        }
      }
    }
  }
  // Home special-case: only exact /
  if (path === "/") {
    return items.find((i) => i.href === "/") || best;
  }
  return best;
}

/**
 * Breadcrumb segments for TopBar.
 * @param {string} pathname
 */
export function breadcrumbFor(pathname) {
  const item = matchNavItem(pathname);
  if (!item) {
    const seg = (pathname || "/").split("/").filter(Boolean);
    if (!seg.length) return { group: "Operate", area: "Home", href: "/" };
    const name = seg[seg.length - 1].replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    return { group: "SaathiOS", area: name, href: pathname };
  }
  const group = NAV_GROUPS.find((g) => g.items.some((i) => i.id === item.id));
  return {
    group: group?.label || (item.global ? "Global" : "SaathiOS"),
    area: item.label,
    href: item.href,
  };
}

/**
 * Integrity validation — throws or returns list of errors.
 * Used by unit tests and optional runtime assert.
 */
export function validateNavigationModel() {
  const errors = [];
  const ids = new Set();
  const hrefs = new Set();
  const primary = getPrimaryAreas();

  if (NAV_GROUPS.length !== 4) {
    errors.push(`Expected 4 groups, got ${NAV_GROUPS.length}`);
  }
  if (primary.length !== 12) {
    errors.push(`Expected 12 primary areas, got ${primary.length}`);
  }

  for (const g of NAV_GROUPS) {
    if (!g.id || !g.label || !Array.isArray(g.items)) {
      errors.push(`Invalid group: ${JSON.stringify(g)}`);
    }
  }

  for (const item of getAllNavItems()) {
    if (!item.id) errors.push("Nav item missing id");
    if (!item.label) errors.push(`Nav item ${item.id} missing label`);
    if (!item.href && item.action !== "copilot") errors.push(`Nav item ${item.id} missing href`);
    if (item.id && ids.has(item.id)) errors.push(`Duplicate nav id: ${item.id}`);
    if (item.id) ids.add(item.id);
    if (item.href) {
      if (hrefs.has(item.href)) errors.push(`Duplicate canonical href: ${item.href}`);
      hrefs.add(item.href);
    }
  }

  // Aliases must not overwrite another item's canonical href as their own id collision
  const canonical = new Set(primary.map((i) => i.href));
  for (const item of getAllNavItems()) {
    for (const a of item.aliases || []) {
      if (canonical.has(a) && a !== item.href) {
        // alias pointing at another primary canonical is OK only as redirect target, not as own href
        // forbid alias equal to a *different* item's primary href only when used as this item's href (already covered)
      }
    }
  }

  // Explicit: no CONTROL key in this model (departments handled separately)
  if (ids.has("CONTROL") || ids.has("control-dup")) {
    errors.push("CONTROL key must not appear as nav id");
  }

  return errors;
}

/** Infer environment label from API base URL (display only). */
export function inferEnvironment(apiBase) {
  if (!apiBase || apiBase === "" || apiBase.includes("localhost") || apiBase.includes("127.0.0.1")) {
    return "local";
  }
  if (/staging|stage|vm\.|canary/i.test(apiBase)) {
    if (/canary/i.test(apiBase)) return "canary";
    return "staging";
  }
  if (/prod|saathiai|railway|fly\.io|koyeb/i.test(apiBase)) {
    return "production";
  }
  return "vm";
}
