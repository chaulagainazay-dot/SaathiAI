"use client";

import { useCallback, useEffect, useState } from "react";
import { fleetActions, healthTone, safeToken, trustTone } from "@/lib/fleet";

const toneColor = {
  ok: "#10C98A",
  warn: "#E8B84B",
  bad: "#FF5A5A",
  muted: "#8B98B4",
};

const DEFAULT_CAPS = ["planning", "analysis", "testing", "platform-agent-runtime"];

export default function FleetWorkspace() {
  const [token, setToken] = useState("");
  const [health, setHealth] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [workers, setWorkers] = useState([]);
  const [leases, setLeases] = useState([]);
  const [decisions, setDecisions] = useState([]);
  const [recons, setRecons] = useState([]);
  const [active, setActive] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mobile, setMobile] = useState(false);

  useEffect(() => {
    setToken(safeToken());
    const mq = window.matchMedia("(max-width: 720px)");
    const apply = () => setMobile(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  const refresh = useCallback(async () => {
    const t = safeToken() || token;
    if (!t) return;
    setError("");
    try {
      const [h, m, w, l, s, r] = await Promise.all([
        fleetActions.health(t),
        fleetActions.metrics(t),
        fleetActions.listWorkers(t),
        fleetActions.listLeases(t),
        fleetActions.schedule(t),
        fleetActions.reconciliations(t),
      ]);
      setHealth(h.health || null);
      setMetrics(m.metrics || null);
      setWorkers(w.workers || []);
      setLeases(l.leases || []);
      setDecisions(s.decisions || []);
      setRecons(r.reconciliations || []);
    } catch (e) {
      setError(e.message || "Failed to load fleet");
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    refresh();
  }, [token, refresh]);

  async function registerDemoWorkers() {
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      await fleetActions.registerWorker(token, {
        worker_id: "wrk_loop_a",
        protocol_version: "fleet.v1",
        runtime_version: "m103.fleet.v1",
        process_instance_id: `proc-a-${Date.now()}`,
        capability_set: DEFAULT_CAPS,
        bind_host: "127.0.0.1",
      });
      await fleetActions.registerWorker(token, {
        worker_id: "wrk_loop_b",
        protocol_version: "fleet.v1",
        runtime_version: "m103.fleet.v1",
        process_instance_id: `proc-b-${Date.now()}`,
        capability_set: [...DEFAULT_CAPS, "coding"],
        bind_host: "127.0.0.1",
      });
      await refresh();
    } catch (e) {
      setError(e.message || "Register failed");
    } finally {
      setBusy(false);
    }
  }

  async function openWorker(id) {
    if (!token) return;
    setBusy(true);
    try {
      const data = await fleetActions.getWorker(token, id);
      setActive(data);
    } catch (e) {
      setError(e.message || "Load worker failed");
    } finally {
      setBusy(false);
    }
  }

  async function runAction(action, workerId) {
    if (!token || !workerId) return;
    if (["quarantine", "revoke"].includes(action)) {
      if (!window.confirm(`${action} worker ${workerId}?`)) return;
    }
    setBusy(true);
    setError("");
    try {
      if (action === "drain") await fleetActions.drain(token, workerId);
      else if (action === "quarantine")
        await fleetActions.quarantine(token, workerId, "operator");
      else if (action === "revoke") await fleetActions.revoke(token, workerId);
      else if (action === "heartbeat")
        await fleetActions.heartbeat(token, workerId, { cpu_pressure: 5 });
      else if (action === "recover") await fleetActions.recover(token);
      await refresh();
      if (workerId) await openWorker(workerId);
    } catch (e) {
      setError(e.message || "Action failed");
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <div style={styles.wrap} data-fleet-panel="signed-out">
        <h1 style={styles.h1}>Fleet &amp; Workers</h1>
        <p style={styles.meta}>Sign in to manage the distributed worker fleet.</p>
        <p style={styles.meta}>
          Phase A only — loopback workers. Production and LAN not authorized.
        </p>
      </div>
    );
  }

  return (
    <div
      style={{ ...styles.wrap, ...(mobile ? styles.wrapMobile : {}) }}
      data-fleet-panel="active"
      aria-label="Fleet and workers"
    >
      <header style={styles.header}>
        <div>
          <h1 style={styles.h1}>Fleet &amp; Workers</h1>
          <p style={styles.meta} data-fleet-phase="PHASE_A_SINGLE_HOST">
            Extends M56 · Loopback Phase A · No public listeners · Production not
            authorized
          </p>
        </div>
        <div style={styles.actions}>
          <button
            type="button"
            style={styles.btn}
            onClick={refresh}
            disabled={busy}
            data-action="refresh"
          >
            Refresh
          </button>
          <button
            type="button"
            style={styles.btnPrimary}
            onClick={registerDemoWorkers}
            disabled={busy}
            data-action="register-workers"
          >
            Register loopback workers
          </button>
          <button
            type="button"
            style={styles.btn}
            onClick={() => runAction("recover", active?.worker?.worker_id || "")}
            disabled={busy}
            data-action="recover"
          >
            Recover lost
          </button>
        </div>
      </header>

      {error ? (
        <div role="alert" style={styles.error} data-fleet-error="true">
          {error}
        </div>
      ) : null}

      <section style={styles.grid} aria-label="Fleet overview" data-fleet-overview="true">
        <div style={styles.card}>
          <h2 style={styles.h2}>Overview</h2>
          {health ? (
            <ul style={styles.list} data-fleet-health="true">
              <li>Registered: {health.registered_workers}</li>
              <li>Active leases: {health.active_leases}</li>
              <li>Dispatch paused: {String(health.dispatch_paused)}</li>
              <li>Transport: {health.transport}</li>
              <li>Phase: {health.phase}</li>
              <li data-public-listener={String(health.public_listener)}>
                Public listener: {String(health.public_listener)}
              </li>
              <li data-production={String(health.production_authorized)}>
                Production: {String(health.production_authorized)}
              </li>
              <li>Direct tools: {String(health.direct_tool_execution)}</li>
            </ul>
          ) : (
            <p style={styles.meta}>Loading…</p>
          )}
          {metrics ? (
            <ul style={styles.list} data-fleet-metrics="true">
              <li>Trusted: {metrics.trusted_workers}</li>
              <li>Healthy: {metrics.healthy_workers}</li>
              <li>Quarantined: {metrics.quarantined_workers}</li>
              <li>Draining: {metrics.draining_workers}</li>
              <li>Stale rejections: {metrics.counters?.rejected_stale || 0}</li>
              <li>Duplicate rejections: {metrics.counters?.rejected_duplicate || 0}</li>
            </ul>
          ) : null}
        </div>

        <div style={styles.card}>
          <h2 style={styles.h2}>Workers</h2>
          <ul style={styles.list} data-worker-list="true">
            {workers.map((w) => (
              <li key={w.worker_id} style={{ marginBottom: 8 }}>
                <button
                  type="button"
                  style={styles.linkBtn}
                  onClick={() => openWorker(w.worker_id)}
                  data-worker-id={w.worker_id}
                  data-trust={w.trust_state}
                  data-health={w.health_state}
                >
                  <strong>{w.worker_id}</strong>
                </button>
                <span
                  style={{
                    ...styles.badge,
                    color: toneColor[trustTone(w.trust_state)],
                  }}
                >
                  {w.trust_state}
                </span>
                <span
                  style={{
                    ...styles.badge,
                    color: toneColor[healthTone(w.health_state)],
                  }}
                >
                  {w.health_state}
                </span>
                <div style={styles.meta}>
                  caps: {(w.capability_set || []).join(", ")} · leases:{" "}
                  {w.active_lease_count}
                </div>
              </li>
            ))}
            {!workers.length ? <li style={styles.meta}>No workers registered.</li> : null}
          </ul>
        </div>

        <div style={styles.card} aria-label="Worker detail" data-worker-detail="true">
          <h2 style={styles.h2}>Worker detail</h2>
          {active?.worker ? (
            <>
              <p data-active-worker={active.worker.worker_id}>
                <strong>{active.worker.worker_id}</strong>
              </p>
              <ul style={styles.list}>
                <li>Trust: {active.worker.trust_state}</li>
                <li>Health: {active.worker.health_state}</li>
                <li>Admission: {active.worker.admission_state}</li>
                <li>Bind: {active.worker.bind_host}</li>
                <li>Quarantine: {active.worker.quarantine_reason || "—"}</li>
                <li>Caps: {(active.worker.capability_set || []).join(", ")}</li>
              </ul>
              <div style={styles.actions}>
                <button
                  type="button"
                  style={styles.btn}
                  data-action="heartbeat"
                  onClick={() => runAction("heartbeat", active.worker.worker_id)}
                >
                  Heartbeat
                </button>
                <button
                  type="button"
                  style={styles.btn}
                  data-action="drain"
                  onClick={() => runAction("drain", active.worker.worker_id)}
                >
                  Drain
                </button>
                <button
                  type="button"
                  style={styles.btn}
                  data-action="quarantine"
                  onClick={() => runAction("quarantine", active.worker.worker_id)}
                >
                  Quarantine
                </button>
                <button
                  type="button"
                  style={styles.btn}
                  data-action="revoke"
                  onClick={() => runAction("revoke", active.worker.worker_id)}
                >
                  Revoke
                </button>
              </div>
              <h3 style={styles.h3}>Active leases</h3>
              <ul style={styles.list} data-active-leases="true">
                {(active.leases || []).slice(0, 8).map((l) => (
                  <li key={l.lease_id}>
                    {l.lease_id} · fence {l.fencing_token} · {l.state}
                  </li>
                ))}
                {!(active.leases || []).length ? (
                  <li style={styles.meta}>No leases.</li>
                ) : null}
              </ul>
            </>
          ) : (
            <p style={styles.meta}>Select a worker.</p>
          )}
        </div>
      </section>

      <section style={styles.grid} aria-label="Leases and reconciliation">
        <div style={styles.card}>
          <h2 style={styles.h2}>Leases</h2>
          <ul style={styles.list} data-lease-list="true">
            {leases.slice(0, 12).map((l) => (
              <li key={l.lease_id} data-lease-id={l.lease_id}>
                {l.work_node_id} → {l.worker_id} · fence {l.fencing_token} ·{" "}
                {l.state}/{l.completion_state}
                {l.active ? " · ACTIVE" : ""}
              </li>
            ))}
            {!leases.length ? <li style={styles.meta}>No leases.</li> : null}
          </ul>
        </div>
        <div style={styles.card}>
          <h2 style={styles.h2}>Scheduling decisions</h2>
          <ul style={styles.list} data-schedule-list="true">
            {decisions
              .slice()
              .reverse()
              .slice(0, 8)
              .map((d, i) => (
                <li key={`${d.work_node_id}-${i}`}>
                  {d.work_node_id}: {d.selected_worker_id || "—"} ({d.reason}) ·{" "}
                  {d.tie_breaking_rule}
                </li>
              ))}
            {!decisions.length ? (
              <li style={styles.meta}>No scheduling decisions yet.</li>
            ) : null}
          </ul>
        </div>
        <div style={styles.card}>
          <h2 style={styles.h2}>Reconciliation</h2>
          <ul style={styles.list} data-recon-list="true">
            {recons.slice(0, 10).map((r, i) => (
              <li
                key={`${r.lease_id}-${i}`}
                data-outcome={r.outcome}
                data-stale-result={String(String(r.outcome).includes("STALE"))}
              >
                {r.outcome} · {r.work_node_id || r.lease_id} · {r.reason}
              </li>
            ))}
            {!recons.length ? <li style={styles.meta}>No reconciliations.</li> : null}
          </ul>
        </div>
      </section>
    </div>
  );
}

const styles = {
  wrap: {
    maxWidth: 1100,
    margin: "0 auto",
    padding: "24px 16px 48px",
    color: "var(--text, #E8ECF4)",
    fontFamily: "var(--font-sans, system-ui, sans-serif)",
  },
  wrapMobile: { padding: "16px 12px 40px" },
  header: {
    display: "flex",
    flexWrap: "wrap",
    gap: 12,
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 16,
  },
  h1: { fontSize: 22, margin: "0 0 4px", fontWeight: 650 },
  h2: { fontSize: 15, margin: "0 0 10px", fontWeight: 600 },
  h3: { fontSize: 13, margin: "14px 0 6px", fontWeight: 600 },
  meta: { fontSize: 12, color: "var(--text-muted, #8B98B4)", margin: 0 },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
    gap: 12,
    marginBottom: 12,
  },
  card: {
    background: "var(--surface, rgba(255,255,255,0.04))",
    border: "1px solid var(--border, rgba(255,255,255,0.08))",
    borderRadius: 12,
    padding: 14,
  },
  list: { margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.5 },
  actions: { display: "flex", flexWrap: "wrap", gap: 8 },
  btn: {
    border: "1px solid var(--border, rgba(255,255,255,0.12))",
    background: "transparent",
    color: "inherit",
    borderRadius: 8,
    padding: "6px 10px",
    fontSize: 12,
    cursor: "pointer",
  },
  btnPrimary: {
    border: "1px solid #3E7BFF",
    background: "rgba(62,123,255,0.15)",
    color: "inherit",
    borderRadius: 8,
    padding: "6px 10px",
    fontSize: 12,
    cursor: "pointer",
  },
  linkBtn: {
    border: "none",
    background: "none",
    color: "#7CB8FF",
    cursor: "pointer",
    padding: 0,
    fontSize: 13,
    textAlign: "left",
  },
  badge: { marginLeft: 8, fontSize: 11, fontWeight: 600 },
  error: {
    background: "rgba(255,90,90,0.12)",
    border: "1px solid rgba(255,90,90,0.35)",
    borderRadius: 8,
    padding: "8px 12px",
    marginBottom: 12,
    fontSize: 13,
  },
};
