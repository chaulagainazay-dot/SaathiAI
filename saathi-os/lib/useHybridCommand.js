"use client";

/**
 * UI-NEXT-3 — Production Hybrid Command data loader.
 * Partial failures isolate per panel. Never injects DEMO financial values.
 */

import { useCallback, useEffect, useState } from "react";
import {
  controlOverview,
  controlAttention,
  platformPendingApprovals,
  fetchMissions,
  fetchEvidence,
  fetchInfraHealth,
} from "@/lib/api";
import { extractList } from "@/lib/approvals";
import { plat, getToken } from "@/lib/platform-client";
import { composeHybridCommandModel } from "@/lib/command-read-model";
import { buildDemoCommandModel } from "@/lib/design-lab/contracts";

function settled(promise) {
  return promise
    .then((value) => ({ ok: true, value }))
    .catch((error) => ({ ok: false, error: String(error?.message || error) }));
}

async function loadPaperCommandSources(token) {
  if (!token) {
    return {
      auth: false,
      accountId: null,
      portfolio: null,
      portfolioError: "session required",
      risk: null,
      riskError: "session required",
      proposal: null,
      proposalError: "session required",
    };
  }
  const g = (path) => plat(path, { token });
  try {
    const ac = await g("/paper/accounts").catch(() => null);
    const accounts = ac?.accounts || [];
    const accountId = accounts[0]?.id || accounts[0]?.account_id || null;
    if (!accountId) {
      return {
        auth: true,
        accountId: null,
        portfolio: null,
        portfolioError: "no paper account",
        risk: null,
        riskError: "no paper account",
        proposal: null,
        proposalError: "no paper account",
      };
    }
    const [snap, risk, props, summary] = await Promise.all([
      settled(g(`/paper/accounts/${accountId}/command-snapshot`)),
      settled(g(`/paper/accounts/${accountId}/risk`)),
      settled(g(`/paper/accounts/${accountId}/proposals`)),
      settled(g(`/paper/accounts/${accountId}/summary`)),
    ]);
    // Prefer command-snapshot; fall back to summary (still live if present)
    const portfolio = snap.ok
      ? snap.value
      : summary.ok
        ? summary.value?.summary || summary.value
        : null;
    return {
      auth: true,
      accountId,
      portfolio,
      portfolioError: portfolio ? null : snap.error || summary.error || "portfolio unavailable",
      risk: risk.ok ? risk.value : null,
      riskError: risk.ok ? null : risk.error,
      proposal: props.ok ? props.value : null,
      proposalError: props.ok ? null : props.error,
    };
  } catch (e) {
    return {
      auth: true,
      accountId: null,
      portfolio: null,
      portfolioError: String(e?.message || e),
      risk: null,
      riskError: String(e?.message || e),
      proposal: null,
      proposalError: String(e?.message || e),
    };
  }
}

/**
 * @param {{
 *   voiceRuntime?: object|null,
 *   voicePrefsEnabled?: boolean|null,
 *   fixtureScenario?: string|null,
 * }} opts
 * fixtureScenario: only for browser cert / design fixtures — never default in production.
 */
