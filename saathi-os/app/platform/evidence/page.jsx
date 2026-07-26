"use client";
// M60 Workstream 9 — Evidence timeline. Read-only aggregation of authorized
// lifecycle events + governed evidence export via GET /runtime/export. Never
// renders secret-bearing logs.
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { Field, SectionPanel } from "@/components/spatial/primitives";
import { usePlatformData, plat } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { buildEvidenceTimeline, actionPermission, classifyError, errorMessage } from "@/lib/operator";
import { fmtTime } from "@/lib/workspace";
import { canExportEvidence, EVIDENCE_EXPORT_KINDS } from "@/lib/platform-ops";

const KIND_FILTERS = ["all", "mission_created", "approval_request", "approval_decision", "execution_start", "attention_event"];
const STATE_COLOR = { Available: "var(--signal-success)", Invalid: "var(--signal-danger)", Unavailable: "var(--text-muted)", Pending: "var(--signal-attention)" };

export default function EvidencePage() {
  const d = usePlatformData();
  const router = useRouter();
  const [kind, setKind] = useState("all");
  const [manifest, setManifest] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const timeline = useMemo(() => buildEvidenceTimeline({ missions: d.missions, approvals: d.approvals, executions: d.executions, attention: d.attention }), [d.missions, d.approvals, d.executions, d.attention]);
  const visible = kind === "all" ? timeline : timeline.filter((e) => e.kind === kind);
  const role = d.me?.context?.role;
  const canExport = canExportEvidence(role);
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";

  const exportEvidence = async (k) => {
    setBusy(true); setErr(null); setManifest(null);
    try {
      const r = await plat(`/runtime/export?kind=${encodeURIComponent(k)}&format=json`, { token: d.token });
      setManifest(r?.manifest || null);
    } catch (e) { setErr(errorMessage(classifyError(e))); }
    finally { setBusy(false); }
  };

  return (
    <SpatialWorkspaceShell
      title="Evidence timeline"
      subtitle="A chronological, authorized record of mission, approval, execution, and attention events. Export is governed; secret-bearing logs are never shown."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Evidence" }]}
      signal={cSignal}
      health={d.health}
      loading={d.loading || busy}
      error={d.error}
      paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <div className="ws-toolbar" style={{ marginBottom: "var(--space-4)" }}>
          <div role="group" aria-label="Filter by kind" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {KIND_FILTERS.map((k) => <button key={k} className="ws-chip" aria-pressed={kind === k} onClick={() => setKind(k)}>{k === "all" ? "All" : k.replace(/_/g, " ")}</button>)}
          </div>
          {canExport && (
            <div style={{ marginLeft: "auto", display: "flex", gap: 6, flexWrap: "wrap" }}>
              {EVIDENCE_EXPORT_KINDS.filter((k) => k !== "lifecycle_timeline").map((k) => <button key={k} className="ws-chip" onClick={() => exportEvidence(k)}>Export {k}</button>)}
            </div>
          )}
        </div>
        {!canExport && <p className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginBottom: 10 }}>Evidence export is read-only for role {role || "unknown"}.</p>}
        {err && <div className="glass-frame glass-frame--danger" style={{ padding: 12, marginBottom: 12 }} role="alert"><span style={{ color: "var(--text-secondary)" }}>{err}</span></div>}
        {manifest && (
          <SectionPanel title="Export manifest" signal="active">
            <div style={{ display: "grid", gap: 6 }}>
              <Field label="Kind" value={manifest.kind} mono />
              <Field label="Records" value={String(manifest.record_count)} />
              <Field label="Content hash" value={manifest.content_hash} mono />
              <Field label="Production data" value={String(manifest.production_data)} />
            </div>
          </SectionPanel>
        )}

        {!d.loading && timeline.length === 0 && <div className="glass-frame" style={{ padding: "var(--space-5)" }}><p style={{ color: "var(--text-muted)" }}>No evidence events. Not generated yet.</p></div>}

        <ol style={{ listStyle: "none", margin: "var(--space-4) 0 0", padding: 0, display: "grid", gap: 6 }}>
          {visible.map((e) => (
            <li key={e.id} className="glass-frame" style={{ padding: "10px 14px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", minWidth: 150 }}>{fmtTime(e.time, "—")}</span>
              <span style={{ color: "var(--text-primary)", fontSize: "var(--fs-sm)" }}>{e.label}</span>
              <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: STATE_COLOR[e.state] || "var(--text-muted)", marginLeft: "auto" }}>{e.state}</span>
              <button className="ws-chip" onClick={() => router.push(`/platform/attention/${e.object}`)} aria-label={`Inspect ${e.object}`}>Inspect</button>
            </li>
          ))}
        </ol>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}
