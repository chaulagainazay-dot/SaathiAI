"use client";
// M59 Workstream 2 — Agent detail + authority view.
// Bound from the authorized binding list (matches GET /agent-bindings/{id}).
// Shows identity, scope, permitted/restricted capabilities, recent runs and
// failures, and authority lifecycle. Never renders secrets, tokens, or
// credential references.
import { useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { StatusPulse } from "@/components/spatial/frame";
import { Field, Metric, SectionPanel } from "@/components/spatial/primitives";
import { usePlatformData } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { normalizeAgent } from "@/lib/workspace";

export default function AgentDetailPage() {
  const d = usePlatformData();
  const router = useRouter();
  const { agentId } = useParams();

  const raw = useMemo(() => d.bindings.find((b) => b.binding_id === agentId), [d.bindings, agentId]);
  const agent = useMemo(() => (raw ? normalizeAgent(raw, { executions: d.executions }) : null), [raw, d.executions]);
  const cSignal = coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics });
  const notFound = d.ready && d.token && !d.loading && !raw;

  return (
    <SpatialWorkspaceShell
      title={agent ? agent.name : "Agent"}
      subtitle={agent ? `${agent.agentId} · ${agent.statusLabel}` : undefined}
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Agents", href: "/platform/agents" }, { label: agent?.name || agentId }]}
      signal={agent?.signal || cSignal}
      health={d.health}
      loading={d.loading}
      error={d.error}
      paletteData={{ agents: d.bindings.map((b) => normalizeAgent(b, {})) }}
    >
      <RequireSession token={d.token} ready={d.ready}>
        {notFound && (
          <div className="glass-frame glass-frame--danger" style={{ padding: "var(--space-5)" }} role="alert">
            <div className="eyebrow" style={{ color: "var(--signal-danger)" }}>Object not found</div>
            <p style={{ color: "var(--text-secondary)", marginTop: 8 }}>Agent binding <span className="mono">{agentId}</span> is unavailable or outside your scope.</p>
            <button onClick={() => router.push("/platform/agents")} style={backBtn}>← Back to Agent Constellation</button>
          </div>
        )}

        {agent && (
          <div style={{ display: "grid", gap: "var(--space-5)" }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "var(--space-4)" }}>
              <SectionPanel title="Identity" signal={agent.signal}>
                <div style={{ display: "grid", gap: 8 }}>
                  <Field label="Name" value={agent.name} />
                  <Field label="Identity" value={agent.agentId} mono />
                  <Field label="Description" value={agent.description || "—"} />
                  <Field label="Version" value={agent.version ?? "—"} mono />
                  <Field label="Status" value={agent.statusLabel} />
                  <Field label="Created" value={agent.createdAt} mono />
                  <Field label="Updated" value={agent.updatedAt} mono />
                </div>
              </SectionPanel>

              <SectionPanel title="Authority & scope" signal={agent.authorityKind === "execution" ? "attention" : "idle"}>
                <div style={{ display: "grid", gap: 8 }}>
                  <Field label="Authority" value={agent.authorityKind === "execution" ? "Execution-capable" : "Advisory only"} />
                  <Field label="Ceiling" value={agent.authorityCeiling} mono />
                  <Field label="Bound" value={agent.bound ? "Yes" : "No"} />
                  <Field label="Organization" value={agent.orgId} mono />
                  <Field label="Workspace" value={agent.workspaceId} mono />
                  <Field label="Project" value={agent.projectId || "—"} mono />
                  <Field label="Mission" value={agent.missionId || "—"} mono />
                </div>
                <p style={{ color: "var(--text-muted)", fontSize: "var(--fs-2xs)", marginTop: 10 }}>
                  Authority is bounded by the ceiling above and enforced server-side. This view claims no autonomy the binding does not grant.
                </p>
              </SectionPanel>
            </div>

            <SectionPanel title="Capability boundary">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)" }}>
                <div>
                  <div className="eyebrow" style={{ color: "var(--signal-active)", marginBottom: 6 }}>Permitted</div>
                  {agent.allowedTools.length === 0 && agent.allowedCapabilities.length === 0 && (
                    <p style={{ color: "var(--text-muted)", fontSize: "var(--fs-sm)" }}>None declared. Restricted to ceiling default.</p>
                  )}
                  <ul style={{ margin: 0, paddingLeft: 16, color: "var(--text-secondary)", fontSize: "var(--fs-sm)" }}>
                    {agent.allowedTools.map((t) => <li key={t} className="mono">{t}</li>)}
                    {agent.allowedCapabilities.map((c) => <li key={c} className="mono">{c}</li>)}
                  </ul>
                </div>
                <div>
                  <div className="eyebrow" style={{ color: "var(--text-muted)", marginBottom: 6 }}>Restricted</div>
                  <p style={{ color: "var(--text-muted)", fontSize: "var(--fs-sm)" }}>
                    Anything above ceiling {agent.authorityCeiling}, plus connector mutations, financial and trading execution — all disabled platform-wide.
                  </p>
                </div>
              </div>
            </SectionPanel>

            <SectionPanel title="Recent runs" meta={`${agent.runs.length} runs · ${agent.recentFailures.length} failed`} signal={agent.recentFailures.length > 0 ? "attention" : "idle"}>
              <div style={{ display: "flex", gap: 18, marginBottom: 12 }}>
                <Metric label="Runs" value={agent.runs.length} tone="idle" />
                <Metric label="Failed" value={agent.recentFailures.length} tone={agent.recentFailures.length > 0 ? "danger" : "idle"} />
              </div>
              {agent.runs.length === 0 && <p style={{ color: "var(--text-muted)" }}>No runs bound to this agent.</p>}
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 6 }}>
                {agent.runs.slice(0, 12).map((e) => (
                  <li key={e.execution_id} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span className="ws-chip" style={{ cursor: "default" }}>{e.state}</span>
                    <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{e.tool_id} · {e.execution_id}</span>
                    {e.error_code && <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--signal-danger)" }}>{e.error_code}</span>}
                  </li>
                ))}
              </ul>
            </SectionPanel>

            <div><button onClick={() => router.push("/platform/agents")} style={backBtn}>← Back to Agent Constellation</button></div>
          </div>
        )}
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}

const backBtn = { marginTop: 4, background: "transparent", border: "1px solid var(--glass-frame-border)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 14px", cursor: "pointer" };
