/**
 * M64 — registry drift detector.
 *
 * Compares the authoritative backend discovery against the local static mirror
 * (registry.js). The backend is always authoritative; the mirror is a bootstrap /
 * offline skeleton only. Drift is a DIAGNOSTIC, not a security control — backend
 * routes and RBAC remain authoritative regardless of drift. But capability,
 * permission, and enablement mismatches are treated as CRITICAL so tests fail and
 * dev surfaces a clear warning; version/route mismatches are informational.
 */

/** Fields whose divergence is security/authority-relevant → fail closed in tests. */
const CRITICAL_FIELDS = new Set(["enabled", "implemented", "permissions", "capabilities"]);

function sortedJoin(arr) {
  return Array.isArray(arr) ? [...arr].map(String).sort().join(",") : String(arr);
}

/**
 * @param {Array} backendModules  normalized backend modules (from client.js)
 * @param {Array} localModules    local mirror descriptors (from registry.js)
 * @returns {{drift: Array, hasCritical: boolean}}
 */
export function detectDrift(backendModules, localModules) {
  const drift = [];
  const backend = new Map(backendModules.map((m) => [m.id, m]));
  const local = new Map(localModules.map((m) => [m.id, m]));

  for (const id of backend.keys()) {
    if (!local.has(id)) drift.push({ moduleId: id, field: "presence", backend: "present", local: "absent", severity: "info" });
  }
  for (const id of local.keys()) {
    if (!backend.has(id)) drift.push({ moduleId: id, field: "presence", backend: "absent", local: "present", severity: "info" });
  }

  for (const [id, b] of backend) {
    const l = local.get(id);
    if (!l) continue;
    const checks = [
      ["version", b.version, l.version, "info"],
      ["enabled", b.enabled, l.status === "enabled", CRITICAL_FIELDS.has("enabled") ? "critical" : "info"],
      ["implemented", b.implemented, l.status !== "placeholder", "critical"],
      ["permissions", sortedJoin(b.permissions), sortedJoin(l.permissions), "critical"],
      ["capabilities", sortedJoin(b.capabilities), sortedJoin(l.capabilities), "critical"],
      ["routes", sortedJoin(b.routes), sortedJoin(l.routes), "info"],
    ];
    for (const [field, bv, lv, severity] of checks) {
      if (String(bv) !== String(lv)) {
        drift.push({ moduleId: id, field, backend: bv, local: lv, severity });
      }
    }
  }

  return { drift, hasCritical: drift.some((d) => d.severity === "critical") };
}

/** Human-readable one-line diagnostics (safe: ids + fields only, no secrets). */
export function driftSummary(result) {
  if (!result.drift.length) return "no drift";
  return result.drift
    .map((d) => `${d.severity.toUpperCase()} ${d.moduleId}.${d.field}: backend=${d.backend} local=${d.local}`)
    .join("; ");
}
