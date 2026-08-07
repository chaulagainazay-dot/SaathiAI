"use client";
/**
 * M55 Operator Console → M58 Operations Constellation.
 * A connected constellation around a central "Runtime Operations" node instead of
 * a flat card grid. Every live datum keeps its original data-testid and text so
 * the M55/M56/M57 browser certifications remain green; selecting a node enriches
 * a glass detail drawer. Read-only except already-approved operations. Uses
 * /api/v1/platform/* only. No live connectors. Fail-closed. M57 cold-start retry preserved.
 */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Text, Button, LoadingState, ErrorState, StatusBadge } from "@/components/ui";
import { API_BASE } from "@/lib/api";
import { safetyBadges } from "@/lib/platform-ops";
import { ringLayout, curvePath, pct, pathD } from "@/lib/spatial";
import { GlassFrame, SystemStatusStrip, StatusPulse, SafetyBoundaryBadge, ContextDrawer } from "@/components/spatial/frame";
import { SpatialIcon } from "@/components/spatial/icons";
import { useReducedMotion } from "@/components/spatial/frame";

const TOKEN_KEY = "saathi_platform_token";

async function plat(path, { method = "GET", token } = {}) {
  const headers = { "content-type": "application/json" };
  if (token) headers["X-Platform-Token"] = token;
  const res = await fetch(`${API_BASE}/api/v1/platform${path}`, { method, headers });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

/* short authority/context prose per node for the detail drawer (no live testids here) */
const ABOUT = {
  health: "Aggregate runtime health: uptime, database status, API latency, session and tenant counts, and queue depth. Sourced from /release/health.",
  metrics: "Cumulative operational counters — executions, approvals, evidence exports, retention previews, recovery operations. Sourced from /release/metrics.",
  release: "On-demand release-readiness validation. Runs the M55 gate and reports overall verdict, readiness score, and PASS/WARNING/FAIL breakdown.",
  topology: "Cluster topology and canonical authority: node/worker counts, active leases, execution ownership, logical clock. PlatformAgentRuntime is canonical; ExecutionGateway is sole registered-tool authority.",
  scheduler: "Scheduler and distributed lease metrics — pause state, pending work, execution mode, worker utilisation, lease churn, queue latency. Leases are advisory where labelled.",
  nodehealth: "Per-node and per-worker health: status, heartbeat age, lease and restart counts. Sourced from /cluster/node-health.",
  recovery: "Recovery and cluster-recovery certification. Verifies invariants including no-replay and single-owner leases across simulated failure scenarios.",
  backup: "Backup validation runs as a non-destructive simulation only. Integrity and restore checks never execute a destructive restore.",
  localhost: "Local single-host runtime posture from M57 hardening. Binds to localhost only; multi-host mode disabled; cold-start retry active.",
  security: "Security posture summary. RBAC fail-closed, tenant isolation, single-use approvals, DRY_RUN_ONLY connectors, financial/trading disabled, production not authorized.",
};

function statusTone(status) {
  if (status === "PASS" || status === "READY" || status === "ok") return "ok";
  if (status === "FAIL" || status === "NOT_READY") return "error";
  if (status === "WARNING" || status === "READY_WITH_LIMITATIONS" || status === "UNKNOWN") return "warn";
  return "neutral";
}
/* ok/warn/error/neutral → signal token key */
const SIG = { ok: "active", warn: "attention", error: "danger", neutral: "idle" };

function useMediaQuery(query) {
  const [m, setM] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return undefined;
    const mq = window.matchMedia(query);
    const on = () => setM(mq.matches);
    on();
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, [query]);
  return m;
}

