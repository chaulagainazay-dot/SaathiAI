"use client";
/**
 * M50 Platform foundation console — identity, tenancy, approvals, runtime health.
 * M58 Glass Frame — re-presented as a central spatial command interface: a live
 * SaathiCore, a floating module ring, and glass detail panels. All original
 * /api/v1/platform/* calls, data, safety labels and test hooks are preserved
 * unchanged; only the presentation is transformed. No live connectors. Fail-closed.
 */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Heading,
  Text,
  Button,
  Input,
  LoadingState,
  ErrorState,
  StatusBadge,
} from "@/components/ui";
import { API_BASE } from "@/lib/api";
import {
  canCancelExecution,
  canPreviewRetention,
  canExportEvidence,
  EVIDENCE_EXPORT_KINDS,
  requiresDestructiveConfirmation,
  runtimeTone,
  safetyBadges,
} from "@/lib/platform-ops";
import { coreSignal, coreMetrics, SIGNAL, SIGNAL_TOKENS } from "@/lib/spatial";
import { SpatialMap } from "@/components/spatial/SpatialMap";
import { GlassFrame, SystemStatusStrip, StatusPulse, SafetyBoundaryBadge } from "@/components/spatial/frame";
import { setToken as setPlatformToken } from "@/lib/platform-client";

const TOKEN_KEY = "saathi_platform_token";

/* module id → in-page anchor, or external route */
const ANCHORS = {
  runtime: "mod-runtime",
  approvals: "mod-approvals",
  attention: "mod-attention",
  bindings: "mod-bindings",
  projects: "mod-projects",
  missions: "mod-missions",
  operations: "mod-operations",
};

