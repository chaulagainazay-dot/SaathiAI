"use client";
// M62.8 — Reconciliation workspace: run history, drift findings across 7 dimensions,
// and repair plans marked PLAN ONLY — NEVER AUTOMATICALLY EXECUTED. No apply/execute.
import { useState } from "react";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, DataTable, StateChip, Loading, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe, useResource, fetchers, actions, fmtTs, shortHash, PERM, hasPerm } from "@/lib/trading";

const DIMENSIONS = ["orders ↔ fills", "fills ↔ positions", "positions ↔ ledger", "ledger ↔ cash",
  "cash ↔ equity", "reservations ↔ balances", "audit ↔ runtime"];

export default function ReconciliationPage() {
  const { token, perms, ready } = useAuthMe();
  const runs = useResource(() => (token ? fetchers.reconRuns(token, "").then((r) => r?.runs || []) : Promise.resolve([])), [token]);
  const plans = useResource(() => (token ? fetchers.repairPlans(token, "").then((r) => r?.repair_plans || []) : Promise.resolve([])), [token]);
  const [sel, setSel] = useState(null);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const openRun = async (r) => {
    setSel(r.run_id); setDetail(null);
    try { setDetail((await fetchers.reconRun(token, r.run_id))?.run || null); }
    catch (e) { setMsg(String(e?.message || e)); }
  };

  const runReconcile = async () => {
    const accts = (await fetchers.accounts(token))?.accounts || [];
    if (!accts.length) { setMsg("No accounts to reconcile."); return; }
    setBusy(true); setMsg(null);
    try {
      for (const a of accts) await actions.reconcile(token, a.id);
      await runs.reload(); await plans.reload();
      setMsg("Reconciliation complete — refreshed from server.");
    } catch (e) { setMsg(`Reconcile failed: ${e?.status || ""} ${e?.message || e}`); }
    finally { setBusy(false); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Reconciliation" severity={(runs.data || []).some((r) => r.severity_max === "CRITICAL") ? "danger" : "ok"}
        subtitle="Independent integrity verification (M62.6). May halt an account; never executes a repair."
        right={hasPerm(perms, PERM.SWEEP) ? <Button onClick={runReconcile} disabled={busy} data-testid="run-reconcile">{busy ? "Reconciling…" : "Reconcile all"}</Button> : null} />
      <TradingTabs />
      <SignInGate ready={ready} token={token}>
        <SafetyBanner severity={(runs.data || []).some((r) => r.severity_max === "CRITICAL") ? "danger" : "ok"} />
        {msg ? <div role="status" className="mono" style={{ fontSize: 12, marginBottom: 12, color: "var(--text-secondary)" }}>{msg}</div> : null}
        {runs.loading ? <Loading /> : null}
        <LoadError error={runs.error} />

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1.2fr)", gap: 12, alignItems: "start" }}>
          <Card>
            <Heading level={3} size="sm">Run history</Heading>
            <DataTable
              testId="recon-runs"
              columns={[
                { key: "severity_max", label: "Severity", render: (r) => <StateChip state={r.severity_max} /> },
                { key: "account_id", label: "Account" },
                { key: "halted", label: "Halted", render: (r) => (r.halted ? "yes" : "no") },
                { key: "ts", label: "When", render: (r) => fmtTs(r.ts) },
              ]}
              rows={runs.data || []} getKey={(r) => r.run_id} onRow={openRun} empty="No reconciliation runs" />
          </Card>

          <Card>
            <Heading level={3} size="sm">Run detail {sel ? <span className="mono" style={{ fontSize: 11, color: "#8FA0C4" }}>{sel}</span> : null}</Heading>
            {!sel ? <Text tone="muted" size="sm" as="p">Select a run to inspect findings.</Text> : null}
            {sel && !detail ? <Loading /> : null}
            {detail ? (
              <>
                <dl style={dl}>
                  <Row k="Severity" v={detail.severity_max} />
                  <Row k="Clean" v={detail.clean ? "yes" : "no"} />
                  <Row k="Halted" v={detail.halted ? "yes" : "no"} />
                  <Row k="Result hash" v={shortHash(detail.report_hash, 16)} />
                  <Row k="Counts" v={JSON.stringify(detail.counts)} />
                </dl>
                <div style={{ display: "flex", gap: 5, flexWrap: "wrap", margin: "8px 0" }}>
                  {DIMENSIONS.map((dm) => <span key={dm} className="mono" style={dimTag}>{dm}</span>)}
                </div>
                <DataTable
                  columns={[
                    { key: "severity", label: "Sev", render: (r) => <StateChip state={r.severity} /> },
                    { key: "dimension", label: "Dimension" },
                    { key: "code", label: "Code" },
                    { key: "expected", label: "Expected" },
                    { key: "actual", label: "Actual" },
                  ]}
                  rows={detail.findings || []} getKey={(r, i) => `${r.code}-${i}`} empty="No findings" />
              </>
            ) : null}
          </Card>
        </div>

        <Card style={{ marginTop: 12 }}>
          <Heading level={3} size="sm">Repair plans
            <span className="mono" style={{ ...planTag, marginLeft: 8 }} data-testid="plan-only-badge">PLAN ONLY — NEVER AUTOMATICALLY EXECUTED</span>
          </Heading>
          <Text tone="muted" size="xs" as="p" style={{ marginTop: 4 }}>
            Repair plans are advisory metadata. There is no execute/apply control — corrective action is a manual, out-of-band operator process.
          </Text>
          <DataTable
            testId="repair-plans"
            columns={[
              { key: "finding_code", label: "Finding" },
              { key: "root_cause", label: "Root cause", wrap: true },
              { key: "status", label: "Status", render: (r) => <StateChip state={r.status} /> },
              { key: "executes_automatically", label: "Auto-exec", render: () => "NO" },
            ]}
            rows={plans.data || []} getKey={(r) => r.plan_id} empty="No repair plans" />
        </Card>
      </SignInGate>
    </div>
  );
}

const dl = { display: "grid", gap: 4, marginTop: 8, fontSize: 12.5 };
const dimTag = { fontSize: 10, color: "#8FA0C4", border: "1px solid #2a2f3a", borderRadius: 5, padding: "1px 6px" };
const planTag = { fontSize: 10, color: "#F5A623", border: "1px solid color-mix(in srgb,#F5A623 45%,transparent)", background: "color-mix(in srgb,#F5A623 10%,transparent)", borderRadius: 5, padding: "2px 7px" };
function Row({ k, v }) {
  return <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><dt style={{ color: "var(--text-muted)" }}>{k}</dt><dd className="mono" style={{ color: "var(--text-secondary)", textAlign: "right", wordBreak: "break-all" }}>{v}</dd></div>;
}
