/**
 * M47.4 — Route parity classification (static evidence + browser-informed).
 * Does NOT implement redirects. Classifications are evidence-backed claims for docs/tests.
 */

/** @typedef {'READY_TO_REDIRECT'|'KEEP_COMPATIBILITY'|'BLOCKED_MISSING_UI'|'BLOCKED_BACKEND'|'BLOCKED_DEEP_LINK'|'BLOCKED_WORKFLOW'} ParityClass */

/**
 * Static parity matrix. parityPct is an engineering estimate from capability coverage,
 * not fabricated browser % — browser cert must re-confirm HTTP load.
 */
export const LEGACY_PARITY = [
  {
    legacy: "/ceo",
    canonical: "/",
    parityPct: 55,
    deepLinkRisk: "medium",
    backendDependency: "executive briefing optional",
    classification: "KEEP_COMPATIBILITY",
    notes: "Legacy CEO surface still distinct; Home is attention-first, not CEO twin of /ceo.",
  },
  {
    legacy: "/os",
    canonical: "/",
    parityPct: 50,
    deepLinkRisk: "medium",
    backendDependency: "ceo/os APIs",
    classification: "KEEP_COMPATIBILITY",
    notes: "OS page has different payload; not equivalent to attention Home.",
  },
  {
    legacy: "/control",
    canonical: "/monitoring + /command",
    parityPct: 65,
    deepLinkRisk: "high",
    backendDependency: "control overview/search/actions",
    classification: "BLOCKED_WORKFLOW",
    notes: "Control has search + multi-facet ops; Monitoring is observe-only; Command is partial compose.",
  },
  {
    legacy: "/chat",
    canonical: "Ask Saathi panel",
    parityPct: 35,
    deepLinkRisk: "high",
    backendDependency: "chat runtime / sessions",
    classification: "BLOCKED_MISSING_UI",
    notes: "Panel is scaffold without ambient history; full chat remains on /chat.",
  },
  {
    legacy: "/workspace",
    canonical: "Ask Saathi panel",
    parityPct: 35,
    deepLinkRisk: "high",
    backendDependency: "workspace chat",
    classification: "BLOCKED_MISSING_UI",
    notes: "Workspace features not in panel scaffold.",
  },
  {
    legacy: "/voice",
    canonical: "/command or Copilot",
    parityPct: 25,
    deepLinkRisk: "high",
    backendDependency: "voice enroll / LOCAL_BASE STT",
    classification: "BLOCKED_WORKFLOW",
    notes: "Voice enrollment and local mic paths not in shell panel.",
  },
  {
    legacy: "/me",
    canonical: "/settings",
    parityPct: 92,
    deepLinkRisk: "low",
    backendDependency: "profile optional",
    classification: "READY_TO_REDIRECT",
    notes: "M47.5: Settings embeds MobileMe profile; soft redirect implemented.",
  },
  {
    legacy: "/finance",
    canonical: "/business",
    parityPct: 45,
    deepLinkRisk: "medium",
    backendDependency: "finance endpoints",
    classification: "BLOCKED_MISSING_UI",
    notes: "Business is compose/links; Finance dashboard not fully absorbed.",
  },
  {
    legacy: "/infrastructure",
    canonical: "/monitoring",
    parityPct: 95,
    deepLinkRisk: "medium",
    backendDependency: "infra health",
    classification: "READY_TO_REDIRECT",
    notes: "M47.5: InfraHealthWorkspace absorbed into Monitoring; soft redirect implemented.",
  },
  {
    legacy: "/studio-os",
    canonical: "/studio",
    parityPct: 75,
    deepLinkRisk: "medium",
    backendDependency: "studio APIs",
    classification: "KEEP_COMPATIBILITY",
    notes: "Studio canonical exists; studio-os may still differ in layout.",
  },
];

export const CANONICAL_ROUTES = [
  "/",
  "/command",
  "/missions",
  "/projects",
  "/approvals",
  "/monitoring",
  "/business",
  "/agents",
  "/trading",
  "/settings",
];

export function validateParityMatrix() {
  const errors = [];
  const seen = new Set();
  for (const row of LEGACY_PARITY) {
    if (seen.has(row.legacy)) errors.push(`duplicate legacy ${row.legacy}`);
    seen.add(row.legacy);
    if (row.parityPct < 0 || row.parityPct > 100) errors.push(`bad pct ${row.legacy}`);
    if (row.classification === "READY_TO_REDIRECT" && row.parityPct < 90) {
      errors.push(`${row.legacy} marked READY_TO_REDIRECT with low parity`);
    }
    // This milestone must not claim ready redirects without evidence
    // M47.5: READY_TO_REDIRECT allowed only for implemented soft redirects
    if (row.classification === "READY_TO_REDIRECT" && row.parityPct < 90) {
      errors.push(`${row.legacy}: READY_TO_REDIRECT requires parityPct >= 90`);
    }
  }
  return errors;
}

export function redirectReadinessSummary() {
  const counts = {};
  for (const row of LEGACY_PARITY) {
    counts[row.classification] = (counts[row.classification] || 0) + 1;
  }
  const ready = LEGACY_PARITY.filter((r) => r.classification === "READY_TO_REDIRECT");
  return {
    total: LEGACY_PARITY.length,
    counts,
    readyToRedirect: ready.length,
    readyRoutes: ready.map((r) => r.legacy),
    policy: "M47.5 soft redirects only for READY_TO_REDIRECT rows",
  };
}
