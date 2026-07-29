"use client";
// M62.8 — Trading Operator Workspace data layer.
//
// One authenticated path (`plat` → /api/v1/platform/paper/*, X-Platform-Token) to
// the canonical M62.5–M62.7 backend. The SERVER is authoritative: this layer only
// reads and formats server-provided decimal strings and routes bounded mutations
// (sweep / acknowledge / reset-request / reset / reconcile) back through the same
// authenticated APIs — which themselves route through PlatformAgentRuntime →
// ExecutionGateway. Nothing here writes SQLite, recomputes financial truth, or
// fabricates success.
import { useCallback, useEffect, useMemo, useState } from "react";
import { plat, getToken } from "./platform-client";

export const SAFETY_BANNER = [
  "PAPER TRADING ONLY",
  "NO LIVE ORDERS",
  "SIMULATED FUNDS",
  "NO LIVE BROKER",
  "LONG-ONLY",
  "LOCALHOST",
];

// ── formatting (display only — never accounting authority) ──────────────────────
export function fmtMoney(v, currency = "USD") {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 2 }).format(n);
}
export function fmtNum(v, dp = 2) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: dp }).format(n);
}
export function fmtPct(v, dp = 2) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return `${n.toFixed(dp)}%`;
}
export function fmtTs(ts) {
  if (!ts) return "—";
  try {
    return new Date(Number(ts) * 1000).toLocaleString();
  } catch {
    return String(ts);
  }
}
export function shortHash(h, n = 10) {
  if (!h) return "—";
  return String(h).length > n ? `${String(h).slice(0, n)}…` : String(h);
}

// ── permission helpers (backend remains authoritative; UI hides for clarity) ─────
export function hasPerm(perms, p) {
  return Array.isArray(perms) && perms.includes(p);
}
export const PERM = {
  SWEEP: "paper_safety.sweep",
  TRIP: "paper_safety.trip",
  ACK: "paper_safety.acknowledge",
  RESET_REQUEST: "paper_safety.reset_request",
  RESET: "paper_safety.reset",
  CONFIGURE: "paper_safety.configure",
  READ: "paper_safety.read",
  RECON_RUN: "reconciliation.run",
  APPROVAL_READ: "approval.read",
  APPROVAL_DECIDE: "approval.decide",
};

const STATE_TONE = {
  NORMAL: "ok", WARNING: "warn", TRIPPED: "danger", HALTED: "danger",
  ACKNOWLEDGED: "warn", RESET_PENDING: "warn", RESET: "ok",
};
export const stateTone = (s) => STATE_TONE[s] || "idle";

// ── reads ────────────────────────────────────────────────────────────────────────
const isTransient = (e) =>
  /Failed to fetch|NetworkError|load failed|ECONNREFUSED|503|cold/i.test(String(e?.message || e)) ||
  e?.status === 503 || e?.status === 502;

// Bounded retry on transient/cold-start failures so a concurrent fan-out can't wipe
// a panel to empty. Hard errors (401/403/404) surface immediately.
async function g(path, token, attempts = 6) {
  let last;
  for (let i = 0; i < attempts; i += 1) {
    try {
      return await plat(path, { token });
    } catch (e) {
      last = e;
      if (!isTransient(e) || i === attempts - 1) throw e;
      await new Promise((r) => setTimeout(r, Math.min(1800, 350 * (i + 1))));
    }
  }
  throw last;
}

// Lightweight auth + permissions for sub-pages (server remains authoritative).
export function useAuthMe() {
  const [token, setTok] = useState("");
  const [me, setMe] = useState(null);
  const [ready, setReady] = useState(false);
  useEffect(() => { setTok(getToken()); }, []);
  useEffect(() => {
    let live = true;
    if (!token) { setReady(true); return; }
    g("/me", token).then((m) => { if (live) { setMe(m); setReady(true); } })
      .catch(() => { if (live) setReady(true); });
    return () => { live = false; };
  }, [token]);
  return { token, me, perms: me?.permissions || [], role: me?.context?.role || "", ready };
}

