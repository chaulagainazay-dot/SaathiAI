"use client";
// M60 — Workflows launcher. Lists local workflow templates as startable guided
// journeys. Starting a workflow prefills a mission draft; it grants no authority.
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { StatusPulse } from "@/components/spatial/frame";
import { usePlatformData } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { WORKFLOW_TEMPLATES } from "@/lib/operator";

export default function WorkflowsPage() {
  const d = usePlatformData();
  const router = useRouter();
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";
  return (
    <SpatialWorkspaceShell
      title="Guided workflows"
      subtitle="Start a governed operator journey from a template. Each workflow guides intent → scope → plan → agent → approval → governed execution → evidence."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Workflows" }]}
      signal={cSignal} health={d.health} loading={d.loading} error={d.error} paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <div style={{ marginBottom: "var(--space-4)" }}>
          <button className="ws-chip" onClick={() => router.push("/platform/workflows/new")}>Start a new workflow →</button>
        </div>
        <ul className="ws-grid" aria-label="Workflows" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {WORKFLOW_TEMPLATES.map((t) => (
            <li key={t.id}>
              <button className="ws-card glass-frame" onClick={() => router.push(`/platform/workflows/${t.id}`)} aria-label={`Open workflow ${t.name}`} style={{ display: "block" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <StatusPulse signal="active" size={8} />
                  <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{t.name}</span>
                </div>
                <p style={{ color: "var(--text-secondary)", fontSize: "var(--fs-sm)", marginTop: 8 }}>{t.objective}</p>
                <div className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginTop: 8 }}>{t.stages.length} stages · risk {t.risk}</div>
              </button>
            </li>
          ))}
        </ul>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}
