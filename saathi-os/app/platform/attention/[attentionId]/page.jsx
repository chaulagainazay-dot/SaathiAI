"use client";
// M59/M61 — Attention detail + workflow.
// An attention item IS a runtime execution; detail = GET /runtime/executions/{id}
// + its lifecycle timeline. M61 adds SERVER_AUTHORIZED acknowledge / resolve /
// reopen (persisted + audited) alongside the governed cancel.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { Field, SectionPanel } from "@/components/spatial/primitives";
import { ServerReconciliationState } from "@/components/spatial/GuidedWorkflow";
import { usePlatformData, plat } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { normalizeAttention } from "@/lib/workspace";
import { canCancelExecution } from "@/lib/platform-ops";
import { actionPermission, classifyError, errorMessage } from "@/lib/operator";
import { attentionState, attentionAction, isConflict } from "@/lib/workflow-api";

export default function AttentionDetailPage() {
  const d = usePlatformData();
  const router = useRouter();
  const { attentionId } = useParams();
  const [execution, setExecution] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [attn, setAttn] = useState(null); // M61 server attention state
  const [recon, setRecon] = useState("idle");

  const load = useCallback(async () => {
    if (!d.token) return;
    setErr(null);
    try {
      const [exec, tl, st] = await Promise.all([
        plat(`/runtime/executions/${attentionId}`, { token: d.token }).catch(() => null),
        plat(`/runtime/executions/${attentionId}/timeline`, { token: d.token }).catch(() => ({ timeline: [] })),
        attentionState(attentionId, d.token).catch(() => null),
      ]);
      setExecution(exec?.execution || exec || null);
      setTimeline(tl?.timeline || []);
      setAttn(st || null);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoaded(true);
    }
  }, [d.token, attentionId]);

  const triage = async (action) => {
    setBusy(true); setRecon("submitting"); setErr(null);
    try {
      const next = await attentionAction(attentionId, action, d.token, { expectedVersion: attn?.version });
      setAttn(next); setRecon("reconciled");
    } catch (e) {
      setRecon(isConflict(e) ? "conflict" : "server_rejected");
      setErr(errorMessage(classifyError(e)));
      await load(); // reconcile authoritative state
    } finally { setBusy(false); }
  };

  useEffect(() => {
    if (d.token) load();
  }, [d.token, load]);

  // Merge runtime attention_reasons (from the attention list) into the record.
  const rawWithReasons = useMemo(() => {
    if (!execution) return null;
    const fromList = d.attention.find((a) => a.execution_id === attentionId);
    return { ...execution, attention_reasons: fromList?.attention_reasons || execution.attention_reasons || [] };
  }, [execution, d.attention, attentionId]);

  const item = useMemo(() => (rawWithReasons ? normalizeAttention(rawWithReasons) : null), [rawWithReasons]);
  const cSignal = coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics });
  const notFound = d.ready && d.token && loaded && !execution;
  const cancellable = rawWithReasons ? canCancelExecution(rawWithReasons) : false;
  const attnPerm = actionPermission(d.me?.context?.role, "cancel_execution"); // operator+ may triage

  const cancel = async () => {
    if (!cancellable || !window.confirm("Cancel this eligible execution through the governed runtime path?")) return;
    setBusy(true);
    setErr(null);
    try {
      await plat(`/runtime/executions/${attentionId}/cancel`, { method: "POST", token: d.token });
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
      title="Attention item"
      subtitle={item ? `${item.severityLabel} · ${item.state}` : undefined}
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Attention", href: "/platform/attention" }, { label: attentionId }]}
      signal={item?.signal || cSignal}
      health={d.health}
      loading={d.loading || busy}
      error={d.error}
      paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        {notFound && (
          <div className="glass-frame glass-frame--danger" style={{ padding: "var(--space-5)" }} role="alert">
            <div className="eyebrow" style={{ color: "var(--signal-danger)" }}>Object not found</div>
            <p style={{ color: "var(--text-secondary)", marginTop: 8 }}>Execution <span className="mono">{attentionId}</span> is unavailable or outside your scope.</p>
            <button onClick={() => router.push("/platform/attention")} style={backBtn}>← Back to Attention Center</button>
          </div>
        )}

        {err && (
          <div className="glass-frame glass-frame--danger" style={{ padding: "var(--space-4)", marginBottom: "var(--space-4)" }} role="alert">
            <span className="eyebrow" style={{ color: "var(--signal-danger)" }}>Action blocked</span>
            <p style={{ color: "var(--text-secondary)", marginTop: 6 }}>{err}</p>
          </div>
        )}

        {item && (
          <div style={{ display: "grid", gap: "var(--space-5)" }}>
            <SectionPanel title="Explanation" signal={item.signal}>
              <p style={{ color: "var(--text-secondary)" }}>
                This <b>{item.severityLabel.toLowerCase()}</b> attention signal comes from execution <span className="mono">{item.id}</span>,
                currently <b>{item.state}</b>. Runtime reason: {item.reason}.
              </p>
              <p style={{ color: "var(--text-muted)", fontSize: "var(--fs-2xs)", marginTop: 8 }}>
                Recommended action: inspect the timeline below, navigate to the related mission or agent, and use the governed cancel only if the execution is still eligible. Acknowledge/resolve is not offered — no such API exists.
              </p>
            </SectionPanel>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "var(--space-4)" }}>
              <SectionPanel title="Affected object">
                <div style={{ display: "grid", gap: 8 }}>
                  <Field label="Type" value={item.objectType} />
                  <Field label="Execution" value={item.id} mono />
                  <Field label="State" value={item.state} mono />
                  <Field label="Error code" value={item.errorCode || "—"} mono />
                  <Field label="Recovery count" value={String(item.recoveryCount)} />
                  <Field label="Detected" value={item.createdAt} mono />
                  <Field label="Updated" value={item.updatedAt} mono />
                </div>
              </SectionPanel>
              <SectionPanel title="Related objects">
                <div style={{ display: "grid", gap: 8 }}>
                  <Field label="Mission" value={item.missionId || "—"} mono />
                  <Field label="Agent" value={item.agentId || "—"} mono />
                  <Field label="Approval" value={item.approvalId || "—"} mono />
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                  {item.missionId && <button className="ws-chip" onClick={() => router.push(`/platform/missions/${item.missionId}`)}>Mission →</button>}
                  {item.agentId && <button className="ws-chip" onClick={() => router.push(`/platform/agents/${item.bindingId || item.agentId}`)}>Agent →</button>}
                  {item.approvalId && <button className="ws-chip" onClick={() => router.push(`/platform/approvals/${item.approvalId}`)}>Approval →</button>}
                </div>
              </SectionPanel>
            </div>

            <SectionPanel title="Lifecycle timeline" meta={`${timeline.length} events`}>
              {timeline.length === 0 && <p style={{ color: "var(--text-muted)" }}>No timeline events. Evidence: Not generated.</p>}
              <ol style={{ margin: 0, paddingLeft: 18, color: "var(--text-secondary)", fontSize: "var(--fs-xs)", display: "grid", gap: 4 }}>
                {timeline.map((e, i) => (
                  <li key={`${e.timestamp}-${i}`} className="mono">
                    {e.event_type} · {e.previous_state || "—"} → {e.new_state || "—"} · {e.reason_code || "no reason code"}
                  </li>
                ))}
              </ol>
            </SectionPanel>

            <SectionPanel title="Triage" meta={attn ? `${attn.state} · v${attn.version}` : "open"} signal={attn?.state === "resolved" ? "active" : attn?.state === "acknowledged" ? "attention" : "idle"}>
              <p style={{ color: "var(--text-secondary)", fontSize: "var(--fs-sm)" }}>
                Server-authorized triage — acknowledge / resolve / reopen. Persisted and audited (M61); the runtime execution itself is unchanged.
              </p>
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10, flexWrap: "wrap" }}>
                {attn?.state !== "acknowledged" && attn?.state !== "resolved" && <button className="ws-chip" disabled={busy || attnPerm !== "permitted"} onClick={() => triage("acknowledge")}>Acknowledge</button>}
                {attn?.state !== "resolved" && <button className="ws-chip" disabled={busy || attnPerm !== "permitted"} onClick={() => triage("resolve")}>Resolve</button>}
                {attn?.state === "resolved" && <button className="ws-chip" disabled={busy || attnPerm !== "permitted"} onClick={() => triage("reopen")}>Reopen</button>}
                <ServerReconciliationState state={recon} />
              </div>
              {attnPerm !== "permitted" && <p className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginTop: 6 }}>Triage requires operator permission (role {d.me?.context?.role || "unknown"}).</p>}
            </SectionPanel>

            <SectionPanel title="Governed action" signal={cancellable ? "attention" : "idle"}>
              {cancellable ? (
                <div>
                  <p style={{ color: "var(--text-secondary)", fontSize: "var(--fs-sm)", marginBottom: 10 }}>
                    This execution is eligible for cancellation through the governed runtime path.
                  </p>
                  <button disabled={busy} onClick={cancel} style={cancelBtn}>Cancel execution</button>
                </div>
              ) : (
                <p style={{ color: "var(--text-muted)" }}>No governed action is available for this execution state. Recovery (resume / reconcile) remains on the Operations workspace.</p>
              )}
            </SectionPanel>

            <div><button onClick={() => router.push("/platform/attention")} style={backBtn}>← Back to Attention Center</button></div>
          </div>
        )}
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}

const backBtn = { background: "transparent", border: "1px solid var(--glass-frame-border)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 14px", cursor: "pointer" };
const cancelBtn = { background: "color-mix(in srgb, var(--signal-danger) 16%, transparent)", border: "1px solid color-mix(in srgb, var(--signal-danger) 50%, transparent)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 18px", cursor: "pointer" };
