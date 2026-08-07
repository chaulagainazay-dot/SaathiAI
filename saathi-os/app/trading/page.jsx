"use client";
// M62.8 — Trading Operator Workspace · Overview.
// Real M62.5–M62.7 backend data via the authenticated platform API. Replaces the
// M54 advisory-only placeholder. Paper execution IS available; live execution is not.
import Link from "next/link";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, StatCard, Loading, LoadError }
  from "@/components/trading/TradingShell";
import { useTradingOverview, fmtMoney, fmtTs, PERM, hasPerm, actions } from "@/lib/trading";
import { useState } from "react";

function overallSeverity(s) {
  if (s.halted > 0 || s.critDrift > 0 || s.blockingBreakers > 0) return "danger";
  if (s.unackAlerts > 0) return "warn";
  return "ok";
}

export default function TradingOverviewPage() {
  const d = useTradingOverview();
  const s = d.summary;
  const sev = overallSeverity(s);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const runSweep = async () => {
    if (busy) return;
    setBusy(true); setMsg(null);
    try {
      await actions.runSweep(d.token);
      await d.refresh(d.token);
      setMsg("Sweep completed — refreshed from server.");
    } catch (e) {
      setMsg(`Sweep failed: ${e?.status || ""} ${e?.message || e}`);
    } finally { setBusy(false); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Trading Operator Workspace"
        subtitle="Bounded paper-trading operations backed by the canonical M62 services. Simulation-only, long-only, localhost-only. Live execution unavailable."
        severity={sev}
        right={
          hasPerm(d.perms, PERM.SWEEP) ? (
            <Button onClick={runSweep} disabled={busy} aria-busy={busy} data-testid="run-sweep">
              {busy ? "Running…" : "Run safety sweep"}
            </Button>
          ) : null
        } />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner severity={sev} />
        {d.loading ? <Loading /> : null}
        <LoadError error={d.error} />
        {msg ? <div role="status" className="mono" style={{ fontSize: 12, marginBottom: 12, color: "var(--text-secondary)" }}>{msg}</div> : null}

        {/* Environment / authority strip */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="env-paper" style={pill("#10C98A")}>ENVIRONMENT: PAPER</span>
          <span className="mono" style={pill("#5B8CFF")}>AUTHORITY: SIMULATION ONLY</span>
          <span className="mono" style={pill("#8FA0C4")}>LIVE EXECUTION: UNAVAILABLE</span>
          <span className="mono" style={pill(sev === "ok" ? "#10C98A" : sev === "warn" ? "#F5A623" : "#FF5A5A")}>
            POSTURE: {sev === "ok" ? "HEALTHY" : sev === "warn" ? "ATTENTION" : "ACTION REQUIRED"}
          </span>
        </div>

        {/* Operational metrics */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
          <StatCard label="Paper accounts" value={s.accounts} hint={`${s.active} active · ${s.halted} halted`} tone={s.halted ? "danger" : "idle"} />
          <StatCard label="Total cash" value={fmtMoney(s.cash)} />
          <StatCard label="Total equity" value={fmtMoney(s.equity)} />
          <StatCard label="Reserved cash" value={fmtMoney(s.reserved)} />
          <StatCard label="Breakers" value={s.breakerCount} hint={`${s.blockingBreakers} blocking`} tone={s.blockingBreakers ? "danger" : "ok"} />
          <StatCard label="Trips" value={s.trips} tone={s.trips ? "warn" : "idle"} />
          <StatCard label="Unacked alerts" value={s.unackAlerts} tone={s.unackAlerts ? "warn" : "ok"} />
          <StatCard label="Critical drift" value={s.critDrift} tone={s.critDrift ? "danger" : "ok"} />
        </div>

        {/* Latest posture cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 12, marginTop: 12 }}>
          <Card>
            <Heading level={3} size="sm">Latest safety sweep</Heading>
            {s.latestSweep ? (
              <dl style={dl}>
                <Row k="Sweep" v={s.latestSweep.sweep_id} mono />
                <Row k="Status" v={s.latestSweep.status} />
                <Row k="Result hash" v={s.latestSweep.result_hash?.slice(0, 12) || "—"} mono />
                <Row k="Completed" v={fmtTs(s.latestSweep.completed_at)} />
              </dl>
            ) : <Text tone="muted" size="sm" as="p">No sweep recorded yet.</Text>}
            <Link href="/trading/safety" className="mono" style={linkS}>Open Safety →</Link>
          </Card>
          <Card>
            <Heading level={3} size="sm">Latest reconciliation</Heading>
            {s.latestRecon ? (
              <dl style={dl}>
                <Row k="Run" v={s.latestRecon.run_id} mono />
                <Row k="Account" v={s.latestRecon.account_id} mono />
                <Row k="Severity" v={s.latestRecon.severity_max} tone={s.latestRecon.severity_max === "CRITICAL" ? "danger" : "ok"} />
                <Row k="Halted" v={s.latestRecon.halted ? "yes" : "no"} />
              </dl>
            ) : <Text tone="muted" size="sm" as="p">No reconciliation run yet.</Text>}
            <Link href="/trading/reconciliation" className="mono" style={linkS}>Open Reconciliation →</Link>
          </Card>
          <Card>
            <Heading level={3} size="sm">Market data</Heading>
            <Text tone="muted" size="sm" as="p">
              Marks derive from fixture / replay data (position average cost). No approved live feed is wired.
            </Text>
            <span className="mono" style={pill("#8FA0C4")}>REPLAY / FIXTURE DATA</span>
          </Card>
        </div>
      </SignInGate>
    </div>
  );
}

const dl = { display: "grid", gap: 4, marginTop: 8, fontSize: 12.5 };
const linkS = { display: "inline-block", marginTop: 10, fontSize: 12, color: "#5B8CFF", textDecoration: "none" };
function pill(color) {
  return { fontSize: 11, letterSpacing: 0.5, color, border: `1px solid color-mix(in srgb, ${color} 45%, transparent)`,
    background: `color-mix(in srgb, ${color} 10%, transparent)`, borderRadius: 6, padding: "3px 9px" };
}
function Row({ k, v, mono, tone }) {
  const color = tone === "danger" ? "#FF5A5A" : tone === "ok" ? "#10C98A" : "var(--text-secondary)";
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
      <dt style={{ color: "var(--text-muted)" }}>{k}</dt>
      <dd className={mono ? "mono" : ""} style={{ color, textAlign: "right" }}>{v}</dd>
    </div>
  );
}
