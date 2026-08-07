"use client";
// M71 Mission Dashboard: platform mission context plus the authenticated,
// backend-authoritative runtime hierarchy, evidence, and checkpoints.
import { useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { StatusPulse } from "@/components/spatial/frame";
import { Field, Metric, SectionPanel } from "@/components/spatial/primitives";
import { useMissionRuntime, usePlatformData } from "@/lib/platform-client";
import { formatMissionEta, normalizeMissionRuntime } from "@/lib/mission-runtime";
import { coreSignal } from "@/lib/spatial";
import { normalizeMission, normalizeAgent, normalizeApproval, normalizeAttention } from "@/lib/workspace";

/* The canonical mission → runtime lineage, rendered as a real dependency chain. */
const LINEAGE = ["Objective", "Stages", "Agents", "Approvals", "PlatformAgentRuntime", "ExecutionGateway", "Registered Tools", "Evidence"];

export default function MissionDetailPage() {
  const d = usePlatformData();
  const router = useRouter();
  const { missionId } = useParams();
  const runtimeRequest = useMissionRuntime(missionId, d.token);
  const missionRuntime = useMemo(
    () => normalizeMissionRuntime(runtimeRequest.data),
    [runtimeRequest.data]
  );
  const finalCertification = missionRuntime.certifications[0] || null;

  const raw = useMemo(() => d.missions.find((m) => m.mission_id === missionId), [d.missions, missionId]);
  const mission = useMemo(
    () => (raw ? normalizeMission(raw, { executions: d.executions, approvals: d.approvals, attention: d.attention }) : null),
    [raw, d.executions, d.approvals, d.attention]
  );
  const agents = useMemo(
    () => d.bindings.filter((b) => b.mission_id === missionId).map((b) => normalizeAgent(b, { executions: d.executions })),
    [d.bindings, d.executions, missionId]
  );
  const approvals = useMemo(() => (mission?.approvals || []).map((a) => normalizeApproval(a)), [mission]);
  const attention = useMemo(() => (mission?.attention || []).map((a) => normalizeAttention(a)), [mission]);
  const cSignal = coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics });

  const notFound = d.ready && d.token && !d.loading && !raw;

  return (
    <SpatialWorkspaceShell
      title={mission ? mission.name : "Mission"}
      subtitle={mission ? `${mission.key} · ${mission.statusLabel}` : undefined}
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Missions", href: "/platform/missions" }, { label: mission?.name || missionId }]}
      signal={missionRuntime.summary?.signal || mission?.signal || cSignal}
      health={d.health}
      loading={d.loading || runtimeRequest.loading}
      error={d.error || runtimeRequest.error}
      paletteData={{ missions: d.missions.map((m) => normalizeMission(m, {})) }}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <div data-testid="mission-detail-page" />
        {notFound && (
          <div className="glass-frame glass-frame--danger" style={{ padding: "var(--space-5)" }} role="alert">
            <div className="eyebrow" style={{ color: "var(--signal-danger)" }}>Object not found</div>
            <p style={{ color: "var(--text-secondary)", marginTop: 8 }}>
              Mission <span className="mono">{missionId}</span> is unavailable — it may be deleted, outside your scope, or not yet loaded.
            </p>
            <button onClick={() => router.push("/platform/missions")} style={backBtn}>← Back to Mission Control</button>
          </div>
        )}

        {mission && (
          <div style={{ display: "grid", gap: "var(--space-5)" }}>
            {/* lineage graph */}
            <SectionPanel title="Execution lineage" signal={mission.signal} meta="Governed path">
              <ol style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, listStyle: "none", margin: 0, padding: 0 }}>
                {LINEAGE.map((node, i) => (
                  <li key={node} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                    <span className="mono" style={{ fontSize: "var(--fs-2xs)", padding: "6px 10px", borderRadius: 999, border: "1px solid var(--glass-frame-border)", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>{node}</span>
                    {i < LINEAGE.length - 1 && <span aria-hidden="true" style={{ color: "var(--connection-active)" }}>→</span>}
                  </li>
                ))}
              </ol>
              <p style={{ color: "var(--text-muted)", fontSize: "var(--fs-2xs)", marginTop: 10 }}>
                All effects flow through PlatformAgentRuntime and ExecutionGateway. The browser holds no execution authority.
              </p>
            </SectionPanel>

            {!missionRuntime.planned && !runtimeRequest.loading && (
              <SectionPanel title="Autonomous runtime" signal="idle" meta="Not planned">
                <p style={{ color: "var(--text-muted)", margin: 0 }}>
                  This platform mission has no Autonomous Mission Runtime plan yet.
                  No progress, ETA, agent, or verification state is inferred.
                </p>
              </SectionPanel>
            )}

            {missionRuntime.planned && (
              <>
                <SectionPanel
                  title="Autonomous runtime"
                  signal={missionRuntime.summary.signal}
                  meta={`${missionRuntime.summary.health} · ${missionRuntime.summary.state}`}
                >
                  <div
                    role="progressbar"
                    aria-label="Mission completion"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={missionRuntime.summary.progress}
                    style={{ height: 8, borderRadius: 999, background: "var(--glass-frame-border)", overflow: "hidden" }}
                  >
                    <div style={{ width: `${missionRuntime.summary.progress}%`, height: "100%", background: "var(--signal-active)" }} />
                  </div>
                  <div style={{ display: "flex", gap: 22, flexWrap: "wrap", marginTop: 14 }}>
                    <Metric label="Complete" value={`${missionRuntime.summary.progress}%`} tone={missionRuntime.summary.signal === "active" ? "active" : "idle"} />
                    <Metric label="Tasks" value={`${missionRuntime.summary.taskCounts.completed || 0}/${missionRuntime.summary.taskCounts.total || 0}`} tone="idle" />
                    <Metric label="ETA" value={formatMissionEta(missionRuntime.summary.etaSeconds)} tone="idle" />
                    <Metric label="Cycles" value={missionRuntime.summary.resourceUsage.cycles || 0} tone="idle" />
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 8, marginTop: 16 }}>
                    <Field label="Objective" value={missionRuntime.objective || "Not recorded"} />
                    <Field label="Active phase" value={missionRuntime.summary.activePhaseTitle || missionRuntime.summary.activePhase || "None"} />
                    <Field label="Active task" value={missionRuntime.summary.activeTaskTitle || missionRuntime.summary.activeTask || "None"} />
                    <Field label="Current agent" value={missionRuntime.summary.currentAgent || "None"} />
                    <Field label="Tests" value={missionRuntime.summary.testStatus} />
                    <Field label="Browser" value={missionRuntime.summary.browserStatus} />
                    <Field label="Latest commit" value={missionRuntime.summary.latestCommit || "Not recorded"} mono />
                    <Field label="Rollback SHA" value={missionRuntime.summary.rollbackSha || "Not recorded"} mono />
                  </div>
                  {(missionRuntime.summary.warnings.length > 0 || missionRuntime.summary.blockers.length > 0) && (
                    <div role="alert" style={{ marginTop: 14, padding: 12, border: "1px solid var(--signal-attention)", borderRadius: 10 }}>
                      {missionRuntime.summary.warnings.map((warning) => <div key={`w-${warning}`} style={{ color: "var(--signal-attention)" }}>Warning: {warning}</div>)}
                      {missionRuntime.summary.blockers.map((blocker) => <div key={`b-${blocker}`} style={{ color: "var(--signal-danger)" }}>Blocker: {blocker}</div>)}
                    </div>
                  )}
                </SectionPanel>

                <SectionPanel title="Dependency-aware task graph" meta={`${missionRuntime.tasks.length} tasks`}>
                  <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
                    {missionRuntime.tasks.map((task) => {
                      const dependencies = missionRuntime.dependencies.filter((edge) => edge.task_id === task.node_id);
                      return (
                        <li key={task.node_id} style={{ border: "1px solid var(--glass-frame-border)", borderRadius: 10, padding: 10 }}>
                          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                            <StatusPulse signal={task.status === "COMPLETED" ? "active" : task.status === "FAILED" || task.status === "BLOCKED" ? "danger" : task.status === "WAITING" ? "attention" : "idle"} size={8} />
                            <strong style={{ color: "var(--text-primary)" }}>{task.title}</strong>
                            <span className="ws-chip" style={{ cursor: "default" }}>{task.status}</span>
                            <span className="mono" style={{ marginLeft: "auto", fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>
                              {task.agent_type || "No agent"} · priority {task.priority} · attempt {task.attempt}/{Number(task.max_retries || 0) + 1}
                            </span>
                          </div>
                          <div className="mono" style={{ marginTop: 6, fontSize: "var(--fs-2xs)", color: "var(--text-muted)", wordBreak: "break-all" }}>
                            Depends on: {dependencies.length ? dependencies.map((edge) => edge.depends_on_task_id).join(", ") : "None"}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </SectionPanel>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "var(--space-4)" }}>
                  <SectionPanel title="Mission evidence" meta={`${missionRuntime.evidence.length}`}>
                    {missionRuntime.evidence.length === 0 && <p style={{ color: "var(--text-muted)" }}>No mission evidence recorded.</p>}
                    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
                      {missionRuntime.evidence.slice(0, 12).map((item) => (
                        <li key={item.evidence_id} style={{ color: "var(--text-secondary)", fontSize: "var(--fs-sm)" }}>
                          <span className="mono">{item.status} · {item.evidence_type}</span>
                          <div>{item.summary}</div>
                          {item.reference && <div className="mono" style={{ color: "var(--text-muted)", fontSize: "var(--fs-2xs)", wordBreak: "break-all" }}>{item.reference}</div>}
                        </li>
                      ))}
                    </ul>
                  </SectionPanel>
                  <SectionPanel title="Recovery checkpoints" meta={`${missionRuntime.checkpoints.length}`}>
                    {missionRuntime.checkpoints.length === 0 && <p style={{ color: "var(--text-muted)" }}>No checkpoint recorded.</p>}
                    {missionRuntime.checkpoints.slice(0, 5).map((checkpoint) => (
                      <div key={checkpoint.checkpoint_id} style={{ marginBottom: 10 }}>
                        <Field label="Checkpoint" value={checkpoint.checkpoint_id} mono />
                        <Field label="Completed / pending" value={`${checkpoint.completed_tasks?.length || 0} / ${checkpoint.pending_tasks?.length || 0}`} />
                        <Field label="Snapshot" value={checkpoint.snapshot_hash} mono />
                      </div>
                    ))}
                  </SectionPanel>
                  <SectionPanel
                    title="Final certification"
                    signal={finalCertification ? "active" : "idle"}
                    meta={finalCertification?.verdict || "Not certified"}
                  >
                    {!finalCertification && (
                      <p style={{ color: "var(--text-muted)", margin: 0 }}>
                        No final mission certificate has been issued.
                      </p>
                    )}
                    {finalCertification && (
                      <div style={{ display: "grid", gap: 8 }}>
                        <Field label="Verdict" value={finalCertification.verdict} />
                        <Field label="Certified by" value={finalCertification.certified_by} mono />
                        <Field label="Summary" value={finalCertification.summary} />
                        <Field label="Evidence" value={`${finalCertification.evidence_ids?.length || 0} passing records`} />
                        <Field label="Snapshot" value={finalCertification.snapshot_hash} mono />
                        <Field
                          label="Limitations"
                          value={finalCertification.limitations?.length
                            ? finalCertification.limitations.join("; ")
                            : "None recorded"}
                        />
                      </div>
                    )}
                  </SectionPanel>
                </div>
              </>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "var(--space-4)" }}>
              <SectionPanel title="Mission" signal={mission.signal}>
                <div style={{ display: "grid", gap: 8 }}>
                  <Field label="Objective" value={mission.name} />
                  <Field label="Status" value={mission.statusLabel} />
                  <Field label="Key" value={mission.key} mono />
                  <Field label="Project" value={mission.projectId} mono />
                  <Field label="Workspace" value={mission.workspaceId} mono />
                  <Field label="Owner" value={mission.owner} mono />
                  <Field label="Created" value={mission.createdAt} mono />
                </div>
              </SectionPanel>
              <SectionPanel title="Platform execution state" signal={missionRuntime.summary?.signal || (mission.attentionCount > 0 ? "attention" : "active")}>
                <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
                  <Metric label="Active" value={mission.activeExecutions} tone={mission.activeExecutions > 0 ? "active" : "idle"} />
                  <Metric label="Total runs" value={mission.executionCount} tone="idle" />
                  <Metric label="Approvals" value={mission.pendingApprovals} tone={mission.pendingApprovals > 0 ? "attention" : "idle"} />
                  <Metric label="Attention" value={mission.attentionCount} tone={mission.attentionCount > 0 ? "attention" : "idle"} />
                </div>
                <p style={{ color: "var(--text-muted)", fontSize: "var(--fs-2xs)", marginTop: 12 }}>
                  Mission-runtime lifecycle comes from the dedicated authenticated API; individual tool execution timelines remain authoritative for dispatch outcomes.
                </p>
              </SectionPanel>
            </div>

            {/* assigned agents */}
            <SectionPanel title="Assigned agents" meta={`${agents.length} bound`}>
              {agents.length === 0 && <p style={{ color: "var(--text-muted)" }}>No agent bindings scoped to this mission.</p>}
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
                {agents.map((a) => (
                  <li key={a.id} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <StatusPulse signal={a.signal} size={8} />
                    <span style={{ color: "var(--text-primary)" }}>{a.name}</span>
                    <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{a.statusLabel} · {a.authorityKind} · ceiling {a.authorityCeiling}</span>
                    <button className="ws-chip" style={{ marginLeft: "auto" }} onClick={() => router.push(`/platform/agents/${a.id}`)}>Open →</button>
                  </li>
                ))}
              </ul>
            </SectionPanel>

            {/* approval junctions */}
            <SectionPanel title="Approval junctions" meta={`${approvals.length}`} signal={mission.pendingApprovals > 0 ? "attention" : "idle"}>
              {approvals.length === 0 && <p style={{ color: "var(--text-muted)" }}>No approvals recorded for this mission.</p>}
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
                {approvals.map((a) => (
                  <li key={a.id} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span className={`ws-chip`} aria-hidden="true" style={{ cursor: "default" }}>{a.lifecycleLabel}</span>
                    <span className="mono" style={{ fontSize: "var(--fs-sm)", color: "var(--text-secondary)" }}>{a.toolId} · risk {a.risk}</span>
                    <button className="ws-chip" style={{ marginLeft: "auto" }} onClick={() => router.push(`/platform/approvals/${a.id}`)}>Open →</button>
                  </li>
                ))}
              </ul>
            </SectionPanel>

            {/* attention */}
            <SectionPanel title="Related attention" meta={`${attention.length}`} signal={attention.length > 0 ? "attention" : "idle"}>
              {attention.length === 0 && <p style={{ color: "var(--text-muted)" }}>No runtime attention for this mission.</p>}
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
                {attention.map((t) => (
                  <li key={t.id} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <StatusPulse signal={t.signal} size={8} />
                    <span className="mono" style={{ fontSize: "var(--fs-sm)", color: "var(--text-secondary)" }}>{t.severityLabel} · {t.reason}</span>
                    <button className="ws-chip" style={{ marginLeft: "auto" }} onClick={() => router.push(`/platform/attention/${t.id}`)}>Open →</button>
                  </li>
                ))}
              </ul>
            </SectionPanel>

            {/* executions / evidence */}
            <SectionPanel title="Executions & evidence" meta={`${mission.executions.length} runs`}>
              {mission.executions.length === 0 && <p style={{ color: "var(--text-muted)" }}>No executions recorded. Evidence: Not generated.</p>}
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 6 }}>
                {mission.executions.map((e) => (
                  <li key={e.execution_id} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span className="ws-chip" style={{ cursor: "default" }}>{e.state}</span>
                    <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{e.tool_id} · {e.execution_id}</span>
                    {e.error_code && <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--signal-danger)" }}>{e.error_code}</span>}
                  </li>
                ))}
              </ul>
              <p style={{ color: "var(--text-muted)", fontSize: "var(--fs-2xs)", marginTop: 10 }}>
                Evidence export is governed on the Operations workspace; raw secret-bearing logs are never rendered here.
              </p>
            </SectionPanel>

            <div>
              <button onClick={() => router.push("/platform/missions")} style={backBtn}>← Back to Mission Control</button>
            </div>
          </div>
        )}
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}

const backBtn = { marginTop: 4, background: "transparent", border: "1px solid var(--glass-frame-border)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 14px", cursor: "pointer" };
