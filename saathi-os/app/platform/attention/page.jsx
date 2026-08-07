"use client";
// M59 Workstream 4 — Runtime Attention Center (list).
// Attention items are runtime executions the backend flagged (attention_reasons).
// Grouped into Critical / High / Medium / Informational lanes. There is no
// acknowledge/resolve API, so the workflow is inspect + navigate + governed
// retry/cancel only — no invented remediation controls.
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { SpatialContextDrawer } from "@/components/spatial/SpatialContextDrawer";
import { StatusPulse } from "@/components/spatial/frame";
import { Field, frameClass } from "@/components/spatial/primitives";
import { usePlatformData } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { normalizeAttention, groupAttentionBySeverity, ATTENTION_GROUPS } from "@/lib/workspace";

const GROUP_LABEL = { critical: "Critical", high: "High", medium: "Medium", informational: "Informational" };

export default function AttentionPage() {
  const d = usePlatformData();
  const router = useRouter();
  const [severity, setSeverity] = useState("all");
  const [selected, setSelected] = useState(null);

  const items = useMemo(() => d.attention.map((e) => normalizeAttention(e)), [d.attention]);
  const grouped = useMemo(() => groupAttentionBySeverity(items), [items]);
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";
  const lanes = severity === "all" ? ATTENTION_GROUPS : [severity];

  return (
    <SpatialWorkspaceShell
      title="Runtime Attention Center"
      subtitle="Executions the runtime flagged for operator attention, ranked by severity. Critical items are never hidden behind hover or animation."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Attention" }]}
      signal={cSignal}
      health={d.health}
      loading={d.loading}
      error={d.error}
      paletteData={{ attention: items }}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <div className="ws-toolbar" style={{ marginBottom: "var(--space-4)" }}>
          <div role="group" aria-label="Filter by severity" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {["all", ...ATTENTION_GROUPS].map((s) => (
              <button key={s} className="ws-chip" aria-pressed={severity === s} onClick={() => setSeverity(s)}>
                {s === "all" ? "All" : GROUP_LABEL[s]}
              </button>
            ))}
          </div>
          <span className="mono" style={{ marginLeft: "auto", fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{items.length} total</span>
        </div>

        {!d.loading && items.length === 0 && (
          <div className="glass-frame glass-frame--active" style={{ padding: "var(--space-5)" }}>
            <p style={{ color: "var(--text-secondary)" }}>No executions require attention. Runtime is clear.</p>
          </div>
        )}

        <div style={{ display: "grid", gap: "var(--space-4)" }}>
          {lanes.map((lane) => {
            const laneItems = grouped[lane] || [];
            if (laneItems.length === 0) return null;
            const sig = lane === "critical" || lane === "high" ? "danger" : lane === "medium" ? "attention" : "idle";
            return (
              <section key={lane} className={`glass-frame ${frameClass(sig)}`} style={{ padding: "var(--space-4)" }} aria-label={`${GROUP_LABEL[lane]} attention`}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                  <StatusPulse signal={sig} size={9} />
                  <h2 className="display" style={{ fontSize: "var(--fs-md)", margin: 0 }}>{GROUP_LABEL[lane]}</h2>
                  <span className="mono" style={{ marginLeft: "auto", fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{laneItems.length}</span>
                </div>
                <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
                  {laneItems.map((t) => (
                    <li key={t.id} style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                      <span style={{ color: "var(--text-primary)", fontSize: "var(--fs-sm)" }}>{t.title}</span>
                      <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{t.reason}</span>
                      <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                        <button className="ws-chip" onClick={() => setSelected(t)} aria-label={`Inspect ${t.title}`}>Inspect</button>
                        <button className="ws-chip" onClick={() => router.push(`/platform/attention/${t.id}`)} aria-label={`Open ${t.title}`}>Open →</button>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>

        <SpatialContextDrawer open={!!selected} title="Attention" subtitle={selected?.id} onClose={() => setSelected(null)}>
          {selected && (
            <div style={{ display: "grid", gap: 10 }}>
              <Field label="Severity" value={selected.severityLabel} />
              <Field label="Object" value={selected.objectType} />
              <Field label="State" value={selected.state} mono />
              <Field label="Reason" value={selected.reason} />
              <Field label="Mission" value={selected.missionId || "—"} mono />
              <Field label="Agent" value={selected.agentId || "—"} mono />
              <Field label="Error code" value={selected.errorCode || "—"} mono />
              <Field label="Detected" value={selected.createdAt} mono />
              <button onClick={() => router.push(`/platform/attention/${selected.id}`)} style={openBtn}>Open full item →</button>
            </div>
          )}
        </SpatialContextDrawer>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}

const openBtn = { marginTop: 6, background: "color-mix(in srgb, var(--signal-attention) 16%, transparent)", border: "1px solid color-mix(in srgb, var(--signal-attention) 45%, transparent)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 14px", cursor: "pointer" };
