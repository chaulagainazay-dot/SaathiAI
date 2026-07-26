"use client";
// M59 Workstream 1 — Mission detail + execution graph.
// No per-mission API; the record is located in the authorized mission list and
// enriched from runtime executions, approvals, attention, and agent bindings
// that carry this mission_id. Absent data renders as explicit sentinels.
import { useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { StatusPulse } from "@/components/spatial/frame";
import { Field, Metric, SectionPanel, frameClass } from "@/components/spatial/primitives";
import { usePlatformData } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { normalizeMission, normalizeAgent, normalizeApproval, normalizeAttention, UNAVAILABLE } from "@/lib/workspace";
import { runtimeTone } from "@/lib/platform-ops";

/* The canonical mission → runtime lineage, rendered as a real dependency chain. */
const LINEAGE = ["Objective", "Stages", "Agents", "Approvals", "PlatformAgentRuntime", "ExecutionGateway", "Registered Tools", "Evidence"];

export default function MissionDetailPage() {
  const d = usePlatformData();
  const router = useRouter();
  const { missionId } = useParams();

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
      signal={mission?.signal || cSignal}
      health={d.health}
      loading={d.loading}
      error={d.error}
      paletteData={{ missions: d.missions.map((m) => normalizeMission(m, {})) }}
    >
      <RequireSession token={d.token} ready={d.ready}>
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
              <SectionPanel title="Runtime state" signal={mission.attentionCount > 0 ? "attention" : "active"}>
                <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
                  <Metric label="Active" value={mission.activeExecutions} tone={mission.activeExecutions > 0 ? "active" : "idle"} />
                  <Metric label="Total runs" value={mission.executionCount} tone="idle" />
                  <Metric label="Approvals" value={mission.pendingApprovals} tone={mission.pendingApprovals > 0 ? "attention" : "idle"} />
                  <Metric label="Attention" value={mission.attentionCount} tone={mission.attentionCount > 0 ? "attention" : "idle"} />
                </div>
                <p style={{ color: "var(--text-muted)", fontSize: "var(--fs-2xs)", marginTop: 12 }}>
                  Last operator action and final result are not exposed by a per-mission API; execution timelines carry the authoritative lifecycle.
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