// Generic single-resource loader with loading/error/refresh for detail routes.
export function useResource(fn, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const reload = useCallback(async () => {
    setLoading(true); setError(null);
    try { setData(await fn()); }
    catch (e) { setError(String(e?.message || e)); setData(null); }
    finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { data, loading, error, reload };
}

// Overview aggregate — one bounded fan-out over the authenticated read surface.
export function useTradingOverview() {
  const [token, setTok] = useState("");
  const [me, setMe] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [states, setStates] = useState([]);
  const [trips, setTrips] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [sweeps, setSweeps] = useState([]);
  const [recon, setRecon] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => { setTok(getToken()); }, []);

  const refresh = useCallback(async (tok) => {
    const t = tok ?? getToken();
    if (!t) { setReady(true); return; }
    setLoading(true); setError(null);
    try {
      const meR = await g("/me", t).catch(() => null);
      setMe(meR || null);
      const [ac, st, tr, al, sw, rc, ap] = await Promise.all([
        g("/paper/accounts", t).catch(() => null),
        g("/paper/safety/states", t).catch(() => null),
        g("/paper/safety/trips?limit=100", t).catch(() => null),
        g("/paper/safety/alerts?limit=100", t).catch(() => null),
        g("/paper/safety/sweeps?limit=50", t).catch(() => null),
        g("/paper/reconciliation/runs?limit=100", t).catch(() => null),
        g("/approvals?status=", t).catch(() => null),
      ]);
      setAccounts(ac?.accounts || []);
      setStates(st?.states || []);
      setTrips(tr?.trips || []);
      setAlerts(al?.alerts || []);
      setSweeps(sw?.sweeps || []);
      setRecon(rc?.runs || []);
      setApprovals(ap?.approvals || []);
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false); setReady(true);
    }
  }, []);

  useEffect(() => { if (token) refresh(token); else setReady(true); }, [token, refresh]);

  const perms = me?.permissions || [];
  const summary = useMemo(() => buildSummary({ accounts, states, trips, alerts, sweeps, recon, approvals }),
    [accounts, states, trips, alerts, sweeps, recon, approvals]);

  return { token, me, perms, role: me?.context?.role || me?.session?.role || "",
    accounts, states, trips, alerts, sweeps, recon, approvals, summary,
    loading, error, ready, refresh };
}

function buildSummary({ accounts, states, trips, alerts, sweeps, recon }) {
  const active = accounts.filter((a) => a.status === "ACTIVE").length;
  const halted = accounts.filter((a) => a.status === "HALTED").length;
  const sum = (arr, k) => arr.reduce((s, a) => s + (Number(a[k]) || 0), 0);
  const blocking = states.filter((s) => s.blocking).length;
  const unackAlerts = alerts.filter((a) => !a.acknowledged).length;
  const critDrift = recon.filter((r) => r.severity_max === "CRITICAL").length;
  const latestSweep = sweeps[0] || null;
  return {
    accounts: accounts.length, active, halted,
    cash: sum(accounts, "current_cash"), equity: sum(accounts, "total_equity"),
    reserved: sum(accounts, "reserved_cash"),
    blockingBreakers: blocking, breakerCount: states.length, trips: trips.length,
    unackAlerts, critDrift, latestSweep, latestRecon: recon[0] || null,
  };
}

// ── bounded mutations (all through authenticated APIs / gateway) ─────────────────
export const actions = {
  runSweep: (token) => plat("/paper/safety/sweeps", { method: "POST", token, body: {} }),
  reconcile: (token, account_id) => plat("/paper/reconciliation/runs", { method: "POST", token, body: { account_id } }),
  acknowledge: (token, trip_id, note, evidence_reviewed) =>
    plat(`/paper/safety/trips/${trip_id}/acknowledge`, { method: "POST", token, body: { note, evidence_reviewed } }),
  requestReset: (token, trip_id, reason, approval_id, idempotency_key) =>
    plat(`/paper/safety/trips/${trip_id}/reset-requests`, { method: "POST", token, body: { reason, approval_id, idempotency_key } }),
  executeReset: (token, request_id, approval_id) =>
    plat(`/paper/safety/reset-requests/${request_id}/execute`, { method: "POST", token, body: { approval_id } }),
  manualTrip: (token, scope, scope_ref, reason) =>
    plat("/paper/safety/trips/manual", { method: "POST", token, body: { scope, scope_ref, reason } }),
};

// single-resource fetchers used by detail routes
export const fetchers = {
  accounts: (t) => g("/paper/accounts", t),
  account: (t, id) => g(`/paper/accounts/${id}`, t),
  intents: (t, id) => g(`/paper/order-intents${id ? `?account_id=${id}` : ""}`, t),
  intent: (t, id) => g(`/paper/order-intents/${id}`, t),
  positions: (t, id) => g(`/paper/accounts/${id}/positions`, t),
  ledger: (t, id) => g(`/paper/accounts/${id}/ledger`, t),
  orders: (t, id) => g(`/paper/orders${id ? `?account_id=${id}` : ""}`, t),
  order: (t, id) => g(`/paper/orders/${id}`, t),
  fills: (t, id) => g(`/paper/orders/${id}/fills`, t),
  breakers: (t) => g("/paper/safety/breakers", t),
  states: (t) => g("/paper/safety/states", t),
  trips: (t) => g("/paper/safety/trips?limit=200", t),
  trip: (t, id) => g(`/paper/safety/trips/${id}`, t),
  alerts: (t) => g("/paper/safety/alerts?limit=200", t),
  sweeps: (t) => g("/paper/safety/sweeps?limit=100", t),
  sweep: (t, id) => g(`/paper/safety/sweeps/${id}`, t),
  reconRuns: (t, id) => g(`/paper/reconciliation/runs${id ? `?account_id=${id}` : ""}`, t),
  reconRun: (t, id) => g(`/paper/reconciliation/runs/${id}`, t),
  repairPlans: (t, id) => g(`/paper/reconciliation/repair-plans${id ? `?account_id=${id}` : ""}`, t),
};