async function plat(path, { method = "GET", body, token } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers["X-Platform-Token"] = token;
  const res = await fetch(`${API_BASE}/api/v1/platform${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "include",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data?.detail?.message || data?.detail?.code || data?.error || res.statusText;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

/* A titled glass detail panel with a signal edge and anchor id. */
function ModulePanel({ id, title, signal = "idle", children, meta }) {
  return (
    <GlassFrame
      id={id}
      signal={signal}
      as="section"
      style={{ scrollMarginTop: 90, padding: "var(--space-5)" }}
      aria-label={title}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: "var(--space-4)" }}>
        <StatusPulse signal={signal} size={9} label={`${title} status`} />
        <Heading level={2} size="md" display={false} style={{ letterSpacing: "0.02em" }}>{title}</Heading>
        {meta ? <span className="mono" style={{ marginLeft: "auto", fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{meta}</span> : null}
      </div>
      {children}
    </GlassFrame>
  );
}

export default function PlatformPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("owner@local");
  const [health, setHealth] = useState(null);
  const [me, setMe] = useState(null);
  const [projects, setProjects] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [config, setConfig] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [echo, setEcho] = useState(null);
  const [bindings, setBindings] = useState([]);
  const [executions, setExecutions] = useState([]);
  const [attention, setAttention] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [selectedExecution, setSelectedExecution] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [diagnostics, setDiagnostics] = useState(null);
  const [retentionPlan, setRetentionPlan] = useState(null);
  const [exportManifest, setExportManifest] = useState(null);
  const [selectedModule, setSelectedModule] = useState(null);

  useEffect(() => {
    const t = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) || "" : "";
    setToken(t);
    plat("/health").then(setHealth).catch(() => {});
  }, []);

  const persist = (t) => {
    setToken(t);
    setPlatformToken(t);
  };

  const refresh = useCallback(async (tok) => {
    if (!tok) return;
    setBusy(true);
    setError(null);
    // Cold-start hardening (M58): the spatial home is heavier to compile, widening
    // the first-hit cold window. `get` retries transient failures; we warm up with a
    // single sequential /me call (absorbs the cold compile + CORS-activation window),
    // then fan the rest out against a now-warm backend so one straggler can no longer
    // wipe the whole authenticated surface (the old Promise.all was all-or-nothing).
    const get = async (path, attempts = 7) => {
      for (let i = 0; i < attempts; i += 1) {
        try {
          return await plat(path, { token: tok });
        } catch (e) {
          const transient = /Failed to fetch|NetworkError|load failed|ECONNREFUSED/i.test(String(e.message || e));
          if (i === attempts - 1 || !transient) {
            if (!transient) setError((prev) => prev || String(e.message || e));
            return null;
          }
          await new Promise((res) => setTimeout(res, Math.min(2500, 500 * (i + 1))));
        }
      }
      return null;
    };
    const m = await get("/me");
    const [p, a, c, h, b, x, q, r, d] = await Promise.all([
      get("/projects"),
      get("/approvals?status=pending"),
      get("/config"),
      get("/health"),
      get("/agent-bindings"),
      get("/runtime/executions?limit=50"),
      get("/runtime/attention"),
      get("/runtime/metrics"),
      get("/runtime/diagnostics"),
    ]);
    if (m) setMe(m);
    setProjects(p?.projects || []);
    setApprovals(a?.approvals || []);
    setConfig(c?.config || null);
    if (h) setHealth(h);
    setBindings(b?.bindings || []);
    setExecutions(x?.executions || []);
    setAttention(q?.attention || []);
    setMetrics(r?.metrics || null);
    setDiagnostics(d?.diagnostics || null);
    setBusy(false);
  }, []);

  useEffect(() => {
    if (token) refresh(token);
  }, [token, refresh]);

  const bootstrap = async () => {
    setBusy(true);
    setError(null);
    try {
      await plat("/bootstrap", {
        method: "POST",
        body: { email, name: "Owner", org_name: "Default Org", workspace_name: "Default Workspace" },
      });
      const login = await plat("/auth/login", { method: "POST", body: { email } });
      persist(login.token);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const login = async () => {
    setBusy(true);
    setError(null);
    try {
      const data = await plat("/auth/login", { method: "POST", body: { email } });
      persist(data.token);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    try {
      await plat("/auth/logout", { method: "POST", token });
    } catch {
      /* ignore */
    }
    persist("");
    setMe(null);
    setProjects([]);
    setApprovals([]);
    setBindings([]);
    setExecutions([]);
    setAttention([]);
    setMetrics(null);
    setSelectedExecution(null);
    setTimeline([]);
    setDiagnostics(null);
    setRetentionPlan(null);
    setExportManifest(null);
  };

  const exportEvidence = async (kind) => {
    setBusy(true);
    setExportManifest(null);
    try {
      const r = await plat(`/runtime/export?kind=${encodeURIComponent(kind)}&format=json`, {
        token,
      });
      setExportManifest(r.manifest || null);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const previewRetention = async () => {
    if (!window.confirm("Preview a dry-run retention purge? Nothing will be deleted.")) return;
    setBusy(true);
    setRetentionPlan(null);
    try {
      const r = await plat("/runtime/retention/preview", { method: "POST", token, body: {} });
      setRetentionPlan(r.retention || null);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const createProject = async () => {
    setBusy(true);
    try {
      await plat("/projects", {
        method: "POST",
        token,
        body: { name: `Project ${new Date().toISOString().slice(0, 16)}` },
      });
      await refresh(token);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const runEcho = async () => {
    setBusy(true);
    setEcho(null);
    try {
      const r = await plat("/execute", {
        method: "POST",
        token,
        body: { tool_id: "m49.echo_readonly", arguments: { text: "m50-platform" } },
      });
      setEcho(r);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const inspectExecution = async (execution) => {
    setSelectedExecution(execution);
    setError(null);
    try {
      const result = await plat(`/runtime/executions/${execution.execution_id}/timeline`, {
        token,
      });
      setTimeline(result.timeline || []);
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  const cancelExecution = async (execution) => {
    if (!canCancelExecution(execution) || !window.confirm("Cancel this eligible execution?")) return;
    setBusy(true);
    try {
      await plat(`/runtime/executions/${execution.execution_id}/cancel`, {
        method: "POST",
        token,
      });
      await refresh(token);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const bindingAction = async (binding, action) => {
    if (
      requiresDestructiveConfirmation(action === "revoke" ? "REVOKE_BINDING" : action) &&
      !window.confirm("This binding cannot be reactivated after revocation. Continue?")
    ) {
      return;
    }
    setBusy(true);
    try {
      await plat(`/agent-bindings/${binding.binding_id}/${action}`, { method: "POST", token });
      await refresh(token);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  /* ---- module ring navigation: scroll to an in-page panel, or route out ---- */
  const onSelectModule = (module) => {
    setSelectedModule(module.id);
    const anchor = ANCHORS[module.id];
    if (anchor && typeof document !== "undefined") {
      const el = document.getElementById(anchor);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
    }
    router.push(module.route);
  };

  const cSignal = token ? coreSignal({ health, metrics, diagnostics }) : (health ? SIGNAL.IDLE : SIGNAL.UNKNOWN);
  const cMetrics = coreMetrics({ metrics, approvals, attention });
  const data = { metrics, approvals, attention, bindings, projects, diagnostics, executions };
  const attnSignal = (attention.length || 0) > 0 ? "attention" : "idle";

  return (
    <div className="spatial-scope">
      <div className="spatial-canvas" style={{ padding: "var(--space-6) var(--space-5) var(--space-8)" }}>
        <div className="spatial-particles" aria-hidden="true" />

        <div style={{ position: "relative", zIndex: 1, maxWidth: 1120, margin: "0 auto", display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
          {/* ---- top status strip ---- */}
          <SystemStatusStrip>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <StatusPulse signal={cSignal} size={9} />
              <span className="mono" style={{ fontSize: "var(--fs-xs)", letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--text-primary)" }}>
                SaathiOS
              </span>
            </span>
            {health ? (
              <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>
                Identity {health.identity} · RBAC {health.rbac} · Gateway {health.runtime?.gateway}
              </span>
            ) : (
              <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>Health unavailable</span>
            )}
            <div style={{ display: "flex", gap: 8, marginLeft: "auto", flexWrap: "wrap" }}>
              <SafetyBoundaryBadge label="Private Alpha" tone="active" />
              <SafetyBoundaryBadge label="Non-production" tone="attention" />
              <SafetyBoundaryBadge label="Trading disabled" tone="idle" />
            </div>
          </SystemStatusStrip>

          {error && <ErrorState title="Platform error" detail={error} />}
          {busy && <LoadingState label="Working…" />}

          {/* ---- spatial hero: core + module ring ---- */}
          <SpatialMap
            coreSignal={cSignal}
            coreMetrics={cMetrics}
            data={data}
            selectedId={selectedModule}
            onSelect={onSelectModule}
          />

          {/* ---- session (shown until authenticated) ---- */}
          {!token && (
            <GlassFrame as="section" style={{ padding: "var(--space-5)", maxWidth: 620, margin: "0 auto", width: "100%" }} aria-label="Session">
              <Heading level={2} size="md" display={false}>Session</Heading>
              <Text tone="muted" size="sm" as="p" style={{ marginTop: 4 }}>
                Sign in to bring the runtime online. Executes only through PlatformAgentRuntime and
                ExecutionGateway. Connectors remain dry-run; production and trading are disabled.
              </Text>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: "var(--space-4)" }}>
                <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email" aria-label="Email" style={{ maxWidth: 220 }} />
                <Button variant="primary" onClick={bootstrap}>Bootstrap + login</Button>
                <Button onClick={login} variant="secondary">Login</Button>
              </div>
            </GlassFrame>
          )}

          {token && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "var(--space-5)" }}>
              {me && (
                <SystemStatusStrip>
                  <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-secondary)" }}>
                    {me.user?.name || me.user?.email} · role {me.context?.role} · org {me.context?.org_id} · workspace {me.context?.workspace_id}
                  </span>
                  <Button onClick={logout} variant="ghost" size="sm" style={{ marginLeft: "auto" }}>Logout</Button>
                </SystemStatusStrip>
              )}

              {/* ---- Operational readiness (module: operations) ---- */}
              <ModulePanel id="mod-operations" title="Operational readiness" signal="active" meta="Operations">
                <div data-testid="readiness-panel" style={{ display: "grid", gap: 10 }}>
                  <Text data-testid="env-classification" tone="muted" size="sm">
                    {(diagnostics?.environment?.classification || "LOCAL_OR_TEST")} · PRIVATE ALPHA · NON-PRODUCTION ·
                    CONNECTOR MUTATIONS DRY-RUN · FINANCIAL EXECUTION DISABLED · TRADING DISABLED
                  </Text>
                  <div data-testid="safety-badges" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {safetyBadges(diagnostics).map((badge) => (
                      <SafetyBoundaryBadge key={badge.key} label={badge.label} tone="idle" />
                    ))}
                  </div>
                  {diagnostics && (
                    <Text tone="muted" size="sm">
                      Attention {diagnostics.runtime?.attention_count} · Waiting approval {diagnostics.runtime?.waiting_approval} ·
                      Paused {diagnostics.runtime?.paused} · Reconciliations {diagnostics.runtime?.reconciliation_records} ·
                      Production authorized {String(diagnostics.environment?.production_authorized)}
                    </Text>
                  )}
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {canExportEvidence(me?.context?.role) &&
                      EVIDENCE_EXPORT_KINDS.filter((k) => k !== "lifecycle_timeline").map((kind) => (
                        <Button key={kind} data-testid={`export-${kind}`} variant="ghost" size="sm" onClick={() => exportEvidence(kind)}>
                          Export {kind}
                        </Button>
                      ))}
                  </div>
                  {exportManifest && (
                    <Text data-testid="export-manifest" tone="muted" size="sm">
                      Exported {exportManifest.kind}: {exportManifest.record_count} records · {exportManifest.content_hash} ·
                      production_data {String(exportManifest.production_data)}
                    </Text>
                  )}
                  {canPreviewRetention(me?.context?.role) && (
                    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                      <Button data-testid="retention-preview" variant="secondary" size="sm" onClick={previewRetention}>
                        Preview retention (dry-run)
                      </Button>
                      {retentionPlan && (
                        <Text data-testid="retention-plan" tone="muted" size="sm">
                          {retentionPlan.mode} · eligible {retentionPlan.eligible_for_purge} · purge_executed {String(retentionPlan.purge_executed)}
                        </Text>
                      )}
                    </div>
                  )}
                  <div style={{ marginTop: 4 }}>
                    <Button variant="ghost" size="sm" onClick={() => router.push("/platform/ops")}>Open Operations constellation →</Button>
                  </div>
                </div>
              </ModulePanel>

              {/* ---- Runtime summary (module: runtime) ---- */}
              <ModulePanel id="mod-runtime" title="Runtime" signal={metrics && metrics.failed_executions > 0 ? "attention" : "active"} meta="PlatformAgentRuntime · ExecutionGateway">
                {metrics ? (
                  <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
                    {[
                      ["Total", metrics.total_executions, "idle"],
                      ["Active", metrics.active_executions, metrics.active_executions > 0 ? "active" : "idle"],
                      ["Waiting approval", metrics.waiting_approvals, metrics.waiting_approvals > 0 ? "attention" : "idle"],
                      ["Attention", metrics.executions_requiring_attention, metrics.executions_requiring_attention > 0 ? "attention" : "idle"],
                      ["Failed", metrics.failed_executions, metrics.failed_executions > 0 ? "danger" : "idle"],
                    ].map(([k, v, sig]) => {
                      const tk = SIGNAL_TOKENS[sig];
                      return (
                        <span key={k} style={{ display: "flex", flexDirection: "column" }}>
                          <span className="mono" style={{ fontSize: "var(--fs-xl)", color: tk.color, lineHeight: 1 }}>{v}</span>
                          <span className="eyebrow" style={{ color: "var(--text-muted)" }}>{k}</span>
                        </span>
                      );
                    })}
                  </div>
                ) : (
                  <Text tone="muted" size="sm">No runtime metrics available</Text>
                )}
                <div style={{ marginTop: "var(--space-4)", display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <Button onClick={runEcho} variant="secondary" size="sm">Echo via ExecutionGateway</Button>
                  <Text tone="muted" size="xs">Read-only demo · governed execution</Text>
                </div>
                {echo && (
                  <pre style={{ marginTop: 12, fontSize: 12, overflow: "auto", color: "var(--text-secondary)" }}>{JSON.stringify(echo, null, 2)}</pre>
                )}
              </ModulePanel>

              {/* ---- Agent bindings (module: bindings) ---- */}
              <ModulePanel id="mod-bindings" title="Agent bindings" signal="active" meta={`${bindings.length} binding${bindings.length === 1 ? "" : "s"}`}>
                <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 10 }}>
                  {bindings.map((binding) => (
                    <li key={binding.binding_id} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <StatusBadge status={runtimeTone(binding.state)}>{binding.state}</StatusBadge>
                      <Text size="sm">{binding.name} · {binding.agent_id} · v{binding.version} · ceiling {binding.authority_ceiling}</Text>
                      {binding.state === "ACTIVE" && <Button onClick={() => bindingAction(binding, "suspend")} variant="ghost" size="sm">Suspend</Button>}
                      {binding.state === "SUSPENDED" && <Button onClick={() => bindingAction(binding, "activate")} variant="ghost" size="sm">Activate</Button>}
                      {binding.state !== "REVOKED" && <Button onClick={() => bindingAction(binding, "revoke")} variant="ghost" size="sm">Revoke</Button>}
                    </li>
                  ))}
                  {!bindings.length && <Text tone="muted" size="sm">No bindings in this workspace</Text>}
                </ul>
              </ModulePanel>

              {/* ---- Attention (module: attention) ---- */}
              <ModulePanel id="mod-attention" title="Runtime attention" signal={attnSignal} meta={`${attention.length} item${attention.length === 1 ? "" : "s"}`}>
                <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
                  {attention.map((execution) => (
                    <li key={execution.execution_id} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <StatusBadge status="warning">{execution.state}</StatusBadge>
                      <Text size="sm">{execution.tool_id} · {execution.attention_reasons.join(", ")}</Text>
                      <Button onClick={() => inspectExecution(execution)} variant="ghost" size="sm">Inspect</Button>
                    </li>
                  ))}
                  {!attention.length && <Text tone="muted" size="sm">No executions require attention</Text>}
                </ul>
              </ModulePanel>

              {/* ---- Executions (module: missions) ---- */}
              <ModulePanel id="mod-missions" title="Recent executions" signal="active" meta={`${executions.length} run${executions.length === 1 ? "" : "s"}`}>
                <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
                  {executions.map((execution) => (
                    <li key={execution.execution_id} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <StatusBadge status={runtimeTone(execution.state)}>{execution.state}</StatusBadge>
                      <Text size="sm" mono>{execution.tool_id} · {execution.execution_id}</Text>
                      <Button onClick={() => inspectExecution(execution)} variant="ghost" size="sm">Timeline</Button>
                      {canCancelExecution(execution) && <Button onClick={() => cancelExecution(execution)} variant="ghost" size="sm">Cancel</Button>}
                    </li>
                  ))}
                  {!executions.length && <Text tone="muted" size="sm">No runtime executions</Text>}
                </ul>
                {selectedExecution && (
                  <div style={{ marginTop: 12 }}>
                    <Heading level={3} size="sm">Lifecycle timeline</Heading>
                    <Text tone="muted" size="xs" mono>{selectedExecution.execution_id}</Text>
                    <ol style={{ marginTop: 6, color: "var(--text-secondary)", fontSize: "var(--fs-xs)" }}>
                      {timeline.map((entry, index) => (
                        <li key={`${entry.timestamp}-${entry.event_type}-${index}`}>
                          {entry.event_type} · {entry.previous_state || "—"} → {entry.new_state || "—"} · {entry.reason_code || "no reason code"}
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </ModulePanel>

              {/* ---- Projects (module: projects) ---- */}
              <ModulePanel id="mod-projects" title="Projects" signal="active" meta={`${projects.length}`}>
                <Button onClick={createProject} variant="secondary" size="sm">New project</Button>
                <ul style={{ listStyle: "none", padding: 0, margin: "var(--space-4) 0 0", display: "grid", gap: 6 }}>
                  {projects.map((p) => (
                    <li key={p.project_id}><Text size="sm">{p.name}</Text> <Text tone="muted" size="xs" mono>({p.project_id})</Text></li>
                  ))}
                  {!projects.length && <Text tone="muted" size="sm">No projects yet</Text>}
                </ul>
              </ModulePanel>

              {/* ---- Approvals (module: approvals) ---- */}
              <ModulePanel id="mod-approvals" title="Approval inbox" signal={approvals.length > 0 ? "attention" : "idle"} meta={`${approvals.length} pending`}>
                <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6 }}>
                  {approvals.map((a) => (
                    <li key={a.approval_id}><Text size="sm" mono>{a.tool_id} · {a.status} · {a.approval_id}</Text></li>
                  ))}
                  {!approvals.length && <Text tone="muted" size="sm">No pending approvals</Text>}
                </ul>
                <div style={{ marginTop: "var(--space-3)" }}>
                  <Button variant="ghost" size="sm" onClick={() => router.push("/approvals")}>Open Approval Center →</Button>
                </div>
              </ModulePanel>

              {/* ---- Configuration ---- */}
              <GlassFrame as="section" style={{ padding: "var(--space-5)" }} aria-label="Configuration">
                <Heading level={2} size="md" display={false}>Configuration</Heading>
                <pre style={{ fontSize: 12, overflow: "auto", color: "var(--text-secondary)", marginTop: 8 }}>{JSON.stringify(config, null, 2)}</pre>
              </GlassFrame>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
