"use client";
// M60 Workstream 3 + 4 + 6 — Mission planning, agent/binding selection, and
// execution readiness. The plan is DRAFT_ONLY (no plan persistence API). Agent
// selection reads real bindings. Execution readiness is classified from real
// state; the governed execute button uses the real POST /execute path (a
// read-only tool, no browser-direct tool call), reconciling from the server.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { WorkflowStage, ServerReconciliationState, RoleBoundaryNotice } from "@/components/spatial/GuidedWorkflow";
import { StatusPulse } from "@/components/spatial/frame";
import { Field, SectionPanel } from "@/components/spatial/primitives";
import { usePlatformData, plat } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import {
  buildMissionPlan, validateMissionPlan, agentSelectionBlockers, isAgentSelectable,
  classifyExecutionReadiness, READINESS, readinessSignal, actionPermission, classifyError, errorMessage,
} from "@/lib/operator";
import { getPlan, upsertPlan, publishPlan, isConflict } from "@/lib/workflow-api";

const READONLY_TOOL = "m49.echo_readonly";

export default function MissionPlanPage() {
  const d = usePlatformData();
  const router = useRouter();
  const { missionId } = useParams();
  const [selectedBinding, setSelectedBinding] = useState("");
  const [recon, setRecon] = useState("idle");
  const [execResult, setExecResult] = useState(null);
  const [err, setErr] = useState(null);
  const [persisted, setPersisted] = useState(null); // M61 server-persisted plan
  const [planRecon, setPlanRecon] = useState("idle");

  useEffect(() => {
    if (d.token && missionId) getPlan(missionId, d.token).then(setPersisted).catch(() => {});
  }, [d.token, missionId]);

  const raw = useMemo(() => d.missions.find((m) => m.mission_id === missionId), [d.missions, missionId]);
  const bindings = useMemo(() => d.bindings.filter((b) => !b.mission_id || b.mission_id === missionId || b.workspace_id === d.me?.context?.workspace_id), [d.bindings, missionId, d.me]);
  const approvals = useMemo(() => d.approvals.filter((a) => a.mission_id === missionId), [d.approvals, missionId]);
  const executions = useMemo(() => d.executions.filter((e) => e.mission_id === missionId), [d.executions, missionId]);
  const attention = useMemo(() => d.attention.filter((a) => a.mission_id === missionId), [d.attention, missionId]);

  const plan = useMemo(() => buildMissionPlan(raw, { bindings, approvals, executions, attention }), [raw, bindings, approvals, executions, attention]);
  const planValidation = useMemo(() => validateMissionPlan(plan, { bindings: bindings.filter((b) => isAgentSelectable(b, { workspaceId: d.me?.context?.workspace_id })) }), [plan, bindings, d.me]);

  const role = d.me?.context?.role;
  const execPerm = actionPermission(role, "create_mission"); // execute gated same as operator-capable
  const chosen = bindings.find((b) => b.binding_id === selectedBinding);

  const readiness = useMemo(() => classifyExecutionReadiness({
    mission: raw, orgId: d.me?.context?.org_id, workspaceId: d.me?.context?.workspace_id, projectId: raw?.project_id,
    agentValid: chosen ? isAgentSelectable(chosen, { workspaceId: d.me?.context?.workspace_id }) : false,
    toolRegistered: chosen ? (chosen.allowed_tools || []).includes(READONLY_TOOL) : false,
    approvalValid: true, // read-only tool needs no approval
    runtimeAvailable: !!d.health && /ENFORCED|ACTIVE|READY|OK/i.test(String(d.health?.runtime?.gateway || "")),
    blockingAttention: attention.length > 0,
    evidenceAvailable: true,
    productionAuthorized: d.diagnostics?.environment?.production_authorized === true,
    connectorSafe: true,
  }), [raw, chosen, d.me, d.health, attention, d.diagnostics]);

  const cSignal = coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics });
  const notFound = d.ready && d.token && !d.loading && !raw;

  const savePlan = async () => {
    setPlanRecon("submitting"); setErr(null);
    try {
      const body = { stages: plan.stages, blocked: plan.blocked, selectedBinding };
      const saved = await upsertPlan(missionId, body, d.token, persisted?.version);
      setPersisted(saved); setPlanRecon("reconciled");
    } catch (e) { setPlanRecon(isConflict(e) ? "conflict" : "server_rejected"); setErr(errorMessage(classifyError(e))); if (isConflict(e)) getPlan(missionId, d.token).then(setPersisted).catch(() => {}); }
  };
  const doPublish = async () => {
    if (!persisted) return;
    setPlanRecon("submitting"); setErr(null);
    try { const p = await publishPlan(missionId, persisted.version, d.token); setPersisted(p); setPlanRecon("reconciled"); }
    catch (e) { setPlanRecon(isConflict(e) ? "conflict" : "server_rejected"); setErr(errorMessage(classifyError(e))); }
  };

  const runGoverned = async () => {
    if (!readiness.executeAllowed) return;
    if (!window.confirm(`Run the read-only tool ${READONLY_TOOL} through the governed runtime (PlatformAgentRuntime → ExecutionGateway) for this mission? No side effects.`)) return;
    setRecon("submitting");
    setErr(null);
    setExecResult(null);
    try {
      const res = await plat("/execute", { method: "POST", token: d.token, body: { tool_id: READONLY_TOOL, arguments: { text: `mission ${missionId}` }, mission_id: missionId, project_id: raw?.project_id } });
      setRecon(res?.ok ? "reconciled" : "server_rejected");
      setExecResult(res);
    } catch (e) {
      setRecon("server_rejected");
      setErr(errorMessage(classifyError(e)));
    }
  };

  return (
    <SpatialWorkspaceShell
      title={raw ? `Plan — ${raw.name}` : "Mission plan"}
      subtitle="A reviewable plan (draft — no plan-persistence API), agent selection, and execution readiness. Execution stays governed by ExecutionGateway."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Missions", href: "/platform/missions" }, { label: raw?.name || missionId, href: `/platform/missions/${missionId}` }, { label: "Plan" }]}
      signal={raw ? readinessSignal(readiness.state) : cSignal}
      health={d.health}
      loading={d.loading}
      error={d.error}
      paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        {notFound && (
          <div className="glass-frame glass-frame--danger" style={{ padding: "var(--space-5)" }} role="alert">
            <div className="eyebrow" style={{ color: "var(--signal-danger)" }}>Mission unavailable</div>
            <button onClick={() => router.push("/platform/missions")} style={backBtn}>← Back to Mission Control</button>
          </div>
        )}

        {raw && (
          <div style={{ display: "grid", gap: "var(--space-5)" }}>
            <SectionPanel title="Plan" meta={persisted ? `SERVER_PERSISTED · v${persisted.version} · ${persisted.state}` : "Not yet saved"} signal={plan.blocked ? "attention" : "active"}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
                <button className="ws-chip" disabled={execPerm !== "permitted"} onClick={savePlan}>Save plan</button>
                {persisted && persisted.state !== "published" && <button className="ws-chip" disabled={execPerm !== "permitted"} onClick={doPublish}>Publish</button>}
                <ServerReconciliationState state={planRecon} />
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                {plan.stages.map((s, i) => (
                  <span key={s.id} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                    <WorkflowStage label={s.label} state={s.state} detail={s.detail} />
                    {i < plan.stages.length - 1 && <span aria-hidden="true" style={{ color: "var(--connection-active)" }}>→</span>}
                  </span>
                ))}
              </div>
              {planValidation.issues.length > 0 && (
                <ul style={{ margin: "12px 0 0", paddingLeft: 18, color: "var(--signal-attention)", fontSize: "var(--fs-2xs)" }}>
                  {planValidation.issues.map((it, i) => <li key={i}>{it.message}</li>)}
                </ul>
              )}
            </SectionPanel>

            <SectionPanel title="Agent / binding selection" meta={`${bindings.length} candidates`}>
              {bindings.length === 0 && <p style={{ color: "var(--text-muted)" }}>No bindings available in this workspace. Cannot select an agent.</p>}
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
                {bindings.map((b) => {
                  const blockers = agentSelectionBlockers(b, { workspaceId: d.me?.context?.workspace_id });
                  const selectable = blockers.length === 0;
                  return (
                    <li key={b.binding_id} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <input type="radio" name="binding" disabled={!selectable} checked={selectedBinding === b.binding_id} onChange={() => setSelectedBinding(b.binding_id)} aria-label={`Select ${b.name}`} />
                      <StatusPulse signal={selectable ? "active" : "danger"} size={7} />
                      <span style={{ color: selectable ? "var(--text-primary)" : "var(--text-muted)" }}>{b.name}</span>
                      <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{b.agent_id} · {b.state} · ceiling {b.authority_ceiling}</span>
                      {!selectable && <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--signal-danger)" }}>{blockers.join("; ")}</span>}
                    </li>
                  );
                })}
              </ul>
            </SectionPanel>

            <SectionPanel title="Execution readiness" meta={readiness.state} signal={readinessSignal(readiness.state)}>
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 4 }}>
                {readiness.checks.map((c) => (
                  <li key={c.id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span aria-hidden="true" style={{ color: c.ok ? "var(--signal-success)" : (c.blocking ? "var(--signal-danger)" : "var(--signal-attention)") }}>{c.ok ? "✓" : (c.blocking ? "✗" : "!")}</span>
                    <span style={{ fontSize: "var(--fs-sm)", color: "var(--text-secondary)" }}>{c.label}</span>
                  </li>
                ))}
              </ul>
              <RoleBoundaryNotice role={role} permission={execPerm} action="governed execution" />
              <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
                <button disabled={!readiness.executeAllowed || execPerm !== "permitted" || recon === "submitting"} onClick={runGoverned} style={execBtn(!(readiness.executeAllowed && execPerm === "permitted"))}>
                  Run governed read-only execution
                </button>
                <ServerReconciliationState state={recon} />
                <button className="ws-chip" onClick={() => router.push(`/platform/approvals/new?mission=${missionId}${chosen ? `&binding=${chosen.binding_id}` : ""}`)}>Prepare approval request →</button>
              </div>
              {err && <p style={{ color: "var(--signal-danger)", marginTop: 8, fontSize: "var(--fs-sm)" }}>{err}</p>}
              {execResult && (
                <div className="glass-frame" style={{ padding: 12, marginTop: 12 }}>
                  <div style={{ display: "grid", gap: 6 }}>
                    <Field label="ok" value={String(execResult.ok)} />
                    <Field label="outcome" value={execResult.outcome_class || "—"} mono />
                    <Field label="execution_id" value={execResult.execution_id || "—"} mono />
                    <Field label="state" value={execResult.execution_state || "—"} mono />
                    <Field label="message" value={execResult.safe_message || "—"} />
                  </div>
                  {execResult.execution_id && <button className="ws-chip" style={{ marginTop: 8 }} onClick={() => router.push(`/platform/attention/${execResult.execution_id}`)}>Open runtime record →</button>}
                </div>
              )}
              <p style={{ color: "var(--text-muted)", fontSize: "var(--fs-2xs)", marginTop: 10 }}>
                Execution submits through PlatformAgentRuntime → ExecutionGateway. The browser never calls a tool directly and shows no optimistic success — status comes from the server response.
              </p>
            </SectionPanel>

            <div><button onClick={() => router.push(`/platform/missions/${missionId}`)} style={backBtn}>← Back to mission</button></div>
          </div>
        )}
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}

const backBtn = { background: "transparent", border: "1px solid var(--glass-frame-border)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 14px", cursor: "pointer" };
const execBtn = (disabled) => ({ background: disabled ? "transparent" : "color-mix(in srgb, var(--signal-active) 18%, transparent)", border: `1px solid ${disabled ? "var(--glass-frame-border)" : "color-mix(in srgb, var(--signal-active) 50%, transparent)"}`, color: disabled ? "var(--text-muted)" : "var(--text-primary)", borderRadius: 10, padding: "8px 16px", cursor: disabled ? "not-allowed" : "pointer" });
