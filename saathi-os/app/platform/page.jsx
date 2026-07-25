"use client";
/**
 * M50 Platform foundation console — identity, tenancy, approvals, runtime health.
 * Uses /api/v1/platform/* only. No live connectors. Fail-closed.
 */
import { useCallback, useEffect, useState } from "react";
import {
  Card,
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

const TOKEN_KEY = "saathi_platform_token";

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

export default function PlatformPage() {
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

  useEffect(() => {
    const t = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) || "" : "";
    setToken(t);
    plat("/health").then(setHealth).catch(() => {});
  }, []);

  const persist = (t) => {
    setToken(t);
    if (typeof window !== "undefined") {
      if (t) localStorage.setItem(TOKEN_KEY, t);
      else localStorage.removeItem(TOKEN_KEY);
    }
  };

  const refresh = useCallback(async (tok) => {
    if (!tok) return;
    setBusy(true);
    setError(null);
    try {
      const [m, p, a, c, h, b, x, q, r, d] = await Promise.all([
        plat("/me", { token: tok }),
        plat("/projects", { token: tok }),
        plat("/approvals?status=pending", { token: tok }),
        plat("/config", { token: tok }),
        plat("/health"),
        plat("/agent-bindings", { token: tok }),
        plat("/runtime/executions?limit=50", { token: tok }),
        plat("/runtime/attention", { token: tok }),
        plat("/runtime/metrics", { token: tok }),
        plat("/runtime/diagnostics", { token: tok }),
      ]);
      setMe(m);
      setProjects(p.projects || []);
      setApprovals(a.approvals || []);
      setConfig(c.config || null);
      setHealth(h);
      setBindings(b.bindings || []);
      setExecutions(x.executions || []);
      setAttention(q.attention || []);
      setMetrics(r.metrics || null);
      setDiagnostics(d.diagnostics || null);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
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

  return (
    <div className="page-stack" style={{ maxWidth: 960, margin: "0 auto", padding: "1.5rem" }}>
      <Heading level={1}>Platform foundation</Heading>
      <Text tone="muted">
        Private-alpha runtime operations · tenant-scoped bindings · lifecycle evidence. Executes
        only through PlatformAgentRuntime and ExecutionGateway. Connectors remain dry-run.
        Production and trading are disabled.
      </Text>

      {error && <ErrorState title="Platform error" message={error} />}
      {busy && <LoadingState label="Working…" />}

      <Card>
        <Heading level={2}>Runtime health</Heading>
        {health ? (
          <div style={{ display: "grid", gap: 8 }}>
            <StatusBadge status={health.identity === "ACTIVE" ? "ok" : "warn"}>
              Identity {health.identity}
            </StatusBadge>
            <Text>
              RBAC {health.rbac} · Approvals {health.approval_center} · Gateway{" "}
              {health.runtime?.gateway}
            </Text>
            <Text tone="muted">
              {health.runtime?.connectors} · {health.runtime?.trading_guardian}
            </Text>
          </div>
        ) : (
          <Text tone="muted">Health unavailable</Text>
        )}
      </Card>

      <Card>
        <Heading level={2}>Session</Heading>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <Input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email"
            aria-label="Email"
          />
          <Button onClick={bootstrap}>Bootstrap + login</Button>
          <Button onClick={login} variant="secondary">
            Login
          </Button>
          {token && (
            <Button onClick={logout} variant="ghost">
              Logout
            </Button>
          )}
        </div>
        {me && (
          <div style={{ marginTop: 12 }}>
            <Text>
              {me.user?.name || me.user?.email} · role {me.context?.role}
            </Text>
            <Text tone="muted">
              org {me.context?.org_id} · workspace {me.context?.workspace_id}
            </Text>
          </div>
        )}
      </Card>

      {token && (
        <>
          <Card>
            <Heading level={2}>Runtime summary</Heading>
            {metrics ? (
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                <Text>Total {metrics.total_executions}</Text>
                <Text>Active {metrics.active_executions}</Text>
                <Text>Waiting approval {metrics.waiting_approvals}</Text>
                <Text>Attention {metrics.executions_requiring_attention}</Text>
                <Text>Failed {metrics.failed_executions}</Text>
              </div>
            ) : (
              <Text tone="muted">No runtime metrics available</Text>
            )}
          </Card>

          <Card>
            <Heading level={2}>Operational readiness</Heading>
            <div data-testid="readiness-panel" style={{ display: "grid", gap: 10 }}>
              <Text data-testid="env-classification" tone="muted">
                {(diagnostics?.environment?.classification || "LOCAL_OR_TEST")} · PRIVATE
                ALPHA · NON-PRODUCTION · CONNECTOR MUTATIONS DRY-RUN · FINANCIAL
                EXECUTION DISABLED · TRADING DISABLED
              </Text>
              <div
                data-testid="safety-badges"
                style={{ display: "flex", gap: 8, flexWrap: "wrap" }}
              >
                {safetyBadges(diagnostics).map((badge) => (
                  <Text key={badge.key} tone="muted">
                    {badge.label}
                  </Text>
                ))}
              </div>
              {diagnostics && (
                <Text tone="muted">
                  Attention {diagnostics.runtime?.attention_count} · Waiting approval{" "}
                  {diagnostics.runtime?.waiting_approval} · Paused{" "}
                  {diagnostics.runtime?.paused} · Reconciliations{" "}
                  {diagnostics.runtime?.reconciliation_records} · Production authorized{" "}
                  {String(diagnostics.environment?.production_authorized)}
                </Text>
              )}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {canExportEvidence(me?.context?.role) &&
                  EVIDENCE_EXPORT_KINDS.filter(
                    (k) => k !== "lifecycle_timeline",
                  ).map((kind) => (
                    <Button
                      key={kind}
                      data-testid={`export-${kind}`}
                      variant="ghost"
                      onClick={() => exportEvidence(kind)}
                    >
                      Export {kind}
                    </Button>
                  ))}
              </div>
              {exportManifest && (
                <Text data-testid="export-manifest" tone="muted">
                  Exported {exportManifest.kind}: {exportManifest.record_count} records ·{" "}
                  {exportManifest.content_hash} · production_data{" "}
                  {String(exportManifest.production_data)}
                </Text>
              )}
              {canPreviewRetention(me?.context?.role) && (
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <Button
                    data-testid="retention-preview"
                    variant="secondary"
                    onClick={previewRetention}
                  >
                    Preview retention (dry-run)
                  </Button>
                  {retentionPlan && (
                    <Text data-testid="retention-plan" tone="muted">
                      {retentionPlan.mode} · eligible {retentionPlan.eligible_for_purge} ·
                      purge_executed {String(retentionPlan.purge_executed)}
                    </Text>
                  )}
                </div>
              )}
            </div>
          </Card>

          <Card>
            <Heading level={2}>Agent bindings</Heading>
            <ul>
              {bindings.map((binding) => (
                <li key={binding.binding_id} style={{ marginBottom: 10 }}>
                  <StatusBadge status={runtimeTone(binding.state)}>{binding.state}</StatusBadge>{" "}
                  {binding.name} · {binding.agent_id} · v{binding.version} · ceiling{" "}
                  {binding.authority_ceiling}
                  {binding.state === "ACTIVE" && (
                    <Button onClick={() => bindingAction(binding, "suspend")} variant="ghost">
                      Suspend
                    </Button>
                  )}
                  {binding.state === "SUSPENDED" && (
                    <Button onClick={() => bindingAction(binding, "activate")} variant="ghost">
                      Activate
                    </Button>
                  )}
                  {binding.state !== "REVOKED" && (
                    <Button onClick={() => bindingAction(binding, "revoke")} variant="ghost">
                      Revoke
                    </Button>
                  )}
                </li>
              ))}
              {!bindings.length && <Text tone="muted">No bindings in this workspace</Text>}
            </ul>
          </Card>

          <Card>
            <Heading level={2}>Runtime attention queue</Heading>
            <ul>
              {attention.map((execution) => (
                <li key={execution.execution_id}>
                  <StatusBadge status="warn">{execution.state}</StatusBadge>{" "}
                  {execution.tool_id} · {execution.attention_reasons.join(", ")}
                  <Button onClick={() => inspectExecution(execution)} variant="ghost">
                    Inspect
                  </Button>
                </li>
              ))}
              {!attention.length && <Text tone="muted">No executions require attention</Text>}
            </ul>
          </Card>

          <Card>
            <Heading level={2}>Recent runtime executions</Heading>
            <ul>
              {executions.map((execution) => (
                <li key={execution.execution_id} style={{ marginBottom: 8 }}>
                  <StatusBadge status={runtimeTone(execution.state)}>{execution.state}</StatusBadge>{" "}
                  {execution.tool_id} · {execution.execution_id}
                  <Button onClick={() => inspectExecution(execution)} variant="ghost">
                    Timeline
                  </Button>
                  {canCancelExecution(execution) && (
                    <Button onClick={() => cancelExecution(execution)} variant="ghost">
                      Cancel
                    </Button>
                  )}
                </li>
              ))}
              {!executions.length && <Text tone="muted">No runtime executions</Text>}
            </ul>
            {selectedExecution && (
              <div style={{ marginTop: 12 }}>
                <Heading level={3}>Lifecycle timeline</Heading>
                <Text tone="muted">{selectedExecution.execution_id}</Text>
                <ol>
                  {timeline.map((entry, index) => (
                    <li key={`${entry.timestamp}-${entry.event_type}-${index}`}>
                      {entry.event_type} · {entry.previous_state || "—"} →{" "}
                      {entry.new_state || "—"} · {entry.reason_code || "no reason code"}
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </Card>

          <Card>
            <Heading level={2}>Projects</Heading>
            <Button onClick={createProject}>New project</Button>
            <ul style={{ marginTop: 12 }}>
              {projects.map((p) => (
                <li key={p.project_id}>
                  {p.name} <Text tone="muted">({p.project_id})</Text>
                </li>
              ))}
              {!projects.length && <Text tone="muted">No projects yet</Text>}
            </ul>
          </Card>

          <Card>
            <Heading level={2}>Approval inbox (pending)</Heading>
            <ul>
              {approvals.map((a) => (
                <li key={a.approval_id}>
                  {a.tool_id} · {a.status} · {a.approval_id}
                </li>
              ))}
              {!approvals.length && <Text tone="muted">No pending approvals</Text>}
            </ul>
          </Card>

          <Card>
            <Heading level={2}>Runtime execute (read-only demo)</Heading>
            <Button onClick={runEcho}>Echo via ExecutionGateway</Button>
            {echo && (
              <pre style={{ marginTop: 12, fontSize: 12, overflow: "auto" }}>
                {JSON.stringify(echo, null, 2)}
              </pre>
            )}
          </Card>

          <Card>
            <Heading level={2}>Configuration</Heading>
            <pre style={{ fontSize: 12, overflow: "auto" }}>
              {JSON.stringify(config, null, 2)}
            </pre>
          </Card>
        </>
      )}
    </div>
  );
}
