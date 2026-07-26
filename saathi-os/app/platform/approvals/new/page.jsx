"use client";
// M60 Workstream 5 — Approval request preparation. LIVE: approval creation is
// POST /approvals (real). Prepares a truthful scoped request, shows a full
// review, submits server-side, reconciles, and navigates to the approval detail.
import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { ServerReconciliationState, RoleBoundaryNotice } from "@/components/spatial/GuidedWorkflow";
import { Field, SectionPanel } from "@/components/spatial/primitives";
import { usePlatformData, plat } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { buildApprovalRequest, RISK_LEVELS, actionPermission, classifyError, errorMessage } from "@/lib/operator";

function ApprovalNewInner() {
  const d = usePlatformData();
  const router = useRouter();
  const params = useSearchParams();
  const missionId = params.get("mission") || "";
  const bindingId = params.get("binding") || "";

  const [input, setInput] = useState({
    toolId: "", authority: "READ_ONLY", sideEffectClass: "READ_ONLY", reason: "", risk: "low",
    ttlSec: 3600, singleUse: true, acknowledged: false,
  });
  const [recon, setRecon] = useState("idle");
  const [err, setErr] = useState(null);

  const role = d.me?.context?.role;
  const perm = actionPermission(role, "request_approval");
  const built = useMemo(() => buildApprovalRequest({
    ...input,
    missionId,
    bindingId,
    agentId: bindingId,
    orgId: d.me?.context?.org_id,
    workspaceId: d.me?.context?.workspace_id,
  }), [input, missionId, bindingId, d.me]);
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";

  const submit = async () => {
    if (!built.valid || perm !== "permitted") return;
    setRecon("submitting");
    setErr(null);
    try {
      const res = await plat("/approvals", { method: "POST", token: d.token, body: built.body });
      setRecon("server_accepted");
      const id = res?.approval?.approval_id;
      // reconcile: refetch and confirm the record exists server-side
      const list = await plat("/approvals?status=", { token: d.token }).catch(() => ({ approvals: [] }));
      const found = (list.approvals || []).find((a) => a.approval_id === id);
      if (found) { setRecon("reconciled"); router.push(`/platform/approvals/${id}`); }
      else setRecon("unknown");
    } catch (e) {
      setRecon("server_rejected");
      setErr(errorMessage(classifyError(e)) + (e?.message ? ` — ${String(e.message).slice(0, 120)}` : ""));
    }
  };

  const set = (patch) => setInput((v) => ({ ...v, ...patch }));

  return (
    <SpatialWorkspaceShell
      title="Prepare approval request"
      subtitle="Prepares a truthful, scoped approval request for server-side submission. This is not the decision screen — the server decides."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Approvals", href: "/platform/approvals" }, { label: "New request" }]}
      signal={cSignal}
      health={d.health}
      loading={d.loading}
      error={d.error}
      paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <div style={{ display: "grid", gap: "var(--space-4)" }}>
          <RoleBoundaryNotice role={role} permission={perm} action="request approval" />
          {err && <div className="glass-frame glass-frame--danger" style={{ padding: 12 }} role="alert"><span style={{ color: "var(--text-secondary)" }}>{err}</span></div>}

          <SectionPanel title="Request" signal="attention">
            <div style={{ display: "grid", gap: 12 }}>
              <L label="Tool or capability *"><input value={input.toolId} onChange={(e) => set({ toolId: e.target.value })} placeholder="e.g. m49.local_note_write" className="mono" style={inp} aria-label="Tool" /></L>
              <L label="Requested authority"><input value={input.authority} onChange={(e) => set({ authority: e.target.value })} className="mono" style={inp} aria-label="Authority" /></L>
              <L label="Side-effect class"><input value={input.sideEffectClass} onChange={(e) => set({ sideEffectClass: e.target.value })} className="mono" style={inp} aria-label="Side-effect class" /></L>
              <L label="Reason *"><textarea value={input.reason} onChange={(e) => set({ reason: e.target.value })} style={{ ...inp, minHeight: 60 }} aria-label="Reason" /></L>
              <L label="Risk">
                <select value={input.risk} onChange={(e) => set({ risk: e.target.value })} style={inp} aria-label="Risk">{RISK_LEVELS.map((r) => <option key={r} value={r}>{r}</option>)}</select>
              </L>
              <L label="Expiration (seconds)"><input type="number" value={input.ttlSec} onChange={(e) => set({ ttlSec: Number(e.target.value) })} className="mono" style={inp} aria-label="TTL seconds" /></L>
              <label style={{ display: "flex", gap: 8, alignItems: "center", color: "var(--text-secondary)", fontSize: "var(--fs-sm)" }}>
                <input type="checkbox" checked={input.singleUse} onChange={(e) => set({ singleUse: e.target.checked })} /> Single-use expected
              </label>
              <label style={{ display: "flex", gap: 8, alignItems: "center", color: "var(--text-secondary)", fontSize: "var(--fs-sm)" }}>
                <input type="checkbox" checked={input.acknowledged} onChange={(e) => set({ acknowledged: e.target.checked })} /> I understand this requests real authority the server will decide
              </label>
            </div>
          </SectionPanel>

          <SectionPanel title="Review before submission">
            <div style={{ display: "grid", gap: 8 }}>
              <Field label="Who is requesting" value={built.preview.requestingAgent} mono />
              <Field label="What authority" value={built.preview.authority} mono />
              <Field label="Exact scope" value={`org ${built.preview.orgId || "—"} / ws ${built.preview.workspaceId || "—"} / project ${built.preview.projectId || "—"} / mission ${missionId || "—"}`} mono />
              <Field label="Tool" value={built.preview.toolId || "— (required)"} mono />
              <Field label="Risk" value={built.preview.risk} />
              <Field label="Expires in" value={`${built.preview.ttlSec}s`} />
              <Field label="Single-use" value={String(built.preview.singleUse)} />
              {!built.valid && <ul style={{ margin: "6px 0 0", paddingLeft: 18, color: "var(--signal-danger)", fontSize: "var(--fs-2xs)" }}>{built.errors.map((e, i) => <li key={i}>{e.message}</li>)}</ul>}
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 14, flexWrap: "wrap" }}>
              <button disabled={!built.valid || perm !== "permitted" || recon === "submitting"} onClick={submit} style={submitBtn(!(built.valid && perm === "permitted"))}>Submit request (server)</button>
              <ServerReconciliationState state={recon} />
            </div>
          </SectionPanel>
        </div>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}

export default function ApprovalNewPage() {
  return <Suspense fallback={null}><ApprovalNewInner /></Suspense>;
}

function L({ label, children }) {
  return <label className="eyebrow" style={{ color: "var(--text-muted)", display: "grid", gap: 4 }}>{label}{children}</label>;
}
const inp = { background: "transparent", border: "1px solid var(--glass-frame-border)", borderRadius: 8, color: "var(--text-primary)", padding: "7px 10px", font: "inherit", width: "100%", boxSizing: "border-box" };
const submitBtn = (disabled) => ({ background: disabled ? "transparent" : "color-mix(in srgb, var(--signal-attention) 18%, transparent)", border: `1px solid ${disabled ? "var(--glass-frame-border)" : "color-mix(in srgb, var(--signal-attention) 50%, transparent)"}`, color: disabled ? "var(--text-muted)" : "var(--text-primary)", borderRadius: 10, padding: "8px 16px", cursor: disabled ? "not-allowed" : "pointer" });
