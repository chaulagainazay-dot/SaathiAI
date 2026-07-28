/**
 * M63/M64 — Platform Module Registry (frontend static MIRROR).
 *
 * ⚠ NON-AUTHORITATIVE as of M64. The authoritative source for browser module
 * discovery, availability, health, navigation, and dashboard composition is the
 * backend ModuleRegistry via GET /api/v1/platform/modules (see client.js). This
 * static mirror exists ONLY for:
 *   - shell bootstrapping / route skeletons before the authenticated fetch resolves
 *   - safe offline presentation
 *   - drift-detection comparison (drift.js)
 *   - tests
 *
 * It must never be treated as operational truth: it does not grant access, does
 * not mark unavailable modules active, and does not override backend feature flags
 * or capability/permission state. `SOURCE` marks it explicitly as a fallback.
 *
 * This is metadata + composition ONLY. Modules never manipulate shell internals
 * directly and never own evidence, notifications, or RBAC — those stay
 * centralized platform services.
 *
 * @typedef {"trading"|"education"|"retail"|"travel"|"finance"|"platform"} ModuleCategory
 * @typedef {"enabled"|"disabled"|"placeholder"} ModuleStatus
 * @typedef {"healthy"|"degraded"|"unknown"|"not_implemented"} ModuleHealth
 *
 * @typedef {Object} NavItem
 * @property {string} id
 * @property {string} label
 * @property {string} href
 * @property {string} [icon]
 * @property {string} [description]
 *
 * @typedef {Object} Widget
 * @property {string} id
 * @property {string} title
 * @property {string} kind
 * @property {string} [href]
 * @property {string} [description]
 *
 * @typedef {Object} ModuleDescriptor
 * @property {string} id
 * @property {string} name
 * @property {string} version
 * @property {string} description
 * @property {string} icon
 * @property {ModuleCategory} category
 * @property {ModuleStatus} status
 * @property {string[]} permissions
 * @property {string[]} routes
 * @property {NavItem[]} navItems
 * @property {Widget[]} widgets
 * @property {{providerId:string, objectTypes:string[]}|null} searchProvider
 * @property {{id:string,label:string,scope:string,href?:string}[]} workspaceViews
 * @property {string[]} capabilities
 * @property {Object} featureFlags
 * @property {ModuleHealth} health
 */

/** Marks this module data as a non-authoritative fallback skeleton (never backend truth). */
export const SOURCE = "fallback";

/** @param {Partial<ModuleDescriptor>} m @returns {ModuleDescriptor} */
export function defineModule(m) {
  if (!m.id || !m.name || !m.version) {
    throw new Error("module requires id, name, version");
  }
  return {
    id: m.id,
    name: m.name,
    version: m.version,
    description: m.description || "",
    icon: m.icon || "▦",
    category: m.category || "platform",
    status: m.status || "placeholder",
    permissions: m.permissions || [],
    routes: m.routes || [],
    navItems: m.navItems || [],
    widgets: m.widgets || [],
    searchProvider: m.searchProvider || null,
    workspaceViews: m.workspaceViews || [],
    capabilities: m.capabilities || [],
    featureFlags: m.featureFlags || {},
    health: m.health || (m.status === "placeholder" ? "not_implemented" : "unknown"),
  };
}

export class ModuleRegistry {
  constructor() {
    /** @type {Map<string, ModuleDescriptor>} */
    this._modules = new Map();
  }

  register(mod) {
    const m = defineModule(mod);
    if (this._modules.has(m.id)) throw new Error(`module already registered: ${m.id}`);
    this._modules.set(m.id, m);
    return m;
  }

  get(id) {
    return this._modules.get(id) || null;
  }

  listInstalled() {
    return [...this._modules.values()].sort(
      (a, b) => a.category.localeCompare(b.category) || a.name.localeCompare(b.name)
    );
  }

  listEnabled() {
    return this.listInstalled().filter((m) => m.status === "enabled");
  }

  /** Data-driven Applications navigation group (platform groups stay in navigation.js). */
  navigation() {
    return {
      group: "applications",
      label: "Applications",
      modules: this.listInstalled().map((m) => ({
        id: m.id,
        label: m.name,
        icon: m.icon,
        status: m.status,
        category: m.category,
        items: m.navItems,
      })),
    };
  }

  /** One card per installed module for the unified dashboard. */
  dashboardCards() {
    return this.listInstalled().map((m) => ({
      moduleId: m.id,
      title: m.name,
      icon: m.icon,
      category: m.category,
      status: m.status,
      health: m.health,
      description: m.description,
      widgets: m.widgets,
      primaryRoute: m.routes[0] || "",
    }));
  }

  widgets() {
    return this.listInstalled().flatMap((m) =>
      m.widgets.map((w) => ({ moduleId: m.id, ...w }))
    );
  }