export function useHybridCommand({
  voiceRuntime = null,
  voicePrefsEnabled = null,
  fixtureScenario = null,
} = {}) {
  const [state, setState] = useState({ loading: true, model: null, accountId: null });

  const load = useCallback(async () => {
    // Explicit fixture mode for cert screenshots only
    if (fixtureScenario) {
      const demo = buildDemoCommandModel(fixtureScenario);
      // Re-tag as fixture, not production DEMO on /command unless query says so
      const model = {
        ...demo,
        global_provenance: "FIXTURE",
        banner: `FIXTURE · ${fixtureScenario} · not live authority · browser/cert only`,
        proposal: demo.proposal || { provenance: "FIXTURE", portfolio_proposal: null },
        meta: {
          inventsMetrics: false,
          liveTrading: false,
          authorizesExecution: false,
          authorizesApproval: false,
          fixture: true,
        },
        saathi: {
          voice_session_state: demo.voice_session_state || "READY",
          transcript: "",
          reply: "Fixture mode. No live financial data.",
          focus: null,
          authority: "fixture",
        },
      };
      // Map design-lab attention ranks
      if (model.attention?.items) {
        model.attention.items = model.attention.items.map((i) => ({
          ...i,
          rank:
            i.severity === "critical"
              ? "CRITICAL"
              : i.severity === "high"
                ? "ACTION_REQUIRED"
                : i.severity === "medium"
                  ? "WARNING"
                  : "INFO",
          focus: i.ref === "risk" ? "risk" : i.kind?.includes("approval") ? "attention" : "saathi",
        }));
      }
      // Attach a synthetic proposal for proposal-ready / risk-blocked fixtures
      if (fixtureScenario === "risk_warning" || fixtureScenario === "healthy") {
        model.proposal = {
          provenance: "FIXTURE",
          authorizes_execution: false,
          mode: "PAPER",
          portfolio_proposal: {
            id: "pprop_fixture_demo",
            status: fixtureScenario === "risk_warning" ? "READY_FOR_APPROVAL" : "READY_FOR_APPROVAL",
            method: "equal_weight",
            source: "fixture",
            created_at: Date.now() / 1000,
            expires_at: Date.now() / 1000 + 86400,
            current: {
              cash: model.portfolio?.cash,
              nav: model.portfolio?.paper_nav,
              largest_position: model.risk?.largest_position,
              risk_status: model.risk?.risk_status,
            },
            proposed: {
              cash: "124850.00",
              nav: model.portfolio?.paper_nav,
              largest_position: "0.15",
              risk_status: model.risk?.risk_status,
              cash_weight: "0.10",
            },
            delta: {},
            trades: [
              {
                symbol: "AAA",
                action: "BUY",
                current_weight: "0.12",
                target_weight: "0.15",
                weight_delta: "0.03",
                estimated_quantity: "10",
                reference_price: "124.83",
                notional_delta: "1248.00",
                reason_codes: ["TARGET_WEIGHT_RESTORE"],
              },
              {
                symbol: "CCC",
                action: "SELL",
                current_weight: "0.08",
                target_weight: "0.05",
                weight_delta: "-0.03",
                estimated_quantity: "5",
                reference_price: "49.95",
                notional_delta: "-249.75",
                reason_codes: ["RISK_CONCENTRATION_REDUCTION"],
              },
            ],
            target_allocations: [
              { symbol: "AAA", target_weight: "0.15" },
              { symbol: "BBB", target_weight: "0.10" },
              { symbol: "CCC", target_weight: "0.05" },
            ],
            projected_risk: model.risk,
            warnings: fixtureScenario === "risk_warning" ? ["RISK_WARN"] : [],
            reason_codes: ["EQUAL_WEIGHT_BASELINE", "TARGET_WEIGHT_RESTORE"],
            reason_labels: [
              { code: "EQUAL_WEIGHT_BASELINE", label: "Equal-weight baseline allocation" },
              { code: "TARGET_WEIGHT_RESTORE", label: "Restore target allocation" },
            ],
            evidence_refs: {},
            approval_status: null,
            authorizes_execution: false,
            mode: "PAPER",
          },
        };
      }
      if (fixtureScenario === "recon_required") {
        model.proposal = {
          provenance: "FIXTURE",
          portfolio_proposal: {
            id: "pprop_fixture_blocked",
            status: "RISK_BLOCKED",
            method: "fixed_target",
            reason_codes: ["RISK_BLOCKED", "LEDGER_UNRECONCILED"],
            reason_labels: [
              { code: "RISK_BLOCKED", label: "Blocked by risk engine" },
              { code: "LEDGER_UNRECONCILED", label: "Ledger reconciliation required" },
            ],
            trades: [],
            warnings: ["RECONCILIATION_REQUIRED"],
            authorizes_execution: false,
            mode: "PAPER",
            current: {},
            proposed: {},
            projected_risk: model.risk,
          },
        };
      }
      return { model, accountId: null };
    }

    const token = getToken();
    const [ov, ctrl, appr, miss, evid, infra, paper] = await Promise.all([
      settled(controlOverview()),
      settled(controlAttention()),
      settled(platformPendingApprovals()),
      settled(fetchMissions()),
      settled(fetchEvidence({ limit: 20 })),
      settled(fetchInfraHealth()),
      loadPaperCommandSources(token),
    ]);

    const approvalsList = appr.ok ? extractList(appr.value) || [] : [];
    const missionsList = miss.ok ? miss.value?.missions || extractList(miss.value) || [] : [];
    const evidenceList = evid.ok
      ? extractList(evid.value) || evid.value?.evidence || evid.value?.items || []
      : [];

    let agents = [];
    if (ov.ok && Array.isArray(ov.value?.agents)) agents = ov.value.agents;
    else if (ov.ok && Array.isArray(ov.value?.agent_bindings)) agents = ov.value.agent_bindings;

    const voiceState =
      voiceRuntime?.sessionState ||
      voiceRuntime?.state ||
      (voicePrefsEnabled === false ? "CLOSED" : "READY");

    const model = composeHybridCommandModel({
      portfolioSnap: paper.portfolio,
      portfolioError: paper.portfolioError,
      riskSnap: paper.risk,
      riskError: paper.riskError,
      proposalPayload: paper.proposal,
      proposalError: paper.proposalError,
      agents,
      missions: Array.isArray(missionsList) ? missionsList : [],
      approvals: Array.isArray(approvalsList) ? approvalsList : [],
      evidence: Array.isArray(evidenceList) ? evidenceList : [],
      voiceState,
      voiceTranscript: voiceRuntime?.transcript || voiceRuntime?.lastTranscript || "",
      voiceReply: voiceRuntime?.reply || voiceRuntime?.lastResponse || "",
      infra: infra.ok ? infra.value : { ok: false },
      tg: null,
      banner: paper.auth
        ? "PRODUCTION Hybrid Command · PAPER · canonical reads · zero execution authority"
        : "PRODUCTION Hybrid Command · sign in for paper ledger/risk/proposal · zero execution authority",
    });

    // Merge control attention titles if present
    if (ctrl.ok) {
      const raw = Array.isArray(ctrl.value?.items) ? ctrl.value.items : Array.isArray(ctrl.value) ? ctrl.value : [];
      for (const it of raw.slice(0, 8)) {
        model.attention.items.push({
          id: `ctrl-${it.id || model.attention.items.length}`,
          severity: "INFO",
          rank: "INFO",
          kind: "control",
          title: it.title || it.message || it.kind || "Control item",
          urgency: 20,
          ref: it.id,
          focus: "attention",
        });
      }
    }

    return { model, accountId: paper.accountId };
  }, [voiceRuntime, voicePrefsEnabled, fixtureScenario]);

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));
    load().then(({ model, accountId }) => {
      if (cancelled) return;
      setState({ loading: false, model, accountId });
    });
    return () => {
      cancelled = true;
    };
  }, [load]);

  const refresh = useCallback(() => {
    setState((s) => ({ ...s, loading: true }));
    load().then(({ model, accountId }) => {
      setState({ loading: false, model, accountId });
    });
  }, [load]);

  return { ...state, refresh };
}
