"use client";

import { useEffect, useState, useCallback } from "react";
import {
  controlOverview,
  controlAttention,
  platformPendingApprovals,
  fetchMissions,
  fetchEvidence,
  fetchInfraHealth,
  API_BASE,
} from "@/lib/api";
import { aggregateAttention } from "@/lib/attention";
import { extractList } from "@/lib/approvals";
import { composeCommandCenterViewModel } from "@/lib/command-composition";
import { plat, getToken } from "@/lib/platform-client";

function settled(promise) {
  return promise
    .then((value) => ({ ok: true, value }))
    .catch((error) => ({ ok: false, error: String(error?.message || error) }));
}

async function fetchPaperOverview(token) {
  if (!token) return { auth: false, ready: true, summary: null, error: null };
  const g = (path) => plat(path, { token }).catch(() => null);
  try {
    const [ac, st, tr, al, sw, rc] = await Promise.all([
      g("/paper/accounts"),
      g("/paper/safety/states"),
      g("/paper/safety/trips?limit=50"),
      g("/paper/safety/alerts?limit=50"),
      g("/paper/safety/sweeps?limit=20"),
      g("/paper/reconciliation/runs?limit=50"),
    ]);
    const accounts = ac?.accounts || [];
    const states = st?.states || [];
    const trips = tr?.trips || [];
    const alerts = al?.alerts || [];
    const sweeps = sw?.sweeps || [];
    const recon = rc?.runs || [];
    const sum = (arr, k) => arr.reduce((s, a) => s + (Number(a[k]) || 0), 0);
    const summary = {
      accounts: accounts.length,
      active: accounts.filter((a) => a.status === "ACTIVE").length,
      halted: accounts.filter((a) => a.status === "HALTED").length,
      cash: sum(accounts, "current_cash"),
      equity: sum(accounts, "total_equity"),
      reserved: sum(accounts, "reserved_cash"),
      blockingBreakers: states.filter((s) => s.blocking).length,
      breakerCount: states.length,
      trips: trips.length,
      unackAlerts: alerts.filter((a) => !a.acknowledged).length,
      critDrift: recon.filter((r) => r.severity_max === "CRITICAL").length,
      latestSweep: sweeps[0] || null,
      latestRecon: recon[0] || null,
    };
    return { auth: true, ready: true, summary, error: null };
  } catch (e) {
    return { auth: true, ready: true, summary: null, error: String(e?.message || e) };
  }
}

/**
 * Bounded multi-source load for /command.
 * Partial failures never block the whole surface.
 */
export function useCommandCenter({ voiceRuntime = null, voicePrefsEnabled = null } = {}) {
  const [state, setState] = useState({
    loading: true,
    model: null,
    refreshCount: 0,
  });

  const load = useCallback(async () => {
    const token = getToken();
    const [ov, ctrl, appr, miss, evid, infra, paper] = await Promise.all([
      settled(controlOverview()),
      settled(controlAttention()),
      settled(platformPendingApprovals()),
      settled(fetchMissions()),
      settled(fetchEvidence({ limit: 12 })),
      settled(fetchInfraHealth()),
      fetchPaperOverview(token),
    ]);

    const controlItems = ctrl.ok
      ? Array.isArray(ctrl.value?.items)
        ? ctrl.value.items
        : Array.isArray(ctrl.value)
          ? ctrl.value
          : []
      : [];
    const approvalsList = appr.ok ? extractList(appr.value) : null;
    const missionsList = miss.ok ? miss.value?.missions || extractList(miss.value) || [] : [];
    const evidenceList = evid.ok
      ? extractList(evid.value) || evid.value?.evidence || evid.value?.items || []
      : [];

    // Agents: best-effort from overview or missions bindings — no new endpoint required
    let agents = [];
    if (ov.ok && Array.isArray(ov.value?.agents)) agents = ov.value.agents;
    else if (ov.ok && Array.isArray(ov.value?.agent_bindings)) agents = ov.value.agent_bindings;

    const attention = aggregateAttention({
      controlItems,
      controlStatus: ctrl.ok ? "connected" : "unavailable",
      controlError: ctrl.ok ? null : ctrl.error,
      missions: Array.isArray(missionsList) ? missionsList : [],
      missionsStatus: miss.ok ? "connected" : "unavailable",
      missionsError: miss.ok ? null : miss.error,
      approvals: Array.isArray(approvalsList) ? approvalsList : [],
      approvalsStatus: appr.ok && Array.isArray(approvalsList) ? "connected" : "unavailable",
      approvalsError: appr.ok ? (Array.isArray(approvalsList) ? null : "unexpected payload") : appr.error,
      infra: infra.ok ? infra.value : null,
      infraStatus: infra.ok ? "connected" : "unavailable",
      infraError: infra.ok ? null : infra.error,
      evidence: Array.isArray(evidenceList) ? evidenceList : [],
      evidenceStatus: evid.ok ? "connected" : "unavailable",
      evidenceError: evid.ok ? null : evid.error,
      generatedAt: ctrl.ok ? ctrl.value?.generated_at || null : null,
    });

    const model = composeCommandCenterViewModel({
      overview: ov.ok ? ov.value : null,
      overviewError: ov.ok ? null : ov.error,
      attention,
      missions: Array.isArray(missionsList) ? missionsList : [],
      missionsStatus: miss.ok ? "connected" : "unavailable",
      agents,
      agentsStatus: agents.length ? "connected" : ov.ok ? "empty" : "unavailable",
      evidence: Array.isArray(evidenceList) ? evidenceList : [],
      evidenceStatus: evid.ok ? "connected" : "unavailable",
      infra: infra.ok ? infra.value : null,
      infraStatus: infra.ok ? "connected" : "unavailable",
      tradingSummary: paper.summary,
      tradingReady: paper.ready,
      tradingAuth: paper.auth,
      tradingError: paper.error,
      voiceRuntime,
      voicePrefsEnabled,
      apiBase: API_BASE,
      controlEvents: controlItems,
    });

    return model;
  }, [voiceRuntime, voicePrefsEnabled]);

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));
    load().then((model) => {
      if (cancelled) return;
      setState((s) => ({ loading: false, model, refreshCount: s.refreshCount + 1 }));
    });
    return () => {
      cancelled = true;
    };
  }, [load]);

  const refresh = useCallback(() => {
    setState((s) => ({ ...s, loading: true }));
    load().then((model) => {
      setState((s) => ({ loading: false, model, refreshCount: s.refreshCount + 1 }));
    });
  }, [load]);

  return { ...state, refresh };
}
