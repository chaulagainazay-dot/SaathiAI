import { marketWindow } from "./feed-policy.js";

// NEPSE — display formatters and calendar helpers. Pure, no side effects.
// Money is Nepali Rupee (Rs). These are DISPLAY ONLY — never accounting authority.

export function fmtRs(v, dp = 2) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return `Rs ${new Intl.NumberFormat("en-IN", { maximumFractionDigits: dp, minimumFractionDigits: dp }).format(n)}`;
}

export function fmtNum(v, dp = 2) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: dp }).format(n);
}

export function fmtPct(v, dp = 2) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  const s = n > 0 ? "+" : "";
  return `${s}${n.toFixed(dp)}%`;
}

// Compact "Ar" (Arba = 100 crore = 1e9) / crore style used on the exchange.
export function fmtCompactRs(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  if (Math.abs(n) >= 1e9) return `Rs ${(n / 1e9).toFixed(2)} Ar`;
  if (Math.abs(n) >= 1e7) return `Rs ${(n / 1e7).toFixed(2)} Cr`;
  if (Math.abs(n) >= 1e5) return `Rs ${(n / 1e5).toFixed(2)} L`;
  return fmtRs(n, 0);
}

export function dayChangePct(ltp, prevClose) {
  const a = Number(ltp);
  const b = Number(prevClose);
  if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return 0;
  return ((a - b) / b) * 100;
}

export function dir(delta) {
  const n = Number(delta);
  if (!Number.isFinite(n) || n === 0) return "flat";
  return n > 0 ? "up" : "down";
}

/**
 * Is NEPSE trading right now? `now` injectable for tests.
 *
 * Delegates to `marketWindow`, which does the arithmetic against Asia/Kathmandu
 * explicitly. This function used to read `getDay()` and `getHours()` — the HOST's
 * timezone — which is right only on a machine already set to NPT and silently
 * wrong everywhere else. It reported the exchange open through a Kathmandu night
 * for anything running in UTC, and shut through a Kathmandu morning for anything
 * west of it. The developer machine happens to be set to +05:45, so the bug could
 * not be observed locally: it would have appeared only once deployed.
 */
export function isMarketOpen(now = new Date()) {
  return marketWindow(now).open;
}
