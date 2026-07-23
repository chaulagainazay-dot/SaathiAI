"use client";
import { useEffect, useState } from "react";
import {
  controlAttention,
  platformPendingApprovals,
  fetchMissions,
  fetchProjects,
  fetchEvidence,
  fetchInfraHealth,
} from "@/lib/api";
import { aggregateAttention } from "@/lib/attention";
import { extractList } from "@/lib/approvals";

function settled(promise) {
  return promise
    .then((value) => ({ ok: true, value }))
    .catch((error) => ({ ok: false, error: String(error) }));
}

/**
 * Multi-source attention aggregation for Home.
 * One failed source never blocks the page.
 */
export function useAttentionHome() {
  const [state, setState] = useState({
    loading: true,
    attention: null,
    projects: [],
    projectsStatus: "loading",
    missionsContinue: [],
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [ctrl, appr, miss, proj, evid, infra] = await Promise.all([
        settled(controlAttention()),
        settled(platformPendingApprovals()),
        settled(fetchMissions()),
        settled(fetchProjects()),
        settled(fetchEvidence({ limit: 8 })),
        settled(fetchInfraHealth()),
      ]);
      if (cancelled) return;

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

      const projects = proj.ok ? proj.value?.projects || extractList(proj.value) || [] : [];
      const missionsContinue = Array.isArray(missionsList)
        ? missionsList.filter((m) => String(m.status).toLowerCase() === "active").slice(0, 6)
        : [];

      setState({
        loading: false,
        attention,
        projects: Array.isArray(projects) ? projects.slice(0, 6) : [],
        projectsStatus: proj.ok ? "connected" : "unavailable",
        missionsContinue,
      });
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
