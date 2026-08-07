"use client";
// M59 Workstream 2 — Standalone Agent Constellation (list).
// Records are platform agent BINDINGS (durable runtime identities), labelled
// truthfully: advisory vs execution-capable, bound vs inactive. No record is
// implied to be an autonomous AI agent beyond what the binding grants.
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { SpatialContextDrawer } from "@/components/spatial/SpatialContextDrawer";
import { StatusPulse } from "@/components/spatial/frame";
import { Field, frameClass } from "@/components/spatial/primitives";
import { usePlatformData } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { normalizeAgent } from "@/lib/workspace";

const STATE_FILTERS = ["all", "ACTIVE", "SUSPENDED", "REVOKED"];
const STATE_LABEL = { all: "All", ACTIVE: "Available", SUSPENDED: "Inactive", REVOKED: "Blocked" };

export default function AgentsPage() {
  const d = usePlatformData();
  const router = useRouter();
  const [state, setState] = useState("all");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState(null);

  const agents = useMemo(
    () => d.bindings.map((b) => normalizeAgent(b, { executions: d.executions })),
    [d.bindings, d.executions]
  );
  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return agents.filter((a) => {
      if (state !== "all" && a.state !== state) return false;
      if (!needle) return true;
      return `${a.name} ${a.agentId} ${a.id}`.toLowerCase().includes(needle);
    });
  }, [agents, state, q]);
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";

  return (
    <SpatialWorkspaceShell
      title="Agent Constellation"
      subtitle="Platform agent bindings — their role, authority boundary, capability scope, and current runtime relationship to ExecutionGateway."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Agents" }]}
      signal={cSignal}
      health={d.health}
      loading={d.loading}
      error={d.error}
      paletteData={{ agents }}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <div className="ws-toolbar" style={{ marginBottom: "var(--space-4)" }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search agents…" aria-label="Search agents" className="mono" style={inputStyle} />
          <div role="group" aria-label="Filter by state" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {STATE_FILTERS.map((s) => (
              <button key={s} className="ws-chip" aria-pressed={state === s} onClick={() => setState(s)}>{STATE_LABEL[s]}</button>
            ))}
          </div>
        </div>

        {/* canonical relationship legend */}
        <SectionLegend />

        {!d.loading && agents.length === 0 && (
          <div className="glass-frame" style={{ padding: "var(--space-5)", marginTop: "var(--space-4)" }}>
            <p style={{ color: "var(--text-muted)" }}>No active records. No agent bindings exist in this workspace.</p>
          </div>
        )}

        {visible.length > 0 && (
          <ul className="ws-grid" aria-label="Agents" style={{ listStyle: "none", margin: "var(--space-4) 0 0", padding: 0 }}>
            {visible.map((a) => (
              <li key={a.id}>
                <div className={`glass-frame ${frameClass(a.signal)}`}>
                  <button className="ws-card" onClick={() => router.push(`/platform/agents/${a.id}`)} aria-label={`Open agent ${a.name}`}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                      <StatusPulse signal={a.signal} size={9} />
                      <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{a.name}</span>
                      <span className="mono" style={{ marginLeft: "auto", fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{a.statusLabel}</span>
                    </div>
                    <div className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{a.agentId} · v{a.version ?? "—"}</div>
                    <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                      <Tag tone={a.authorityKind === "execution" ? "attention" : "idle"}>{a.authorityKind === "execution" ? "Execution-capable" : "Advisory"}</Tag>
                      <Tag tone="idle">Ceiling {a.authorityCeiling}</Tag>
                      <Tag tone={a.bound ? "active" : "idle"}>{a.bound ? "Bound" : "Unbound"}</Tag>
                    </div>
                  </button>
                  <div style={{ padding: "0 var(--space-4) var(--space-4)" }}>
                    <button className="ws-chip" onClick={() => setSelected(a)} aria-label={`Quick inspect ${a.name}`}>Inspect</button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        <SpatialContextDrawer open={!!selected} title="Agent binding" subtitle={selected?.id} onClose={() => setSelected(null)}>
          {selected && (
            <div style={{ display: "grid", gap: 10 }}>
              <Field label="Name" value={selected.name} />
              <Field label="Identity" value={selected.agentId} mono />
              <Field label="Status" value={selected.statusLabel} />
              <Field label="Authority" value={selected.authorityKind === "execution" ? "Execution-capable" : "Advisory only"} />
              <Field label="Ceiling" value={selected.authorityCeiling} mono />
              <Field label="Bound" value={selected.bound ? "Yes" : "No"} />
              <Field label="Allowed tools" value={selected.allowedTools.length ? String(selected.allowedTools.length) : "None declared"} />
              <Field label="Mission" value={selected.missionId || "—"} mono />
              <Field label="Last update" value={selected.updatedAt} mono />
              <button onClick={() => router.push(`/platform/agents/${selected.id}`)} style={openBtn}>Open full agent →</button>
            </div>
          )}
        </SpatialContextDrawer>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}

function SectionLegend() {
  return (
    <div className="glass-frame" style={{ padding: "var(--space-4)" }}>
      <div className="eyebrow" style={{ color: "var(--text-muted)", marginBottom: 6 }}>Canonical relationship</div>
      <ol style={{ display: "flex", flexWrap: "wrap", gap: 8, listStyle: "none", margin: 0, padding: 0 }}>
        {["Agent", "Binding", "PlatformAgentRuntime", "ExecutionGateway", "Registered tools"].map((n, i, arr) => (
          <li key={n} style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
            <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-secondary)" }}>{n}</span>
            {i < arr.length - 1 && <span aria-hidden="true" style={{ color: "var(--connection-active)" }}>→</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Tag({ tone, children }) {
  const color = tone === "attention" ? "var(--signal-attention)" : tone === "active" ? "var(--signal-active)" : "var(--text-muted)";
  return (
    <span className="mono" style={{ fontSize: "var(--fs-2xs)", padding: "3px 8px", borderRadius: 999, border: `1px solid color-mix(in srgb, ${color} 40%, transparent)`, color }}>
      {children}
    </span>
  );
}

const inputStyle = { background: "transparent", border: "1px solid var(--glass-frame-border)", borderRadius: 10, color: "var(--text-primary)", padding: "7px 12px", minWidth: 200 };
const openBtn = { marginTop: 6, background: "color-mix(in srgb, var(--signal-active) 16%, transparent)", border: "1px solid color-mix(in srgb, var(--signal-active) 45%, transparent)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 14px", cursor: "pointer" };
