"use client";
// M60 Workstream 12 — Workflow templates (LOCAL_WORKFLOW_TEMPLATE). Planning aids
// only: they grant no authority, hold no secrets, do not execute, and do not
// bypass approvals.
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { SectionPanel } from "@/components/spatial/primitives";
import { usePlatformData } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { WORKFLOW_TEMPLATES } from "@/lib/operator";

export default function TemplatesPage() {
  const d = usePlatformData();
  const router = useRouter();
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";
  return (
    <SpatialWorkspaceShell
      title="Workflow templates"
      subtitle="Reusable planning aids. Local-only, no authority, no execution — they help you structure a mission, not bypass governance."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Templates" }]}
      signal={cSignal} health={d.health} loading={d.loading} error={d.error} paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <ul className="ws-grid" aria-label="Templates" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {WORKFLOW_TEMPLATES.map((t) => (
            <li key={t.id}>
              <div className="glass-frame" style={{ padding: "var(--space-4)", height: "100%" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{t.name}</span>
                  <span className="mono" style={{ marginLeft: "auto", fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>risk {t.risk}</span>
                </div>
                <p style={{ color: "var(--text-secondary)", fontSize: "var(--fs-sm)", marginTop: 8 }}>{t.objective}</p>
                <div className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginTop: 8 }}>Stages: {t.stages.join(" → ")}</div>
                <div className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginTop: 4 }}>Approvals: {t.approvals} · Evidence: {t.evidence}</div>
                <div style={{ marginTop: 12 }}>
                  <button className="ws-chip" onClick={() => router.push(`/platform/workflows/${t.id}`)}>Open workflow →</button>
                </div>
              </div>
            </li>
          ))}
        </ul>
        <p className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginTop: 14 }}>LOCAL_WORKFLOW_TEMPLATE — frontend planning aids, not server-persisted.</p>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}
