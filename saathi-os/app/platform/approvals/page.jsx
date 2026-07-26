"use client";
// M59 Workstream 3 — Approval Authority Center (list).
// Fetches ALL approval lifecycle states (status="") from the server and filters
// client-side. Decisions are NEVER optimistic — they route through the
// server-authorized decide/revoke APIs on the detail route and reconcile from
// the server afterwards.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { SpatialContextDrawer } from "@/components/spatial/SpatialContextDrawer";
import { Field, Metric, frameClass } from "@/components/spatial/primitives";
import { usePlatformData, plat } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { normalizeApproval, filterPlatformApprovals, summarizePlatformApprovals } from "@/lib/workspace";

const LIFECYCLE_FILTERS = ["all", "pending", "approved", "rejected", "expired", "revoked", "consumed"];
const RISK_FILTERS = ["all", "high", "medium", "low", "unknown"];

export default function ApprovalsPage() {
  const d = usePlatformData();
  const router = useRouter();
  const [raw, setRaw] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [lifecycle, setLifecycle] = useState("all");
  const [risk, setRisk] = useState("all");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    if (!d.token) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await plat("/approvals?status=", { token: d.token });
      setRaw(r?.approvals || []);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }, [d.token]);

  useEffect(() => {
    if (d.token) load();
  }, [d.token, load]);

  const approvals = useMemo(() => raw.map((a) => normalizeApproval(a)), [raw]);
  const summary = useMemo(() => summarizePlatformApprovals(approvals), [approvals]);
  const visible = useMemo(() => filterPlatformApprovals(approvals, { lifecycle, risk, q }), [approvals, lifecycle, risk, q]);
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";

  return (
    <SpatialWorkspaceShell
      title="Approval Authority Center"
      subtitle="Server-authorized approvals — scope, risk, evidence, and lifecycle. Decisions are enforced by the platform, never by the browser."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Approvals" }]}
      signal={cSignal}
      health={d.health}
      loading={d.loading || busy}
      error={d.error || err}
      paletteData={{ approvals }}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <div className="glass-frame" style={{ padding: "var(--space-4)", marginBottom: "var(--space-4)" }}>
          <div style={{ display: "flex", gap: 22, flexWrap: "wrap" }}>
            <Metric label="Pending" value={summary.pending} tone={summary.pending > 0 ? "attention" : "idle"} />
            <Metric label="High risk" value={summary.highRisk} tone={summary.highRisk > 0 ? "danger" : "idle"} />
            <Metric label="Consumed" value={summary.consumed} tone="idle" />
            <Metric label="Rejected" value={summary.rejected} tone="idle" />
            <Metric label="Expired" value={summary.expired} tone="idle" />
          </div>
        </div>

        <div className="ws-toolbar" style={{ marginBottom: "var(--space-4)" }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search approvals…" aria-label="Search approvals" className="mono" style={inputStyle} />
          <div role="group" aria-label="Filter by lifecycle" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {LIFECYCLE_FILTERS.map((s) => (
              <button key={s} className="ws-chip" aria-pressed={lifecycle === s} onClick={() => setLifecycle(s)}>{s === "all" ? "All" : s[0].toUpperCase() + s.slice(1)}</button>
            ))}
          </div>
          <label className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", display: "inline-flex", gap: 6, alignItems: "center" }}>
            Risk
            <select value={risk} onChange={(e) => setRisk(e.target.value)} aria-label="Filter by risk" style={selectStyle}>
              {RISK_FILTERS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </label>
        </div>

        {!busy && approvals.length === 0 && (
          <div className="glass-frame" style={{ padding: "var(--space-5)" }}>
            <p style={{ color: "var(--text-muted)" }}>No active records. No approval requests exist in this organization.</p>
          </div>
        )}

        {visible.length > 0 && (
          <ul className="ws-grid" aria-label="Approvals" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {visible.map((a) => (
              <li key={a.id}>
                <div className={`glass-frame ${frameClass(a.signal)}`}>
                  <button className="ws-card" onClick={() => router.push(`/platform/approvals/${a.id}`)} aria-label={`Open approval ${a.toolId}`}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                      <span className="mono" style={{ fontWeight: 500, color: "var(--text-primary)" }}>{a.toolId}</span>
                      <span className="mono" style={{ marginLeft: "auto", fontSize: "var(--fs-2xs)", color: riskColor(a.risk) }}>{a.risk} risk</span>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                      <Lc lifecycle={a.lifecycle} label={a.lifecycleLabel} />
                      {a.consumed && <Lc lifecycle="consumed" label="Single-use consumed" />}
                    </div>
                    <div className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{a.action || "—"} · {a.authority}</div>
                    <div className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginTop: 4 }}>Expires {a.expiresAt}</div>
                  </button>
                  <div style={{ padding: "0 var(--space-4) var(--space-4)" }}>
                    <button className="ws-chip" onClick={() => setSelected(a)} aria-label={`Quick inspect ${a.toolId}`}>Inspect</button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        <SpatialContextDrawer open={!!selected} title="Approval" subtitle={selected?.id} onClose={() => setSelected(null)}>
          {selected && (
            <div style={{ display: "grid", gap: 10 }}>
              <Field label="Tool" value={selected.toolId} mono />
              <Field label="Action" value={selected.action || "—"} />
              <Field label="Authority" value={selected.authority} mono />
              <Field label="Side-effect" value={selected.sideEffectClass} mono />
              <Field label="Risk" value={selected.risk} />
              <Field label="Lifecycle" value={selected.lifecycleLabel} />
              <Field label="Requested by" value={selected.requestedBy} mono />
              <Field label="Mission" value={selected.missionId || "—"} mono />
              <Field label="Created" value={selected.createdAt} mono />
              <Field label="Expires" value={selected.expiresAt} mono />
              <button onClick={() => router.push(`/platform/approvals/${selected.id}`)} style={openBtn}>Open full approval →</button>
            </div>
          )}
        </SpatialContextDrawer>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}

function Lc({ lifecycle, label }) {
  const c = lifecycle === "rejected" || lifecycle === "revoked" || lifecycle === "expired" ? "var(--signal-danger)"
    : lifecycle === "approved" || lifecycle === "consumed" ? "var(--signal-success)"
    : "var(--signal-attention)";
  return <span className="mono" style={{ fontSize: "var(--fs-2xs)", padding: "3px 8px", borderRadius: 999, color: c, border: `1px solid color-mix(in srgb, ${c} 40%, transparent)` }}>{label}</span>;
}

function riskColor(r) {
  return r === "high" ? "var(--signal-danger)" : r === "medium" ? "var(--signal-attention)" : "var(--text-muted)";
}

const inputStyle = { background: "transparent", border: "1px solid var(--glass-frame-border)", borderRadius: 10, color: "var(--text-primary)", padding: "7px 12px", minWidth: 200 };
const selectStyle = { background: "transparent", border: "1px solid var(--glass-frame-border)", borderRadius: 8, color: "var(--text-secondary)", padding: "4px 6px" };
const openBtn = { marginTop: 6, background: "color-mix(in srgb, var(--signal-attention) 16%, transparent)", border: "1px solid color-mix(in srgb, var(--signal-attention) 45%, transparent)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 14px", cursor: "pointer" };
