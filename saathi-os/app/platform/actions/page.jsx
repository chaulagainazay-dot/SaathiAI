"use client";
// M60 Workstream 7 — Operator action queue. Aggregates ONLY real, supported
// operator actions from authorized records (pending approvals, blocked missions,
// failed executions, attention, onboarding). No invented acknowledge/resolve/rerun.
import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { StatusPulse } from "@/components/spatial/frame";
import { frameClass } from "@/components/spatial/primitives";
import { usePlatformData } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { aggregateOperatorActions, onboardingProgress } from "@/lib/operator";
import { lsGet, LS_KEYS } from "@/lib/local-store";

const CAT_LABEL = { urgent: "Urgent", needs_decision: "Needs decision", needs_review: "Needs review", needs_configuration: "Needs configuration", waiting: "Waiting", informational: "Informational" };
const CAT_SIGNAL = { urgent: "danger", needs_decision: "attention", needs_review: "attention", needs_configuration: "idle", waiting: "idle", informational: "idle" };

export default function ActionsPage() {
  const d = usePlatformData();
  const router = useRouter();
  const onboardingComplete = typeof window !== "undefined" ? onboardingProgress(lsGet(LS_KEYS.onboarding, [])).complete : true;

  const items = useMemo(() => aggregateOperatorActions({
    approvals: d.approvals, missions: d.missions, executions: d.executions, attention: d.attention, onboardingComplete,
  }), [d.approvals, d.missions, d.executions, d.attention, onboardingComplete]);

  const grouped = useMemo(() => {
    const g = {};
    for (const it of items) (g[it.category] ||= []).push(it);
    return g;
  }, [items]);
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";

  return (
    <SpatialWorkspaceShell
      title="Operator action queue"
      subtitle="Every safe, supported action awaiting you — derived from real authorized records. Only actions the platform actually supports appear here."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Actions" }]}
      signal={cSignal}
      health={d.health}
      loading={d.loading}
      error={d.error}
      paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        {!d.loading && items.length === 0 && (
          <div className="glass-frame glass-frame--active" style={{ padding: "var(--space-5)" }}>
            <p style={{ color: "var(--text-secondary)" }}>Queue clear. No operator actions required.</p>
          </div>
        )}
        <div style={{ display: "grid", gap: "var(--space-4)" }}>
          {Object.entries(grouped).map(([cat, list]) => (
            <section key={cat} className={`glass-frame ${frameClass(CAT_SIGNAL[cat])}`} style={{ padding: "var(--space-4)" }} aria-label={CAT_LABEL[cat]}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <StatusPulse signal={CAT_SIGNAL[cat]} size={9} />
                <h2 className="display" style={{ fontSize: "var(--fs-md)", margin: 0 }}>{CAT_LABEL[cat]}</h2>
                <span className="mono" style={{ marginLeft: "auto", fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{list.length}</span>
              </div>
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
                {list.map((it) => (
                  <li key={it.id} style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ color: "var(--text-primary)", fontSize: "var(--fs-sm)" }}>{it.title}</span>
                    <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{it.reason}</span>
                    <button className="ws-chip" style={{ marginLeft: "auto" }} onClick={() => router.push(it.route)} aria-label={`${it.action}: ${it.title}`}>{it.action} →</button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}
