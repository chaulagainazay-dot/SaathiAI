"use client";
// M60 — Workflow (template) detail. Shows the guided journey and starts it by
// prefilling a LOCAL mission draft, then routing to governed mission creation.
// The template itself grants no authority and does not execute.
import { useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { WorkflowStage } from "@/components/spatial/GuidedWorkflow";
import { Field, SectionPanel } from "@/components/spatial/primitives";
import { usePlatformData } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { WORKFLOW_TEMPLATES, normalizeMissionDraft } from "@/lib/operator";
import { lsSet, LS_KEYS } from "@/lib/local-store";

export default function WorkflowDetailPage() {
  const d = usePlatformData();
  const router = useRouter();
  const { workflowId } = useParams();
  const tpl = useMemo(() => WORKFLOW_TEMPLATES.find((t) => t.id === workflowId), [workflowId]);
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";

  const start = () => {
    if (!tpl) return;
    const draft = normalizeMissionDraft({ title: tpl.name, objective: tpl.objective, risk: tpl.risk, notes: `From template: ${tpl.id}`, savedAt: nowLabel() });
    lsSet(LS_KEYS.missionDraft, draft);
    router.push("/platform/missions/new");
  };

  return (
    <SpatialWorkspaceShell
      title={tpl ? tpl.name : "Workflow"}
      subtitle={tpl ? tpl.objective : undefined}
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Workflows", href: "/platform/workflows" }, { label: tpl?.name || workflowId }]}
      signal={cSignal} health={d.health} loading={d.loading} error={d.error} paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        {!tpl ? (
          <div className="glass-frame glass-frame--danger" style={{ padding: "var(--space-5)" }} role="alert">
            <div className="eyebrow" style={{ color: "var(--signal-danger)" }}>Workflow not found</div>
            <button onClick={() => router.push("/platform/workflows")} style={backBtn}>← Back to workflows</button>
          </div>
        ) : (
          <div style={{ display: "grid", gap: "var(--space-5)" }}>
            <SectionPanel title="Guided stages" meta="LOCAL_WORKFLOW_TEMPLATE" signal="active">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                {tpl.stages.map((s, i) => (
                  <span key={s} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                    <WorkflowStage label={s} state="proposed" detail={`step ${i + 1}`} />
                    {i < tpl.stages.length - 1 && <span aria-hidden="true" style={{ color: "var(--connection-active)" }}>→</span>}
                  </span>
                ))}
              </div>
            </SectionPanel>
            <SectionPanel title="Details">
              <div style={{ display: "grid", gap: 8 }}>
                <Field label="Required inputs" value={tpl.inputs.join(", ")} />
                <Field label="Suggested roles" value={tpl.roles.join(", ")} />
                <Field label="Tools" value={tpl.tools.join(", ")} mono />
                <Field label="Approvals" value={tpl.approvals} />
                <Field label="Evidence" value={tpl.evidence} />
                <Field label="Risk" value={tpl.risk} />
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
                <button onClick={start} style={primaryBtn}>Start workflow → mission creation</button>
                <button className="ws-chip" onClick={() => router.push("/platform/templates")}>Template catalog</button>
              </div>
              <p className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginTop: 10 }}>Starting prefills a local mission draft only. Creation, approval, and execution remain governed server actions.</p>
            </SectionPanel>
          </div>
        )}
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}

function nowLabel() { try { return new Date().toISOString().slice(0, 16).replace("T", " "); } catch { return "recently"; } }
const backBtn = { background: "transparent", border: "1px solid var(--glass-frame-border)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 14px", cursor: "pointer" };
const primaryBtn = { background: "color-mix(in srgb, var(--signal-active) 18%, transparent)", border: "1px solid color-mix(in srgb, var(--signal-active) 50%, transparent)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 16px", cursor: "pointer" };
