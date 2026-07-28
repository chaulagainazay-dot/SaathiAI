"use client";
// M62.8 — Safety workspace: breaker definitions, states, trips, sweeps, alerts, and
// the acknowledge → request-reset → approval → execute-reset workflow. Every mutation
// routes through the authenticated API → Runtime → ExecutionGateway. Acknowledgement
// never resets a breaker; approval never overrides failing technical checks.
import { useState } from "react";
import { Card, Heading, Text, Button, Input } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, DataTable, StateChip, Loading, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe, useResource, fetchers, actions, fmtTs, shortHash, PERM, hasPerm } from "@/lib/trading";

const RESET_PREREQS = [
  "Operator acknowledgement exists",
  "Fresh reconciliation passes (no CRITICAL drift)",
  "Accounting invariants hold",
  "Market-data source healthy",
  "Triggering threshold no longer breached",
  "No broader breaker still blocking the scope",
  "Valid, unexpired, single-use, payload-matched approval",
  "Breaker version matches the request",
];

export default function SafetyPage() {
  const { token, perms, ready } = useAuthMe();
  const states = useResource(() => (token ? fetchers.states(token).then((r) => r?.states || []) : Promise.resolve([])), [token]);
  const trips = useResource(() => (token ? fetchers.trips(token).then((r) => r?.trips || []) : Promise.resolve([])), [token]);
  const sweeps = useResource(() => (token ? fetchers.sweeps(token).then((r) => r?.sweeps || []) : Promise.resolve([])), [token]);
  const alerts = useResource(() => (token ? fetchers.alerts(token).then((r) => r?.alerts || []) : Promise.resolve([])), [token]);
  const breakers = useResource(() => (token ? fetchers.breakers(token).then((r) => r?.breakers || []) : Promise.resolve([])), [token]);
  const [sel, setSel] = useState(null);

  const reloadAll = async () => { await Promise.all([states.reload(), trips.reload(), alerts.reload()]); };
  const blocking = (states.data || []).filter((s) => s.blocking).length;

  return (
    <div className="page shell-page">
      <TradingHeader title="Safety" severity={blocking ? "danger" : "ok"}
        subtitle="Circuit breakers, sweeps, alerts, and the fail-closed reset workflow (M62.7)." />
      <TradingTabs />
      <SignInGate ready={ready} token={token}>
        <SafetyBanner severity={blocking ? "danger" : "ok"} />
        <SweepRunner token={token} perms={perms} onDone={() => sweeps.reload()} />

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: 12, alignItems: "start" }}>
          <Card>
            <Heading level={3} size="sm">Breaker states</Heading>
            {states.loading ? <Loading /> : null}
            <LoadError error={states.error} />
            <DataTable
              testId="breaker-states"
              columns={[
                { key: "state", label: "State", render: (r) => <StateChip state={r.state} /> },
                { key: "scope", label: "Scope" },
                { key: "scope_ref", label: "Ref" },
                { key: "trip_count", label: "Trips", align: "right" },
              ]}
              rows={(states.data || []).filter((s) => s.state !== "NORMAL").concat((states.data || []).filter((s) => s.state === "NORMAL"))}
              getKey={(r) => r.definition_id} empty="No breaker states" />
          </Card>

          <Card>
            <Heading level={3} size="sm">Active trips</Heading>
            {trips.loading ? <Loading /> : null}
            <DataTable
              testId="trips-table"
              columns={[
                { key: "severity", label: "Sev", render: (r) => <StateChip state={r.severity} /> },
                { key: "breaker_type", label: "Type" },
                { key: "scope", label: "Scope" },
                { key: "scope_ref", label: "Ref" },
                { key: "ts", label: "When", render: (r) => fmtTs(r.ts) },
              ]}
              rows={trips.data || []} getKey={(r) => r.trip_id} onRow={(r) => setSel(r)} empty="No trips" />
          </Card>
        </div>

        {sel ? <ResetWorkflow token={token} perms={perms} trip={sel} onClose={() => setSel(null)} onChange={reloadAll} /> : null}

        <Card style={{ marginTop: 12 }}>
          <Heading level={3} size="sm">Alerts</Heading>
          {alerts.loading ? <Loading /> : null}
          <DataTable
            testId="alerts-table"
            columns={[
              { key: "level", label: "Level", render: (r) => <StateChip state={r.level} /> },
              { key: "breaker_type", label: "Type" },
              { key: "scope", label: "Scope" },
              { key: "acknowledged", label: "Acked", render: (r) => (r.acknowledged ? "yes" : "no") },
              { key: "ts", label: "When", render: (r) => fmtTs(r.ts) },
            ]}
            rows={alerts.data || []} getKey={(r) => r.alert_id} empty="No alerts" />
        </Card>

        <Card style={{ marginTop: 12 }}>
          <Heading level={3} size="sm">Safety sweeps</Heading>
          <DataTable
            testId="sweeps-table"
            columns={[
              { key: "status", label: "Status" },
              { key: "started_at", label: "Started", render: (r) => fmtTs(r.started_at) },
              { key: "completed_at", label: "Completed", render: (r) => fmtTs(r.completed_at) },
              { key: "result_hash", label: "Result hash", render: (r) => shortHash(r.result_hash, 12) },
            ]}
            rows={sweeps.data || []} getKey={(r) => r.sweep_id} empty="No sweeps" />
        </Card>

        <Card style={{ marginTop: 12 }}>
          <Heading level={3} size="sm">Breaker definitions</Heading>
          <DataTable
            testId="breakers-table"
            columns={[
              { key: "breaker_type", label: "Type" },
              { key: "scope", label: "Scope" },
              { key: "threshold", label: "Threshold", align: "right" },
              { key: "open_order_policy", label: "Open-order policy" },
              { key: "enabled", label: "Enabled", render: (r) => (r.enabled ? "yes" : "no") },
            ]}
            rows={breakers.data || []} getKey={(r) => r.id} empty="No breaker definitions" />
        </Card>
      </SignInGate>
    </div>
  );
}

