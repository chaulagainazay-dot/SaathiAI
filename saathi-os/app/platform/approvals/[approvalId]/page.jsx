"use client";
// M59 Workstream 3 — Approval detail + server-authorized decision.
// Approve/reject call POST /approvals/{id}/decide; revoke calls .../revoke.
// The browser holds NO authority: after any decision we refetch from the server
// and render the authoritative record. Decidability is re-derived from server
// state, never optimistically flipped. Stale / expired / consumed / insufficient
// -authority responses are surfaced verbatim (minus secrets).
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { Field, SectionPanel } from "@/components/spatial/primitives";
import { usePlatformData, plat } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { normalizeApproval } from "@/lib/workspace";

export default function ApprovalDetailPage() {
  const d = usePlatformData();
  const router = useRouter();
  const { approvalId } = useParams();
  const [raw, setRaw] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [reason, setReason] = useState("");

  // No single-GET approval API — fetch the authorized list (all statuses) and
  // select this record. Re-run after each decision to reconcile from server.
  const load = useCallback(async () => {
    if (!d.token) return;
    setErr(null);
    try {
      const r = await plat("/approvals?status=", { token: d.token });
      const hit = (r?.approvals || []).find((a) => a.approval_id === approvalId) || null;
      setRaw(hit);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoaded(true);
    }
  }, [d.token, approvalId]);

  useEffect(() => {
    if (d.token) load();
  }, [d.token, load]);

  const approval = useMemo(() => (raw ? normalizeApproval(raw) : null), [raw]);
  const cSignal = coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics });
  const notFound = d.ready && d.token && loaded && !raw;

  const decide = async (approve) => {
    if (!approval?.decidable) return;
    const verb = approve ? "APPROVE" : "REJECT";
    const ok = window.confirm(
      `${verb} this authority request?\n\nTool: ${approval.toolId}\nAuthority: ${approval.authority}\nScope: org ${approval.orgId} / ws ${approval.workspaceId}${approval.missionId ? ` / mission ${approval.missionId}` : ""}\nExpires: ${approval.expiresAt}\n\nThis is a governed, server-enforced decision.`
    );
    if (!ok) return;
    setBusy(true);
    setErr(null);
    try {
      await plat(`/approvals/${approval.id}/decide`, { method: "POST", token: d.token, body: { approve, reason } });
      await load(); // reconcile authoritative state from server
    } catch (e) {
      setErr(String(e.message || e));
      await load(); // resync even on failure (may be stale/expired/consumed)
    } finally {
      setBusy(false);
    }
  };

  const revoke = async () => {
    if (!window.confirm("Revoke this approval? This cannot be reactivated.")) return;
    setBusy(true);
    setErr(null);
    try {
      await plat(`/approvals/${approval.id}/revoke`, { method: "POST", token: d.token });
      await load();
    } catch (e) {
      setErr(String(e.message || e));
      await load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <SpatialWorkspaceShell
      title="Approval"
      subtitle={approval ? `${approval.toolId} · ${approval.lifecycleLabel}` : undefined}
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Approvals", href: "/platform/approvals" }, { label: approval?.toolId || approvalId }]}
      signal={approval?.signal || cSignal}
      health={d.health}
      loading={d.loading || busy}
      error={d.error}
      paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <div data-testid="approval-detail-page" />
        {notFound && (
          <div className="glass-frame glass-frame--danger" style={{ padding: "var(--space-5)" }} role="alert">
            <div className="eyebrow" style={{ color: "var(--signal-danger)" }}>Object not found</div>
            <p style={{ color: "var(--text-secondary)", marginTop: 8 }}>Approval <span className="mono">{approvalId}</span> is unavailable or outside your scope.</p>
            <button onClick={() => router.push("/platform/approvals")} style={backBtn}>← Back to Approval Center</button>
          </div>
        )}

        {err && (
          <div className="glass-frame glass-frame--danger" style={{ padding: "var(--space-4)", marginBottom: "var(--space-4)" }} role="alert">
            <span className="eyebrow" style={{ color: "var(--signal-danger)" }}>Decision blocked</span>
            <p style={{ color: "var(--text-secondary)", marginTop: 6 }}>{err}</p>
          </div>
        )}

        {approval && (
          <div style={{ display: "grid", gap: "var(--space-5)" }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "var(--space-4)" }}>
              <SectionPanel title="Request summary" signal={approval.signal}>
                <div style={{ display: "grid", gap: 8 }}>
                  <Field label="Tool" value={approval.toolId} mono />
                  <Field label="Requested action" value={approval.action || "—"} />
                  <Field label="Capability" value={approval.capability || "—"} mono />
                  <Field label="Connector" value={approval.connector || "—"} mono />
                  <Field label="Target resource" value={approval.targetResource || "—"} mono />
                  <Field label="Requested by" value={approval.requestedBy} mono />
                </div>
              </SectionPanel>
              <SectionPanel title="Authority & scope" signal={approval.risk === "high" ? "danger" : "attention"}>
                <div style={{ display: "grid", gap: 8 }}>
                  <Field label="Authority" value={approval.authority} mono />
                  <Field label="Side-effect class" value={approval.sideEffectClass} mono />
                  <Field label="Risk level" value={approval.risk} />
                  <Field label="Organization" value={approval.orgId} mono />
                  <Field label="Workspace" value={approval.workspaceId} mono />
                  <Field label="Project" value={approval.projectId || "—"} mono />
                  <Field label="Mission" value={approval.missionId || "—"} mono />
                  <Field label="Run" value={approval.runId || "—"} mono />
                </div>
              </SectionPanel>
            </div>

            <SectionPanel title="Lifecycle & consumption">
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 }}>
                <Field label="Status" value={approval.lifecycleLabel} />
                <Field label="Single-use" value={approval.consumed ? "Consumed" : "Not consumed"} />
                <Field label="Expired" value={approval.expired ? "Yes" : "No"} />
                <Field label="Created" value={approval.createdAt} mono />
                <Field label="Expires" value={approval.expiresAt} mono />
                <Field label="Decided at" value={approval.decidedAt || "—"} mono />
                <Field label="Decided by" value={approval.decidedBy || "—"} mono />
                <Field label="Consumed at" value={approval.consumedAt || "—"} mono />
                <Field label="Reason" value={approval.reason || "—"} />
              </div>
            </SectionPanel>

            <SectionPanel title="Operator decision" signal={approval.decidable ? "attention" : "idle"}>
              {approval.decidable ? (
                <div style={{ display: "grid", gap: 12 }}>
                  <p style={{ color: "var(--text-secondary)", fontSize: "var(--fs-sm)" }}>
                    Deciding grants exactly the scope above until {approval.expiresAt}. This is a consequential, server-enforced action.
                  </p>
                  <label className="eyebrow" style={{ color: "var(--text-muted)" }}>
                    Decision reason (optional)
                    <input value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Decision reason" className="mono" style={{ display: "block", width: "100%", boxSizing: "border-box", marginTop: 4, background: "transparent", border: "1px solid var(--glass-frame-border)", borderRadius: 8, color: "var(--text-primary)", padding: "7px 10px" }} />
                  </label>
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <button data-testid="approval-approve" disabled={busy} onClick={() => decide(true)} style={approveBtn}>Approve</button>
                    <button data-testid="approval-reject" disabled={busy} onClick={() => decide(false)} style={rejectBtn}>Reject</button>
                    <button disabled={busy} onClick={revoke} style={backBtn}>Revoke</button>
                  </div>
                </div>
              ) : (
                <p style={{ color: "var(--text-muted)" }}>
                  This approval is {approval.lifecycleLabel.toLowerCase()} and can no longer be decided. The server is the sole authority; no browser action can change a settled record.
                </p>
              )}
            </SectionPanel>

            <div><button onClick={() => router.push("/platform/approvals")} style={backBtn}>← Back to Approval Center</button></div>
          </div>
        )}
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}

const backBtn = { background: "transparent", border: "1px solid var(--glass-frame-border)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 14px", cursor: "pointer" };
const approveBtn = { background: "color-mix(in srgb, var(--signal-success) 18%, transparent)", border: "1px solid color-mix(in srgb, var(--signal-success) 55%, transparent)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 18px", cursor: "pointer" };
const rejectBtn = { background: "color-mix(in srgb, var(--signal-danger) 16%, transparent)", border: "1px solid color-mix(in srgb, var(--signal-danger) 50%, transparent)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 18px", cursor: "pointer" };