  searchProviders() {
    return this.listInstalled()
      .filter((m) => m.searchProvider)
      .map((m) => ({ moduleId: m.id, ...m.searchProvider }));
  }

  workspaceViews() {
    return this.listInstalled().flatMap((m) =>
      m.workspaceViews.map((v) => ({ moduleId: m.id, ...v }))
    );
  }

  permissionNamespaces() {
    return this.listInstalled()
      .filter((m) => m.permissions.length)
      .map((m) => ({ moduleId: m.id, namespaces: m.permissions }));
  }

  healthReport() {
    return this.listInstalled().map((m) => ({
      moduleId: m.id,
      status: m.status,
      health: m.health,
    }));
  }
}

/** Trading — the first fully integrated platform module (reference implementation). */
export const TRADING_MODULE = defineModule({
  id: "trading",
  name: "Trading",
  version: "62.9",
  description:
    "Bounded paper-trading platform: research → strategy → paper orders → reconciliation → safety. Simulation-only, long-only, localhost.",
  icon: "◈",
  category: "trading",
  status: "enabled",
  permissions: ["paper_account", "paper_order", "reconciliation", "paper_safety"],
  routes: [
    "/trading",
    "/trading/accounts",
    "/trading/orders",
    "/trading/positions",
    "/trading/strategies",
    "/trading/reconciliation",
    "/trading/safety",
    "/trading/approvals",
    "/trading/evidence",
  ],
  navItems: [
    { id: "trading-home", label: "Overview", href: "/trading", icon: "◈" },
    { id: "trading-accounts", label: "Accounts", href: "/trading/accounts", icon: "▤" },
    { id: "trading-orders", label: "Orders", href: "/trading/orders", icon: "▦" },
    { id: "trading-safety", label: "Safety", href: "/trading/safety", icon: "⛊" },
    { id: "trading-recon", label: "Reconciliation", href: "/trading/reconciliation", icon: "⚖" },
  ],
  widgets: [
    { id: "trading-active-accounts", title: "Active Accounts", kind: "metric", href: "/trading/accounts" },
    { id: "trading-open-orders", title: "Open Orders", kind: "metric", href: "/trading/orders" },
    { id: "trading-safety-alerts", title: "Safety Alerts", kind: "alert", href: "/trading/safety" },
  ],
  searchProvider: { providerId: "trading", objectTypes: ["order", "account", "strategy", "reconciliation"] },
  workspaceViews: [
    { id: "trading-app", label: "Trading", scope: "application", href: "/trading" },
    { id: "trading-evidence", label: "Trading Evidence", scope: "evidence", href: "/trading/evidence" },
  ],
  capabilities: ["paper_trading", "reconciliation", "circuit_breakers", "deterministic_backtest"],
  featureFlags: { live_trading: false, real_money: false, external_broker: false },
  health: "healthy",
});

function placeholder(id, name, icon, category, description, routes, widgetTitles, searchTypes) {
  return defineModule({
    id,
    name,
    version: "0.0.0",
    description,
    icon,
    category,
    status: "placeholder",
    permissions: [id],
    routes,
    navItems: [{ id: `${id}-home`, label: name, href: routes[0] || `/${id}`, icon }],
    widgets: widgetTitles.map((t) => ({
      id: `${id}-${t.toLowerCase().replace(/\s+/g, "-")}`,
      title: t,
      kind: "metric",
    })),
    searchProvider: { providerId: id, objectTypes: searchTypes },
    workspaceViews: [{ id: `${id}-app`, label: name, scope: "application", href: routes[0] || `/${id}` }],
    featureFlags: { implemented: false },
  });
}

export const PLACEHOLDER_MODULES = [
  placeholder("ielts", "IELTSAlert", "✦", "education", "IELTS exam alerting and preparation.",
    ["/ielts"], ["Upcoming Exams", "Alerts", "Students"], ["test", "student", "alert"]),
  placeholder("hcgpos", "HCG POS", "▣", "retail", "Canteen point-of-sale and kitchen operations.",
    ["/pos"], ["Sales", "Kitchen", "Orders"], ["order", "inventory", "customer"]),
  placeholder("travel", "Travel", "✈", "travel", "Trip, itinerary, and booking management.",
    ["/travel"], ["Trips", "Bookings"], ["booking", "itinerary", "client"]),
  placeholder("finance", "Finance", "$", "finance", "Personal and business finance tracking.",
    ["/finance"], ["Cashflow", "Budgets"], ["account", "transaction", "budget"]),
];

/** Construct the platform's default registry: Trading enabled + placeholders. */
export function buildDefaultRegistry() {
  const r = new ModuleRegistry();
  r.register(TRADING_MODULE);
  for (const p of PLACEHOLDER_MODULES) r.register(p);
  return r;
}

let _default = null;
/** Stable process-wide registry (startup registration). */
export function getRegistry() {
  if (!_default) _default = buildDefaultRegistry();
  return _default;
}
