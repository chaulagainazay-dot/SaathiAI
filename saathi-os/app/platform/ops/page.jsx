"use client";
/**
 * M55 Operator Console — centralized, read-only operations dashboard.
 * Aggregates platform health, metrics, release readiness, recovery, and backup
 * validation. Read-only except already-approved operations. Uses
 * /api/v1/platform/* only. No live connectors. Fail-closed.
 */
import { useCallback, useEffect, useState } from "react";
import {
  Card,
  Heading,
  Text,
  Button,
  LoadingState,
  ErrorState,
  StatusBadge,
} from "@/components/ui";
import { API_BASE } from "@/lib/api";
import { safetyBadges } from "@/lib/platform-ops";

const TOKEN_KEY = "saathi_platform_token";

async function plat(path, { method = "GET", token } = {}) {
  const headers = { "content-type": "application/json" };
  if (token) headers["X-Platform-Token"] = token;
  const res = await fetch(`${API_BASE}/api/v1/platform${path}`, { method, headers });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

function statusTone(status) {
  if (status === "PASS" || status === "READY" || status === "ok") return "ok";
  if (status === "FAIL" || status === "NOT_READY") return "error";
  if (status === "WARNING" || status === "READY_WITH_LIMITATIONS" || status === "UNKNOWN")
    return "warn";
  return "neutral";
}

export default function OperatorConsolePage() {
  const [token, setToken] = useState("");
  const [health, setHealth] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [release, setRelease] = useState(null);
  const [recovery, setRecovery] = useState(null);
  const [backup, setBackup] = useState(null);
  const [topology, setTopology] = useState(null);
  const [nodeHealth, setNodeHealth] = useState(null);
  const [clusterMetrics, setClusterMetrics] = useState(null);
  const [scheduler, setScheduler] = useState(null);
  const [clusterRecovery, setClusterRecovery] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) || "" : "";
    setToken(t);
  }, []);

  const refresh = useCallback(async (tok) => {
    if (!tok) return;
    setBusy(true);
    setLoading(true);
    setError(null);
    // Cold-start hardening: during first Next.js route compilation, concurrent
    // cross-origin fetches can transiently fail. Retry each with bounded backoff
    // so a cold race shows "Loading…" then data — never a misleading fatal.
    const loadWithRetry = async (path, key, setter, attempts = 4) => {
      for (let i = 0; i < attempts; i += 1) {
        try {
          const r = await plat(path, { token: tok });
          setter(r[key] || null);
          return true;
        } catch (e) {
          const transient = /Failed to fetch|NetworkError|load failed|ECONNREFUSED/i.test(
            String(e.message || e),
          );
          if (i === attempts - 1 || !transient) {
            // Only surface a genuine error after retries are exhausted, or on a
            // non-transient error (e.g. 401/403). Cold-start races stay quiet.
            if (!transient) setError((prev) => prev || String(e.message || e));
            else setError((prev) => prev || `Some data unavailable (${path})`);
            return false;
          }
          await new Promise((res) => setTimeout(res, 400 * (i + 1))); // 400/800/1200ms
        }
      }
      return false;
    };
    await Promise.allSettled([
      loadWithRetry("/release/health", "health", setHealth),
      loadWithRetry("/release/metrics", "metrics", setMetrics),
      loadWithRetry("/cluster/topology", "topology", setTopology),
      loadWithRetry("/cluster/node-health", "node_health", setNodeHealth),
      loadWithRetry("/cluster/metrics", "metrics", setClusterMetrics),
      loadWithRetry("/cluster/scheduler", "scheduler", setScheduler),
    ]);
    setLoading(false);
    setBusy(false);
  }, []);

  useEffect(() => {
    if (token) refresh(token);
  }, [token, refresh]);

  const run = async (path, setter) => {
    setBusy(true);
    setError(null);
    try {
      const r = await plat(path, { method: "POST", token });
      setter(r[Object.keys(r)[0]] || r);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-stack" style={{ maxWidth: 960, margin: "0 auto", padding: "1.5rem" }}>
      <Heading level={1}>Operator console</Heading>
      <Text tone="muted" data-testid="ops-banner">
        Private-alpha operations · read-only except already-approved operations · LOCAL OR
        TEST ENVIRONMENT · NON-PRODUCTION · CONNECTOR MUTATIONS DRY-RUN · FINANCIAL EXECUTION
        DISABLED · TRADING DISABLED
      </Text>

      {loading && (
        <div data-testid="ops-loading">
          <LoadingState label="Loading operator console…" />
        </div>
      )}
      {!loading && error && <ErrorState title="Console notice" message={error} />}
      {!loading && busy && <LoadingState label="Working…" />}
      {!token && <Text tone="muted">Sign in on the Platform page first.</Text>}

      <Card>
        <Heading level={2}>Platform health</Heading>
        {health ? (
          <div data-testid="ops-health" style={{ display: "grid", gap: 6 }}>
            <StatusBadge status={statusTone(health.runtime_health)}>
              Runtime {health.runtime_health}
            </StatusBadge>
            <Text tone="muted">Runtime {health.runtime_health}</Text>
            <Text tone="muted">
              Uptime {Math.round(health.uptime_seconds)}s · DB {health.database_status} · Latency{" "}
              {health.api_latency_ms}ms · Sessions {health.active_sessions} · Tenants{" "}
              {health.tenant_counts} · Workspaces {health.workspace_counts}
            </Text>
            <Text tone="muted">
              Queue {health.queue_depth} · Waiting {health.waiting_executions} · Failed{" "}
              {health.failed_executions} · Recovered {health.recovered_executions} · Production
              authorized {String(health.production_authorized)}
            </Text>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {safetyBadges({ safety: health.safety }).map((b) => (
                <Text key={b.key} tone="muted">
                  {b.label}
                </Text>
              ))}
            </div>
          </div>
        ) : (
          <Text tone="muted">No health data</Text>
        )}
      </Card>

      <Card>
        <Heading level={2}>Metrics</Heading>
        {metrics ? (
          <Text data-testid="ops-metrics" tone="muted">
            Executions {metrics.execution_totals} · Approvals {metrics.approval_counts} · Exports{" "}
            {metrics.evidence_exports} · Retention previews {metrics.retention_previews} · Recovery
            ops {metrics.recovery_operations} · Restart count {String(metrics.restart_count)}
          </Text>
        ) : (
          <Text tone="muted">No metrics</Text>
        )}
      </Card>

      <Card>
        <Heading level={2}>Release readiness</Heading>
        <Button data-testid="run-release" onClick={() => run("/release/validate", setRelease)}>
          Run release validation
        </Button>
        {release && (
          <div data-testid="ops-release" style={{ marginTop: 10, display: "grid", gap: 6 }}>
            <StatusBadge status={statusTone(release.overall)}>
              {release.overall} · score {release.readiness_score}
            </StatusBadge>
            <Text tone="muted">
              Overall {release.overall} · score {release.readiness_score}
            </Text>
            <Text tone="muted">
              PASS {release.summary?.PASS || 0} · WARNING {release.summary?.WARNING || 0} · FAIL{" "}
              {release.summary?.FAIL || 0} · production authorized{" "}
              {String(release.production_authorized)}
            </Text>
          </div>
        )}
      </Card>

      <Card>
        <Heading level={2}>Recovery certification</Heading>
        <Button
          data-testid="run-recovery"
          variant="secondary"
          onClick={() => run("/release/recovery", setRecovery)}
        >
          Certify recovery
        </Button>
        {recovery && (
          <Text data-testid="ops-recovery" tone="muted" style={{ display: "block", marginTop: 8 }}>
            {recovery.overall} · scenarios{" "}
            {(recovery.scenarios || []).map((s) => `${s.scenario}:${s.status}`).join(" · ")}
          </Text>
        )}
      </Card>

      <Card>
        <Heading level={2}>Backup validation</Heading>
        <Button
          data-testid="run-backup"
          variant="secondary"
          onClick={() => run("/release/backup", setBackup)}
        >
          Validate backup (simulation)
        </Button>
        {backup && (
          <Text data-testid="ops-backup" tone="muted" style={{ display: "block", marginTop: 8 }}>
            {backup.mode} · integrity {backup.integrity_check} · restore{" "}
            {backup.restore_simulation} · destructive {String(backup.destructive_restore)}
          </Text>
        )}
      </Card>

      <Card>
        <Heading level={2}>Cluster & topology</Heading>
        {topology ? (
          <Text data-testid="ops-topology" tone="muted">
            Runtime {topology.runtime_status} · nodes {topology.cluster?.nodes} · workers{" "}
            {topology.cluster?.workers} · active leases {topology.queue_status?.active_leases} ·
            ownership {topology.execution_ownership} · logical clock {topology.logical_clock} ·
            runtime {topology.canonical_runtime} · authority {topology.registered_tool_authority}
          </Text>
        ) : (
          <Text tone="muted">No topology</Text>
        )}
      </Card>

      <Card>
        <Heading level={2}>Node & worker health</Heading>
        {nodeHealth ? (
          <div data-testid="ops-nodehealth" style={{ display: "grid", gap: 4 }}>
            {Object.values(nodeHealth.nodes || {}).map((n) => (
              <Text key={n.node_id} tone="muted">
                Node {n.node_id} · {n.status} · healthy {String(n.healthy)} · workers{" "}
                {n.worker_count} · leases {n.lease_count} · heartbeat age{" "}
                {Math.round(n.heartbeat_age_seconds)}s · restarts {n.restart_count}
              </Text>
            ))}
          </div>
        ) : (
          <Text tone="muted">No node health</Text>
        )}
      </Card>

      <Card>
        <Heading level={2}>Leases, scheduler & distributed metrics</Heading>
        {scheduler && (
          <Text data-testid="ops-scheduler" tone="muted" style={{ display: "block" }}>
            Scheduler paused {String(scheduler.paused)} · pending {scheduler.pending} · mode{" "}
            {scheduler.execution_mode} · fair {scheduler.fair_scheduling}
          </Text>
        )}
        {clusterMetrics && (
          <Text data-testid="ops-cluster-metrics" tone="muted" style={{ display: "block", marginTop: 6 }}>
            Active leases {clusterMetrics.per_lease?.active} · ownership{" "}
            {clusterMetrics.execution_ownership} · worker utilization{" "}
            {clusterMetrics.worker_utilization} · lease churn {clusterMetrics.lease_churn} · queue
            latency {clusterMetrics.queue_latency_seconds}s
          </Text>
        )}
      </Card>

      <Card>
        <Heading level={2}>Runtime ownership & recovery timeline</Heading>
        <Button
          data-testid="run-cluster-recovery"
          variant="secondary"
          onClick={() => run("/cluster/recovery", setClusterRecovery)}
        >
          Certify cluster recovery
        </Button>
        {clusterRecovery && (
          <Text data-testid="ops-cluster-recovery" tone="muted" style={{ display: "block", marginTop: 8 }}>
            {clusterRecovery.overall} · invariants{" "}
            {(clusterRecovery.invariants || []).join(", ")} ·{" "}
            {(clusterRecovery.scenarios || []).map((s) => `${s.scenario}:${s.status}`).join(" · ")}
          </Text>
        )}
      </Card>

      <Card>
        <Heading level={2}>Security status</Heading>
        <Text data-testid="ops-security" tone="muted">
          RBAC fail-closed · tenant isolation enforced · approval single-use · uncertain dispatch
          non-replay · single-owner leases · connectors DRY_RUN_ONLY · financial/trading DISABLED ·
          Trading Guardian UNENGAGED_ADVISORY_ONLY · production NOT AUTHORIZED
        </Text>
      </Card>
    </div>
  );
}
