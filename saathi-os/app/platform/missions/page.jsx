"use client";
// M59 Workstream 1 — Standalone Mission Control (list).
// Real /api/v1/platform/missions, with active-execution / pending-approval /
// attention counts derived by matching mission_id on runtime records. No
// per-mission API exists, so those counts are the honest composed truth.
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { SpatialContextDrawer } from "@/components/spatial/SpatialContextDrawer";
import { StatusPulse } from "@/components/spatial/frame";
import { usePlatformData } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { normalizeMission, filterMissions, sortMissions, missionStatusLabel } from "@/lib/workspace";

const STATUS_FILTERS = ["all", "active", "blocked", "completed", "failed", "draft"];

export default function MissionsPage() {
  const d = usePlatformData();
  const router = useRouter();
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("activity");
  const [selected, setSelected] = useState(null);

  const missions = useMemo(
    () => d.missions.map((m) => normalizeMission(m, { executions: d.executions, approvals: d.approvals, attention: d.attention })),
    [d.missions, d.executions, d.approvals, d.attention]
  );
  const visible = useMemo(() => sortMissions(filterMissions(missions, { status, q }), sort), [missions, status, q, sort]);
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";

  return (
    <SpatialWorkspaceShell
      title="Mission Control"
      subtitle="Every accessible mission, its live executions, pending approvals, and attention signals — governed by PlatformAgentRuntime and ExecutionGateway."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Missions" }]}
      signal={cSignal}
      health={d.health}
      loading={d.loading}
      error={d.error}
      paletteData={{ missions }}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <div className="ws-toolbar" style={{ marginBottom: "var(--space-4)" }}>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search missions…"
            aria-label="Search missions"
            className="mono"
            style={{ background: "transparent", border: "1px solid var(--glass-frame-border)", borderRadius: 10, color: "var(--text-primary)", padding: "7px 12px", minWidth: 200 }}
          />
          <div role="group" aria-label="Filter by status" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {STATUS_FILTERS.map((s) => (
              <button key={s} className="ws-chip" aria-pressed={status === s} onClick={() => setStatus(s)}>
                {s === "all" ? "All" : missionStatusLabel(s)}
              </button>
            ))}
          </div>
          <label className="mono" style={{ marginLeft: "auto", fontSize: "var(--fs-2xs)", color: "var(--text-muted)", display: "inline-flex", gap: 6, alignItems: "center" }}>
            Sort
            <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort missions" style={{ background: "transparent", border: "1px solid var(--glass-frame-border)", borderRadius: 8, color: "var(--text-secondary)", padding: "4px 6px" }}>
              <option value="activity">Activity</option>
              <option value="risk">Risk</option>
              <option value="status">Status</option>
            </select>
          </label>
        </div>

        {!d.loading && missions.length === 0 && (
          <div className="glass-frame" style={{ padding: "var(--space-5)" }}>
            <p style={{ color: "var(--text-muted)" }}>No active records. No missions are accessible in this workspace yet.</p>
          </div>
        )}

        {visible.length > 0 && (
          <ul className="ws-grid" aria-label="Missions" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {visible.map((m) => (
              <li key={m.id}>
                <div className={`glass-frame ${m.signal === "danger" ? "glass-frame--danger" : m.signal === "attention" ? "glass-frame--authority" : m.signal === "active" ? "glass-frame--active" : ""}`}>
                  <button className="ws-card" onClick={() => router.push(`/platform/missions/${m.id}`)} aria-label={`Open mission ${m.name}`}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                      <StatusPulse signal={m.signal} size={9} />
                      <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{m.name}</span>
                      <span className="mono" style={{ marginLeft: "auto", fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{m.statusLabel}</span>
                    </div>
                    <div className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{m.key} · {m.id}</div>
                    <div style={{ display: "flex", gap: 14, marginTop: 10 }}>
                      <Metric label="Active" value={m.activeExecutions} tone={m.activeExecutions > 0 ? "active" : "idle"} />
                      <Metric label="Approvals" value={m.pendingApprovals} tone={m.pendingApprovals > 0 ? "attention" : "idle"} />
                      <Metric label="Attention" value={m.attentionCount} tone={m.attentionCount > 0 ? "attention" : "idle"} />
                    </div>
                  </button>
                  <div style={{ padding: "0 var(--space-4) var(--space-4)" }}>
                    <button className="ws-chip" onClick={() => setSelected(m)} aria-label={`Quick inspect ${m.name}`}>Inspect</button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        <SpatialContextDrawer
          open={!!selected}
          title="Mission"
          subtitle={selected?.id}
          onClose={() => setSelected(null)}
        >
          {selected && (
            <div style={{ display: "grid", gap: 10 }}>
              <Field label="Name" value={selected.name} />
              <Field label="Status" value={selected.statusLabel} />
              <Field label="Key" value={selected.key} mono />
              <Field label="Project" value={selected.projectId} mono />
              <Field label="Owner" value={selected.owner} mono />
              <Field label="Created" value={selected.createdAt} mono />
              <Field label="Executions" value={`${selected.activeExecutions} active / ${selected.executionCount} total`} />
              <Field label="Pending approvals" value={String(selected.pendingApprovals)} />
              <Field label="Attention" value={String(selected.attentionCount)} />
              <button
                onClick={() => router.push(`/platform/missions/${selected.id}`)}
                style={{ marginTop: 6, background: "color-mix(in srgb, var(--signal-active) 16%, transparent)", border: "1px solid color-mix(in srgb, var(--signal-active) 45%, transparent)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 14px", cursor: "pointer" }}
              >
                Open full mission →
              </button>
            </div>
          )}
        </SpatialContextDrawer>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}

function Metric({ label, value, tone }) {
  const color = tone === "active" ? "var(--signal-active)" : tone === "attention" ? "var(--signal-attention)" : "var(--text-muted)";
  return (
    <span style={{ display: "flex", flexDirection: "column" }}>
      <span className="mono" style={{ fontSize: "var(--fs-lg)", color, lineHeight: 1 }}>{value}</span>
      <span className="eyebrow" style={{ color: "var(--text-muted)" }}>{label}</span>
    </span>
  );
}

function Field({ label, value, mono }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
      <span className="eyebrow" style={{ color: "var(--text-muted)" }}>{label}</span>
      <span className={mono ? "mono" : ""} style={{ fontSize: "var(--fs-sm)", color: "var(--text-secondary)", textAlign: "right", wordBreak: "break-word" }}>{value}</span>
    </div>
  );
}