function SweepRunner({ token, perms, onDone }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  if (!hasPerm(perms, PERM.SWEEP)) return null;
  const run = async () => {
    if (busy) return;
    setBusy(true); setMsg(null);
    try { const r = await actions.runSweep(token); await onDone(); setMsg(`Sweep ${r?.result?.sweep_id || "done"} — ${r?.result?.trips_created ?? 0} trips.`); }
    catch (e) { setMsg(`Sweep failed: ${e?.status || ""} ${e?.message || e}`); }
    finally { setBusy(false); }
  };
  return (
    <div style={{ marginBottom: 12, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
      <Button onClick={run} disabled={busy} data-testid="safety-run-sweep">{busy ? "Running…" : "Run on-demand sweep"}</Button>
      {msg ? <span role="status" className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>{msg}</span> : null}
    </div>
  );
}

function ResetWorkflow({ token, perms, trip, onClose, onChange }) {
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [approvalId, setApprovalId] = useState("");
  const [requestId, setRequestId] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [decision, setDecision] = useState(null);

  const call = async (fn) => { setBusy(true); setMsg(null); try { return await fn(); } finally { setBusy(false); } };

  const doAck = () => call(async () => {
    try { await actions.acknowledge(token, trip.trip_id, note || "reviewed", true); setMsg("Acknowledged. The halt remains active."); await onChange(); }
    catch (e) { setMsg(`Acknowledge failed: ${e?.status || ""} ${e?.message || e}`); }
  });
  const doRequest = () => call(async () => {
    try { const r = await actions.requestReset(token, trip.trip_id, reason || "operator reset", approvalId, `reset:${trip.trip_id}`);
      setRequestId(r?.result?.request_id || r?.request_id || ""); setMsg("Reset requested. Awaiting execution."); await onChange(); }
    catch (e) { setMsg(`Reset request failed: ${e?.status || ""} ${e?.message || e}`); }
  });
  const doExecute = () => call(async () => {
    try { const r = await actions.executeReset(token, requestId, approvalId);
      const res = r?.result || r; setDecision(res); setMsg(res?.allowed ? "Reset succeeded — server checks passed." : "Reset DENIED — technical checks failed."); await onChange(); }
    catch (e) { setMsg(`Reset execute failed: ${e?.status || ""} ${e?.message || e}`); }
  });

  const canAck = hasPerm(perms, PERM.ACK);
  const canReq = hasPerm(perms, PERM.RESET_REQUEST);
  const canReset = hasPerm(perms, PERM.RESET);

  return (
    <Card style={{ marginTop: 12, borderColor: "color-mix(in srgb,#5B8CFF 35%,transparent)" }} data-testid="reset-workflow">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Heading level={3} size="sm">Reset workflow · {trip.breaker_type} @ {trip.scope}:{trip.scope_ref || "—"}</Heading>
        <button onClick={onClose} aria-label="Close" style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 18 }}>×</button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: 16, marginTop: 8 }}>
        <div>
          <Text tone="muted" size="xs" mono>Trip evidence</Text>
          <dl style={dl}>
            <Row k="Trip" v={trip.trip_id} />
            <Row k="Threshold" v={trip.threshold} />
            <Row k="Reasons" v={(trip.reason_codes || []).join(", ") || "—"} />
            <Row k="Open-order policy" v={trip.open_order_policy} />
            <Row k="Recon run" v={trip.reconciliation_run_id || "—"} />
            <Row k="Trip hash" v={shortHash(trip.trip_hash, 14)} />
          </dl>
        </div>
        <div>
          <Text tone="muted" size="xs" mono>Reset prerequisites (server-enforced)</Text>
          <ul style={{ margin: "6px 0 0", paddingLeft: 16, fontSize: 12, color: "var(--text-secondary)" }}>
            {RESET_PREREQS.map((p) => <li key={p} style={{ marginBottom: 2 }}>{p}</li>)}
          </ul>
          <Text size="xs" as="p" style={{ marginTop: 8, color: "#F5A623" }}>
            Human approval cannot override failing technical checks. Approval alone is never sufficient.
          </Text>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 12, marginTop: 12 }}>
        <div>
          <Text tone="muted" size="xs" mono>1 · Acknowledge (halt retained)</Text>
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Operator note" aria-label="Acknowledge note" style={{ marginTop: 4 }} />
          <Button onClick={doAck} disabled={busy || !canAck} data-testid="ack-btn" style={{ marginTop: 6 }}>Acknowledge</Button>
          {!canAck ? <Perm /> : null}
        </div>
        <div>
          <Text tone="muted" size="xs" mono>2 · Request reset</Text>
          <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reset reason" aria-label="Reset reason" style={{ marginTop: 4 }} />
          <Input value={approvalId} onChange={(e) => setApprovalId(e.target.value)} placeholder="Approval ID (from Approval Center)" aria-label="Approval ID" style={{ marginTop: 4 }} />
          <Button onClick={doRequest} disabled={busy || !canReq} data-testid="request-reset-btn" style={{ marginTop: 6 }}>Request reset</Button>
          {!canReq ? <Perm /> : null}
        </div>
        <div>
          <Text tone="muted" size="xs" mono>3 · Execute reset (server re-checks)</Text>
          <Input value={requestId} onChange={(e) => setRequestId(e.target.value)} placeholder="Reset request ID" aria-label="Request ID" style={{ marginTop: 4 }} />
          <Button onClick={doExecute} disabled={busy || !canReset || !requestId} data-testid="execute-reset-btn" style={{ marginTop: 6 }}>Execute reset</Button>
          {!canReset ? <Perm /> : null}
        </div>
      </div>

      {msg ? <div role="status" data-testid="reset-msg" className="mono" style={{ fontSize: 12, marginTop: 10, color: decision && !decision.allowed ? "#FF5A5A" : "var(--text-secondary)" }}>{msg}</div> : null}
      {decision?.decision?.checks ? (
        <div style={{ marginTop: 8 }}>
          <Text tone="muted" size="xs" mono>Server decision checks</Text>
          <DataTable
            columns={[
              { key: "check", label: "Check" },
              { key: "ok", label: "OK", render: (r) => (r.ok ? "✓" : "✗") },
              { key: "detail", label: "Detail", wrap: true },
            ]}
            rows={decision.decision.checks} getKey={(r) => r.check} empty="—" />
        </div>
      ) : null}
    </Card>
  );
}

const dl = { display: "grid", gap: 4, marginTop: 6, fontSize: 12.5 };
function Row({ k, v }) {
  return <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><dt style={{ color: "var(--text-muted)" }}>{k}</dt><dd className="mono" style={{ color: "var(--text-secondary)", textAlign: "right", wordBreak: "break-all" }}>{v}</dd></div>;
}
function Perm() { return <div style={{ fontSize: 10.5, color: "#8FA0C4", marginTop: 3 }}>Not permitted for your role</div>; }
