/**
 * Trading contract adapter for design-branch prototype.
 *
 * Decision: FIXTURE_ADAPTER (exact schema) — do not merge T-NEXT branches.
 * Optional future: fetch real endpoints when available; never invent numbers.
 */

import { PROVENANCE, buildDemoCommandModel } from "./contracts.js";

/**
 * Load command read model.
 * @param {{ scenario?: string, preferLive?: boolean }} opts
 */
export async function loadCommandReadModel(opts = {}) {
  const scenario = opts.scenario || "healthy";
  if (opts.preferLive) {
    try {
      // Placeholder for future real endpoints — design branch has no fund_ledger API.
      // Returning null forces DEMO with explicit provenance.
      const live = null;
      if (live) {
        return { ...live, global_provenance: PROVENANCE.REAL, banner: "REAL read contracts" };
      }
    } catch {
      /* fall through */
    }
  }
  const model = buildDemoCommandModel(scenario);
  return model;
}

export function tagField(value, provenance, authority) {
  return { value, provenance, authority };
}

/** Format fraction 0.12 → 12.0% for display only (not risk math). */
export function formatFraction(v) {
  if (v == null || v === "—") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  if (Math.abs(n) <= 1 && String(v).includes(".")) return `${(n * 100).toFixed(1)}%`;
  return String(v);
}

export function formatMoney(v) {
  if (v == null) return "—";
  const n = Number(String(v).replace(/,/g, ""));
  if (Number.isNaN(n)) return String(v);
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
