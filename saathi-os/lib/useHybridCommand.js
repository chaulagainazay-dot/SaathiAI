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
    const [snap, risk, props, summary, perf] = await Promise.all([
      settled(g(`/paper/accounts/${accountId}/command-snapshot`)),
      settled(g(`/paper/accounts/${accountId}/risk`)),
      settled(g(`/paper/accounts/${accountId}/proposals`)),
      settled(g(`/paper/accounts/${accountId}/summary`)),
      settled(g(`/paper/accounts/${accountId}/performance`)),
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
      performance: perf.ok ? perf.value : null,
      performanceError: perf.ok ? null : perf.error,
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
      if (
        fixtureScenario === "risk_warning" ||
        fixtureScenario === "healthy" ||
        fixtureScenario === "risk_breached" ||
        fixtureScenario === "proposal_ready" ||
        fixtureScenario === "performance" ||
        fixtureScenario === "agent_active"
      ) {
        const propStatus =
          fixtureScenario === "risk_breached"
            ? "RISK_BLOCKED"
            : fixtureScenario === "risk_warning"
              ? "READY_FOR_APPROVAL"
              : "READY_FOR_APPROVAL";
        model.proposal = {
          provenance: "FIXTURE",
          authorizes_execution: false,
          mode: "PAPER",
          portfolio_proposal: {
            id: "pprop_fixture_demo",
            status: propStatus,
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
            warnings: fixtureScenario === "risk_warning" || fixtureScenario === "risk_breached" ? ["RISK_WARN"] : [],
            reason_codes: ["EQUAL_WEIGHT_BASELINE", "TARGET_WEIGHT_RESTORE"],
            reason_labels: [
              { code: "EQUAL_WEIGHT_BASELINE", label: "Equal-weight baseline allocation" },
              { code: "TARGET_WEIGHT_RESTORE", label: "Restore target allocation" },
            ],
            evidence_refs: { proposal_id: "pprop_fixture_demo" },
            approval_status: null,
            authorizes_execution: false,
            mode: "PAPER",
          },
        };
      }
      if (fixtureScenario === "recon_required" || fixtureScenario === "proposal_blocked") {
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
      if (fixtureScenario === "risk_breached") {
        if (model.risk) {
          model.risk = {
            ...model.risk,
            risk_status: "BREACHED",
            result: "BLOCK",
            reason_codes: ["HARD_LIMIT_DRAWDOWN", "LARGEST_POSITION_BREACH"],
            active_breaches: [{ code: "HARD_LIMIT_DRAWDOWN", severity: "critical" }],
          };
        }
        if (model.system?.risk) {
          model.system.risk = { value: "BREACHED", status: "BREACHED" };
        }
      }
      // Performance read-contract fixture (T-NEXT-4 shapes; no frontend math)
      if (
        fixtureScenario === "healthy" ||
        fixtureScenario === "performance" ||
        fixtureScenario === "risk_warning"
      ) {
        model.performance = {
          provenance: "FIXTURE",
          paper_performance: {
            source: "portfolio_performance_engine",
            provenance: "DERIVED",
            mode: "PAPER",
            live_execution: "UNAVAILABLE",
            nav: model.portfolio?.paper_nav || "1248500.00",
            total_return: "0.024",
            max_drawdown: "0.031",
            realized_pnl: model.portfolio?.realized_pnl || "1200.00",
            unrealized_pnl: model.portfolio?.unrealized_pnl || "850.00",
            nav_history: [
              { t: "2026-08-01", nav: "1220000.00" },
              { t: "2026-08-04", nav: "1234000.00" },
              { t: "2026-08-07", nav: model.portfolio?.paper_nav || "1248500.00" },
            ],
            position_contribution: [
              { symbol: "AAA", contribution: "0.012", pnl: "420.00" },
              { symbol: "BBB", contribution: "0.008", pnl: "210.00" },
              { symbol: "CCC", contribution: "0.004", pnl: "95.00" },
            ],
          },
        };
      }
      // Agent / mission states for motion cert
      if (fixtureScenario === "healthy" || fixtureScenario === "agent_active") {
        model.agents = {
          provenance: "FIXTURE",
          authority: "fixture",
          nodes: [
            {
              id: "agent_research",
              name: "Research",
              role: "analyst",
              status: "ACTIVE",
              task: "scan",
              mission: "mission_alpha",
              dependencies: [],
              evidence: ["ev_risk_1"],
            },
            {
              id: "agent_risk",
              name: "Risk",
              role: "guardian",
              status: "WAITING",
              task: "await",
              mission: "mission_alpha",
              dependencies: ["agent_research"],
              evidence: [],
            },
            {
              id: "agent_exec",
              name: "Construction",
              role: "builder",
              status: "APPROVAL_REQUIRED",
              task: "proposal",
              mission: "mission_alpha",
              dependencies: ["agent_risk"],
              evidence: ["pprop_fixture_demo"],
            },
          ],
        };
        model.missions = {
          provenance: "FIXTURE",
          items: [
            {
              id: "mission_alpha",
              name: "Paper rebalance",
              status: "ACTIVE",
              stage: "RISK_REVIEW",
            },
          ],
        };
      }
      // Linked evidence for focus highlighting (real related_ids only)
      if (
        fixtureScenario === "healthy" ||
        fixtureScenario === "risk_warning" ||
        fixtureScenario === "risk_breached" ||
        fixtureScenario === "agent_active"
      ) {
        model.evidence = {
          provenance: "FIXTURE",
          events: [
            {
              id: "ev_risk_1",
              type: "risk_breach",
              status: "OPEN",
              timestamp: "2026-08-07T10:00:00Z",
              actor: "PortfolioRiskEngine",
              reason: "soft warning near limit",
              related_ids: ["pprop_fixture_demo", "AAA"],
            },
            {
              id: "ev_prop_1",
              type: "proposal",
              status: "READY",
              timestamp: "2026-08-07T10:05:00Z",
              actor: "PortfolioConstruction",
              reason: "equal weight restore",
              related_ids: ["pprop_fixture_demo"],
              proposal_id: "pprop_fixture_demo",
            },
            {
              id: "ev_agent_1",
              type: "agent",
              status: "ACTIVE",
              timestamp: "2026-08-07T10:06:00Z",
              actor: "agent_research",
              agent_id: "agent_research",
              mission_id: "mission_alpha",
              related_ids: ["mission_alpha"],
            },
          ],
          causal_chain: [
            { type: "signal", status: "ok", provenance: "FIXTURE" },
            { type: "risk", status: "warn", provenance: "FIXTURE" },
            { type: "proposal", status: "ready", provenance: "FIXTURE" },
          ],
        };
      }
      // Map unknown cert aliases onto design-lab bases
      if (fixtureScenario === "proposal_ready") {
        model.banner = "FIXTURE · proposal_ready · not live authority · browser/cert only";
      }
      if (fixtureScenario === "proposal_blocked") {
        const base = buildDemoCommandModel("recon_required");
        model.portfolio = base.portfolio;
        model.risk = base.risk;
        model.banner = "FIXTURE · proposal_blocked · not live authority · browser/cert only";
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
      performancePayload: paper.performance,
      performanceError: paper.performanceError,
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
