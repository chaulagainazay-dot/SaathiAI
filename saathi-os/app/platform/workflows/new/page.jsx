"use client";
// M60 — Start a new workflow: pick a template to launch the guided journey.
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { usePlatformData } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { WORKFLOW_TEMPLATES } from "@/lib/operator";

export default function WorkflowNewPage() {
  const d = usePlatformData();
  const router = useRouter();
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";
  return (
    <SpatialWorkspaceShell
      title="Start a workflow"
      subtitle="Choose a template. It prefills a mission draft; nothing is created or executed until you explicitly submit through the governed flow."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Workflows", href: "/platform/workflows" }, { label: "New" }]}
      signal={cSignal} health={d.health} loading={d.loading} error={d.error} paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <ul className="ws-grid" aria-label="Choose template" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {WORKFLOW_TEMPLATES.map((t) => (
            <li key={t.id}>
              <button className="ws-card glass-frame" onClick={() => router.push(`/platform/workflows/${t.id}`)} aria-label={`Choose ${t.name}`} style={{ display: "block" }}>
                <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{t.name}</span>
                <p style={{ color: "var(--text-secondary)", fontSize: "var(--fs-sm)", marginTop: 6 }}>{t.objective}</p>
              </button>
            </li>
          ))}
        </ul>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}
