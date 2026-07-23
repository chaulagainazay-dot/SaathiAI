/**
 * M47.5 — Safe soft redirects only.
 * permanent: false (temporary) so bookmarks can be reversed without hard 308 cache pain.
 * Query strings are preserved by Next.js redirects by default.
 *
 * Rules:
 * - Only READY_TO_REDIRECT rows from the parity matrix may appear here.
 * - Never redirect /project/create/*, chat, control, voice, trading.
 * - No loops: destinations must not redirect back to sources.
 */

/** @type {{ source: string, destination: string, permanent: boolean, reason: string }[]} */
export const SAFE_REDIRECTS = [
  {
    source: "/infrastructure",
    destination: "/monitoring",
    permanent: false,
    reason: "Infra health workspace absorbed into Monitoring (M47.5)",
  },
  {
    source: "/me",
    destination: "/settings",
    permanent: false,
    reason: "Profile companion absorbed into Settings (M47.5)",
  },
];

/** Paths that must never appear as redirect sources in this program. */
export const NEVER_REDIRECT_SOURCES = [
  "/project/create",
  "/chat",
  "/workspace",
  "/saathi",
  "/voice",
  "/control",
  "/ceo",
  "/os",
  "/finance",
  "/studio-os",
  "/mission",
  "/trading",
];

export function validateRedirectTable() {
  const errors = [];
  const sources = new Set();
  const dests = new Set(SAFE_REDIRECTS.map((r) => r.destination));

  for (const r of SAFE_REDIRECTS) {
    if (!r.source?.startsWith("/")) errors.push(`bad source ${r.source}`);
    if (!r.destination?.startsWith("/")) errors.push(`bad dest ${r.destination}`);
    if (r.permanent === true) {
      // Soft redirects preferred in M47.5; permanent allowed only with explicit reason flag
      if (!r.allowPermanent) errors.push(`${r.source}: permanent redirect not allowed without allowPermanent`);
    }
    if (sources.has(r.source)) errors.push(`duplicate source ${r.source}`);
    sources.add(r.source);
    if (r.source === r.destination) errors.push(`loop self ${r.source}`);
    // destination must not be a source (simple loop)
    if (SAFE_REDIRECTS.some((x) => x.source === r.destination)) {
      errors.push(`loop chain ${r.source} → ${r.destination}`);
    }
    for (const never of NEVER_REDIRECT_SOURCES) {
      if (r.source === never || r.source.startsWith(never + "/")) {
        errors.push(`forbidden source ${r.source}`);
      }
    }
  }

  // destinations of redirects should not include never-list as sources only
  void dests;
  return errors;
}

/** Shape for next.config.mjs */
export function toNextRedirects() {
  return SAFE_REDIRECTS.map(({ source, destination, permanent }) => ({
    source,
    destination,
    permanent: Boolean(permanent),
  }));
}
