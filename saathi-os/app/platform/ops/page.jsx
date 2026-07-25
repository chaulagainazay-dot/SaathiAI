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
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) || "" : "";
    setToken(t);
  }, []);

  const refresh = useCallback(async (tok) => {
    if (!tok) return;
    setBusy(true);
    setError(null);
    try {
      const [h, m] = await Promise.all([
        plat("/release/health", { token: tok }),
        plat("/release/metrics", { token: tok }),
      ]);
      setHealth(h.health || null);
      setMetrics(m.metrics || null);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
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

      {error && <ErrorState title="Console error" message={error} />}
      {busy && <LoadingState label="Working…" />}
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
        <Heading level={2}>Security status</Heading>
        <Text data-testid="ops-security" tone="muted">
          RBAC fail-closed · tenant isolation enforced · approval single-use · uncertain dispatch
          non-replay · connectors DRY_RUN_ONLY · financial/trading DISABLED · Trading Guardian
          UNENGAGED_ADVISORY_ONLY · production NOT AUTHORIZED
        </Text>
      </Card>
    </div>
  );
}
