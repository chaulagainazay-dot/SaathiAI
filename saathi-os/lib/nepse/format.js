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

// NEPSE trades Sun–Thu, roughly 11:00–15:00 Nepal time. `now` injectable for tests.
export function isMarketOpen(now = new Date()) {
  const day = now.getDay(); // 0 Sun .. 6 Sat
  if (day === 5 || day === 6) return false; // Fri, Sat closed
  const mins = now.getHours() * 60 + now.getMinutes();
  return mins >= 11 * 60 && mins <= 15 * 60;
}
