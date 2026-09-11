"use client";
// Orbit live data — maps the real fleet into constellation nodes.
//
// Honesty rule, matching the rest of the program: the surface must never present
// fallback shape as if it were live truth. Every result carries an explicit
// `source` ("live" | "fallback" | "unauthenticated") and the page renders that
// state. Unknown health becomes `neutral`, never `success`.

import { useCallback, useEffect, useState } from "react";
import { fleetActions, safeToken } from "./fleet.js";

/** Fleet health/trust vocabulary -> the orbit's agent state vocabulary. */
export function workerState(worker) {
  const health = String(worker?.health_state || "").toUpperCase();
  const trust = String(worker?.trust_state || "").toUpperCase();

  // Trust problems outrank health: a quarantined worker is blocked even if "healthy".
  if (["QUARANTINED", "REVOKED"].includes(trust)) return "blocked";
  if (["UNHEALTHY", "OFFLINE"].includes(health)) return "error";
  if (["QUARANTINED"].includes(health)) return "blocked";
  if (["DEGRADED", "DRAINING", "STALE"].includes(health)) return "degraded";
  if (["PENDING_ADMISSION"].includes(trust)) return "pending";
  if (health === "HEALTHY") return "active";
  return "unknown"; // -> neutral tone; never optimistically "active"
}

/** Readable label from a worker id, without inventing a name. */
export function workerLabel(worker) {
  const id = String(worker?.worker_id || "").trim();
  if (!id) return "worker";
  const short = id.split(/[:@/]/)[0].replace(/[-_]+/g, " ");
  return short.length > 22 ? `${short.slice(0, 21)}…` : short;
}

/** Primary capabilities orbit closer to the core. */
const TIER1_CAPS = ["orchestrator", "chief", "research", "trading", "finance", "ops", "content"];

export function workerTier(worker) {
  const caps = (worker?.capability_set || []).map((c) => String(c).toLowerCase());
  const id = String(worker?.worker_id || "").toLowerCase();
  const hit = TIER1_CAPS.some((c) => id.includes(c) || caps.some((x) => x.includes(c)));
  return hit ? 1 : 2;
}

export function mapWorkersToAgents(workers = []) {
  return workers.map((w) => ({
    id: String(w.worker_id || Math.random().toString(36).slice(2)),
    label: workerLabel(w),
    tier: workerTier(w),
    state: workerState(w),
    detail: [
      w.health_state && `health ${w.health_state}`,
      w.trust_state && `trust ${w.trust_state}`,
      typeof w.active_lease_count === "number" && `${w.active_lease_count} active lease(s)`,
    ].filter(Boolean).join(" · ") || "no detail reported",
  }));
}

/**
 * Live fleet -> orbit agents.
 * Never throws into the render path; failure degrades to a labelled fallback.
 */
export function useOrbitAgents(fallback = []) {
  const [state, setState] = useState({
    agents: fallback, source: "fallback", loading: true, error: "",
  });

  const load = useCallback(async (signal) => {
    const token = safeToken();
    if (!token) {
      setState({ agents: fallback, source: "unauthenticated", loading: false, error: "" });
      return;
    }
    try {
      const res = await fleetActions.listWorkers(token, signal);
      const workers = res?.workers || res || [];
      const agents = mapWorkersToAgents(Array.isArray(workers) ? workers : []);
      if (!agents.length) {
        setState({ agents: fallback, source: "fallback", loading: false, error: "fleet reported no workers" });
        return;
      }
      setState({ agents, source: "live", loading: false, error: "" });
    } catch (e) {
      setState({
        agents: fallback, source: "fallback", loading: false,
        error: String(e?.message || e).slice(0, 160),
      });
    }
  }, [fallback]);

  useEffect(() => {
    const ac = new AbortController();
    load(ac.signal);
    return () => ac.abort();
  }, [load]);

  return { ...state, reload: () => load() };
}

export const SOURCE_LABEL = {
  live: "LIVE FLEET",
  fallback: "REFERENCE SHAPE — NOT LIVE FLEET",
  unauthenticated: "SIGN IN FOR LIVE FLEET — SHOWING REFERENCE SHAPE",
};