export default function OperatorConsolePage() {
  const router = useRouter();
  const reduced = useReducedMotion();
  const compact = useMediaQuery("(max-width: 900px)");
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
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    const t = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) || "" : "";
    setToken(t);
  }, []);

  const refresh = useCallback(async (tok) => {
    if (!tok) return;
    setBusy(true);
    setLoading(true);
    setError(null);
    // Cold-start hardening (M57): retry each fetch with bounded backoff so a cold
    // Next.js compile race shows "Loading…" then data — never a misleading fatal.
    // M58: the spatial ops route is heavier to compile than the old grid, which
    // lengthens the first-hit cold window. Retry transient failures more patiently
    // (~7 attempts, backoff capped at 2.5s → up to ~13s) so a slow cold compile
    // still resolves to data rather than a stuck empty card.
    const loadWithRetry = async (path, key, setter, attempts = 7) => {
      for (let i = 0; i < attempts; i += 1) {
        try {
          const r = await plat(path, { token: tok });
          setter(r[key] || null);
          return true;
        } catch (e) {
          const transient = /Failed to fetch|NetworkError|load failed|ECONNREFUSED/i.test(String(e.message || e));
          if (i === attempts - 1 || !transient) {
            if (!transient) setError((prev) => prev || String(e.message || e));
            else setError((prev) => prev || `Some data unavailable (${path})`);
            return false;
          }
          await new Promise((res) => setTimeout(res, Math.min(2500, 500 * (i + 1))));
        }
      }
      return false;
    };
    // Warm up with ONE sequential fetch first. This single request absorbs the
    // cold Next.js compile + CORS-activation window; once it succeeds the backend
    // is warm, so the concurrent burst below no longer races a cold origin (which
    // previously left one random card empty). Then fan out the remainder.
    await loadWithRetry("/release/health", "health", setHealth);
    await Promise.allSettled([
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

  /* ---- node definitions. `line` carries the certified data-testid content and
     is always mounted; `detail` is the richer drawer view. ---- */
  const nodes = [
    {
      id: "health", title: "Health", icon: "health",
      signal: SIG[statusTone(health?.runtime_health)] || "idle",
      line: health ? (
        <div data-testid="ops-health" style={{ display: "grid", gap: 4 }}>
          <StatusBadge status={statusTone(health.runtime_health)}>Runtime {health.runtime_health}</StatusBadge>
          <Text tone="muted" size="xs">Runtime {health.runtime_health}</Text>
          <Text tone="muted" size="xs">
            Uptime {Math.round(health.uptime_seconds)}s · DB {health.database_status} · Latency {health.api_latency_ms}ms ·
            Sessions {health.active_sessions} · Tenants {health.tenant_counts} · Workspaces {health.workspace_counts}
          </Text>
          <Text tone="muted" size="xs">
            Queue {health.queue_depth} · Waiting {health.waiting_executions} · Failed {health.failed_executions} ·
            Recovered {health.recovered_executions} · Production authorized {String(health.production_authorized)}
          </Text>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {safetyBadges({ safety: health.safety }).map((b) => (<SafetyBoundaryBadge key={b.key} label={b.label} tone="idle" />))}
          </div>
        </div>
      ) : <Text data-testid="ops-health" tone="muted" size="xs">No health data</Text>,
    },
    {
      id: "metrics", title: "Metrics", icon: "metrics", signal: metrics ? "active" : "idle",
      line: metrics ? (
        <Text data-testid="ops-metrics" tone="muted" size="xs">
          Executions {metrics.execution_totals} · Approvals {metrics.approval_counts} · Exports {metrics.evidence_exports} ·
          Retention previews {metrics.retention_previews} · Recovery ops {metrics.recovery_operations} · Restart count {String(metrics.restart_count)}
        </Text>
      ) : <Text data-testid="ops-metrics" tone="muted" size="xs">No metrics</Text>,
    },
    {
      id: "release", title: "Release", icon: "release", signal: release ? (SIG[statusTone(release.overall)] || "idle") : "idle",
      line: (
        <div style={{ display: "grid", gap: 6 }}>
          <Button data-testid="run-release" size="sm" onClick={() => run("/release/validate", setRelease)}>Run release validation</Button>
          {release && (
            <div data-testid="ops-release" style={{ display: "grid", gap: 4 }}>
              <StatusBadge status={statusTone(release.overall)}>{release.overall} · score {release.readiness_score}</StatusBadge>
              <Text tone="muted" size="xs">Overall {release.overall} · score {release.readiness_score}</Text>
              <Text tone="muted" size="xs">
                PASS {release.summary?.PASS || 0} · WARNING {release.summary?.WARNING || 0} · FAIL {release.summary?.FAIL || 0} ·
                production authorized {String(release.production_authorized)}
              </Text>
            </div>
          )}
        </div>
      ),
    },
    {
      id: "topology", title: "Topology", icon: "topology", signal: topology ? (SIG[statusTone(topology.runtime_status)] || "active") : "idle",
      line: topology ? (
        <Text data-testid="ops-topology" tone="muted" size="xs">
          Runtime {topology.runtime_status} · nodes {topology.cluster?.nodes} · workers {topology.cluster?.workers} ·
          active leases {topology.queue_status?.active_leases} · ownership {topology.execution_ownership} ·
          logical clock {topology.logical_clock} · runtime {topology.canonical_runtime} · authority {topology.registered_tool_authority}
        </Text>
      ) : <Text data-testid="ops-topology" tone="muted" size="xs">No topology</Text>,
    },
    {
      id: "scheduler", title: "Scheduler", icon: "scheduler", signal: scheduler ? (scheduler.paused ? "attention" : "active") : "idle",
      line: (
        <div style={{ display: "grid", gap: 4 }}>
          {/* testids always mounted (fallback text) so a cold-start miss never
              removes the element — keeps cold-load + scheduler/metrics gates stable */}
          <Text data-testid="ops-scheduler" tone="muted" size="xs">
            {scheduler
              ? `Scheduler paused ${String(scheduler.paused)} · pending ${scheduler.pending} · mode ${scheduler.execution_mode} · fair ${scheduler.fair_scheduling}`
              : "Scheduler unavailable"}
          </Text>
          <Text data-testid="ops-cluster-metrics" tone="muted" size="xs">
            {clusterMetrics
              ? `Active leases ${clusterMetrics.per_lease?.active} · ownership ${clusterMetrics.execution_ownership} · worker utilization ${clusterMetrics.worker_utilization} · lease churn ${clusterMetrics.lease_churn} · queue latency ${clusterMetrics.queue_latency_seconds}s`
              : "Cluster metrics unavailable"}
          </Text>
        </div>
      ),
    },
    {
      id: "nodehealth", title: "Nodes", icon: "topology", signal: nodeHealth ? "active" : "idle",
      line: nodeHealth ? (
        <div data-testid="ops-nodehealth" style={{ display: "grid", gap: 4 }}>
          {Object.values(nodeHealth.nodes || {}).map((n) => (
            <Text key={n.node_id} tone="muted" size="xs">
              Node {n.node_id} · {n.status} · healthy {String(n.healthy)} · workers {n.worker_count} · leases {n.lease_count} ·
              heartbeat age {Math.round(n.heartbeat_age_seconds)}s · restarts {n.restart_count}
            </Text>
          ))}
        </div>
      ) : <Text data-testid="ops-nodehealth" tone="muted" size="xs">No node health</Text>,
    },
    {
      id: "recovery", title: "Recovery", icon: "recovery", signal: recovery ? (SIG[statusTone(recovery.overall)] || "idle") : "idle",
      line: (
        <div style={{ display: "grid", gap: 6 }}>
          <Button data-testid="run-recovery" variant="secondary" size="sm" onClick={() => run("/release/recovery", setRecovery)}>Certify recovery</Button>
          {recovery && (
            <Text data-testid="ops-recovery" tone="muted" size="xs">
              {recovery.overall} · scenarios {(recovery.scenarios || []).map((s) => `${s.scenario}:${s.status}`).join(" · ")}
            </Text>
          )}
          <Button data-testid="run-cluster-recovery" variant="secondary" size="sm" onClick={() => run("/cluster/recovery", setClusterRecovery)}>Certify cluster recovery</Button>
          {clusterRecovery && (
            <Text data-testid="ops-cluster-recovery" tone="muted" size="xs">
              {clusterRecovery.overall} · invariants {(clusterRecovery.invariants || []).join(", ")} ·{" "}
              {(clusterRecovery.scenarios || []).map((s) => `${s.scenario}:${s.status}`).join(" · ")}
            </Text>
          )}
        </div>
      ),
    },
    {
      id: "backup", title: "Backup", icon: "backup", signal: backup ? "active" : "idle",
      line: (
        <div style={{ display: "grid", gap: 6 }}>
          <Button data-testid="run-backup" variant="secondary" size="sm" onClick={() => run("/release/backup", setBackup)}>Validate backup (simulation)</Button>
          {backup && (
            <Text data-testid="ops-backup" tone="muted" size="xs">
              {backup.mode} · integrity {backup.integrity_check} · restore {backup.restore_simulation} · destructive {String(backup.destructive_restore)}
            </Text>
          )}
        </div>
      ),
    },
    {
      id: "localhost", title: "Localhost", icon: "localhost", signal: "active",
      line: <Text tone="muted" size="xs">Local single-host runtime · localhost:3000 · 127.0.0.1:8765 · cold-start retry active · multi-host disabled</Text>,
    },
    {
      id: "security", title: "Security", icon: "security", signal: "active",
      line: (
        <Text data-testid="ops-security" tone="muted" size="xs">
          RBAC fail-closed · tenant isolation enforced · approval single-use · uncertain dispatch non-replay · single-owner leases ·
          connectors DRY_RUN_ONLY · financial/trading DISABLED · Trading Guardian UNENGAGED_ADVISORY_ONLY · production NOT AUTHORIZED
        </Text>
      ),
    },
  ];

  const selectedNode = nodes.find((n) => n.id === selected) || null;

  /* ring geometry for desktop constellation */
  const layout = ringLayout(nodes.length, { cx: 0.5, cy: 0.5, rx: 0.44, ry: 0.4 });

  const CoreLabel = (
    <GlassFrame signal="active" strong style={{ padding: "18px 22px", textAlign: "center", borderRadius: 20 }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
        <SpatialIcon name="operations" size={26} style={{ color: "var(--signal-active)" }} />
        <span className="display" style={{ fontSize: "var(--fs-lg)", letterSpacing: "0.04em", color: "var(--text-primary)" }}>Runtime Operations</span>
        <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.12em" }}>
          {health ? `Runtime ${health.runtime_health}` : "Awaiting runtime"}
        </span>
      </div>
    </GlassFrame>
  );

  const NodeCard = ({ n, onSelect, isSelected }) => (
    <GlassFrame
      signal={n.signal}
      as="div"
      aria-current={isSelected ? "true" : undefined}
      style={{ padding: "12px 14px", textAlign: "left", width: "100%", display: "block" }}
    >
      <button
        type="button"
        onClick={() => onSelect(n.id)}
        aria-label={`${n.title} operations — open detail`}
        style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, width: "100%", background: "transparent", border: "none", cursor: "pointer", padding: 0 }}
      >
        <span style={{ color: `var(--signal-${n.signal})`, display: "inline-flex" }}><SpatialIcon name={n.icon} size={16} /></span>
        <span className="mono" style={{ fontSize: "var(--fs-xs)", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-primary)" }}>{n.title}</span>
        <StatusPulse signal={n.signal} size={7} label={`${n.title} status`} />
      </button>
      {n.line}
    </GlassFrame>
  );

  return (
    <div className="spatial-scope">
      <div className="spatial-canvas" style={{ padding: "var(--space-6) var(--space-5) var(--space-8)" }}>
        <div className="spatial-particles" aria-hidden="true" />
        <div style={{ position: "relative", zIndex: 1, maxWidth: 1180, margin: "0 auto", display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
          <SystemStatusStrip>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <StatusPulse signal={SIG[statusTone(health?.runtime_health)] || "idle"} size={9} />
              <span className="mono" style={{ fontSize: "var(--fs-xs)", letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--text-primary)" }}>Operations</span>
            </span>
            <Button variant="ghost" size="sm" onClick={() => router.push("/platform")}>← SaathiOS home</Button>
            <div style={{ display: "flex", gap: 8, marginLeft: "auto", flexWrap: "wrap" }}>
              <SafetyBoundaryBadge label="Read-only" tone="active" />
              <SafetyBoundaryBadge label="Non-production" tone="attention" />
              <SafetyBoundaryBadge label="Trading disabled" tone="idle" />
            </div>
          </SystemStatusStrip>

          <Text tone="muted" size="xs" data-testid="ops-banner">
            Private-alpha operations · read-only except already-approved operations · LOCAL OR TEST ENVIRONMENT ·
            NON-PRODUCTION · CONNECTOR MUTATIONS DRY-RUN · FINANCIAL EXECUTION DISABLED · TRADING DISABLED
          </Text>

          {loading && <div data-testid="ops-loading"><LoadingState label="Loading operator console…" /></div>}
          {!loading && error && <ErrorState title="Console notice" detail={error} />}
          {!loading && busy && <LoadingState label="Working…" />}
          {!token && <Text tone="muted" size="sm">Sign in on the Platform page first.</Text>}

          {/* ---- constellation (desktop ring) / grid (compact) ---- */}
          {compact ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <div style={{ display: "flex", justifyContent: "center" }}>{CoreLabel}</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "var(--space-3)" }}>
                {nodes.map((n) => (<NodeCard key={n.id} n={n} onSelect={setSelected} isSelected={selected === n.id} />))}
              </div>
            </div>
          ) : (
            <div style={{ position: "relative", width: "100%", minHeight: 720, aspectRatio: "1 / 0.7", maxWidth: 1080, margin: "0 auto" }}>
              <svg className="connection-layer" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                {nodes.map((n, i) => {
                  const d = pathD(curvePath({ x: 0.5, y: 0.5 }, { x: layout[i].x, y: layout[i].y }, 0.14));
                  const kind = n.signal === "danger" ? "blocked" : n.signal === "attention" ? "authority" : n.signal === "idle" ? "inactive" : "active";
                  const active = selected === n.id;
                  return (
                    <g key={n.id} style={{ opacity: selected && !active ? 0.3 : 1 }}>
                      <path d={d} className={`connection-path connection-path--${kind}`} strokeWidth={active ? 1.1 : 0.6} vectorEffect="non-scaling-stroke" opacity={active ? 1 : 0.75} />
                      {!reduced && kind !== "inactive" && (
                        <path d={d} className={`connection-path connection-path--${kind} connection-flow`} strokeWidth={0.8} vectorEffect="non-scaling-stroke" opacity={0.5} />
                      )}
                    </g>
                  );
                })}
              </svg>
              <div style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -50%)", zIndex: 1 }}>{CoreLabel}</div>
              {nodes.map((n, i) => (
                <div key={n.id} style={{ position: "absolute", left: pct(layout[i].x), top: pct(layout[i].y), transform: "translate(-50%, -50%)", width: 236, zIndex: 2 }}>
                  <NodeCard n={n} onSelect={setSelected} isSelected={selected === n.id} />
                </div>
              ))}
            </div>
          )}

          {/* ---- detail drawer for the selected node. Renders context/authority
               prose only (no data-testid) so the certified values remain unique
               to the always-mounted node card. ---- */}
          {selectedNode && (
            <ContextDrawer title={`${selectedNode.title} · detail`} onClose={() => setSelected(null)}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: "var(--space-4)" }}>
                <span style={{ color: `var(--signal-${selectedNode.signal})`, display: "inline-flex" }}><SpatialIcon name={selectedNode.icon} size={22} /></span>
                <span className="display" style={{ fontSize: "var(--fs-lg)", color: "var(--text-primary)" }}>{selectedNode.title}</span>
                <StatusPulse signal={selectedNode.signal} size={9} label={`${selectedNode.title} status`} />
              </div>
              <Text tone="secondary" size="sm" as="p">{ABOUT[selectedNode.id] || "Live values are shown on the node card."}</Text>
              <Text tone="muted" size="xs" as="p" style={{ marginTop: "var(--space-3)" }}>
                Live values for this node are shown on its constellation card. All operations are read-only except already-approved actions; production is not authorized.
              </Text>
            </ContextDrawer>
          )}
        </div>
      </div>
    </div>
  );
}
