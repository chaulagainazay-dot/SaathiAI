"use client";
// M62.8 — Evidence & audit workspace. Read-only, aggregated from immutable backend
// records (trips, sweeps, reconciliation runs, repair plans, alerts, orders/fills).
// No mutation controls. No secrets/payloads/paths — only ids, hashes, correlation refs.
import { useMemo, useState } from "react";
import Link from "next/link";
import { Card, Heading, Text } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, DataTable, StateChip, Loading, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe, useResource, fetchers, fmtTs, shortHash } from "@/lib/trading";

const TYPES = ["all", "trip", "sweep", "reconciliation", "repair_plan", "alert", "order", "fill"];
const PAGE = 25;

export default function EvidencePage() {
  const { token, ready } = useAuthMe();
  const ev = useResource(async () => {
    if (!token) return [];
    const [tr, sw, rc, rp, al, od] = await Promise.all([
      fetchers.trips(token).then((r) => r?.trips || []).catch(() => []),
      fetchers.sweeps(token).then((r) => r?.sweeps || []).catch(() => []),
      fetchers.reconRuns(token, "").then((r) => r?.runs || []).catch(() => []),
      fetchers.repairPlans(token, "").then((r) => r?.repair_plans || []).catch(() => []),
      fetchers.alerts(token).then((r) => r?.alerts || []).catch(() => []),
      fetchers.orders(token, "").then((r) => r?.orders || []).catch(() => []),
    ]);
    const items = [];
    tr.forEach((t) => items.push(mk("trip", t.ts, t.trip_id, t.severity, t.scope_ref, t.trip_hash, t.correlation_id, { href: "/trading/safety", label: t.breaker_type, immutable: true })));
    sw.forEach((s) => items.push(mk("sweep", s.completed_at || s.started_at, s.sweep_id, "INFO", "", s.result_hash, "", { href: "/trading/safety", label: s.status, immutable: true })));
    rc.forEach((r) => items.push(mk("reconciliation", r.ts, r.run_id, r.severity_max, r.account_id, r.report_hash, "", { href: "/trading/reconciliation", label: r.halted ? "halted" : "ok", immutable: true })));
    rp.forEach((p) => items.push(mk("repair_plan", p.created_at, p.plan_id, "INFO", p.account_id, "", "", { href: "/trading/reconciliation", label: p.status, plan: true })));
    al.forEach((a) => items.push(mk("alert", a.ts, a.alert_id, a.level, a.scope_ref, "", a.correlation_id, { href: "/trading/safety", label: a.acknowledged ? "acked" : "open", immutable: true })));
    od.forEach((o) => items.push(mk("order", o.submitted_at, o.id, "INFO", o.paper_account_id, "", o.correlation_id, { href: `/trading/orders/${o.id}`, label: o.broker_state, immutable: true })));
    return items.sort((x, y) => (Number(y.ts) || 0) - (Number(x.ts) || 0));
  }, [token]);

  const [type, setType] = useState("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const all = ev.data || [];
  const filtered = useMemo(() => all.filter((e) =>
    (type === "all" || e.type === type) &&
    (!q || `${e.ref} ${e.correlation} ${e.scope} ${e.hash}`.toLowerCase().includes(q.toLowerCase()))
  ), [all, type, q]);
  const pageRows = filtered.slice(page * PAGE, page * PAGE + PAGE);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE));

  return (
    <div className="page shell-page">
      <TradingHeader title="Evidence & Audit"
        subtitle="Immutable evidence from the canonical services — result hashes, correlation IDs, and record references. Read-only." />
      <TradingTabs />
      <SignInGate ready={ready} token={token}>
        <SafetyBanner severity="ok" />
        {ev.loading ? <Loading /> : null}
        <LoadError error={ev.error} />

        <div className="ws-toolbar" style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12, alignItems: "center" }}>
          <input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="Filter by ref / correlation / scope / hash…"
            aria-label="Filter evidence" className="mono" style={{ flex: "1 1 240px", padding: "7px 10px", borderRadius: 8, background: "var(--surface-2,#12151b)", border: "1px solid var(--border-subtle,#20242e)", color: "var(--text-primary)" }} />
          <div role="group" aria-label="Evidence type" style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
            {TYPES.map((t) => (
              <button key={t} className="mono" data-testid={`type-${t}`} aria-pressed={type === t}
                onClick={() => { setType(t); setPage(0); }} style={chip(type === t)}>{t}</button>
            ))}
          </div>
        </div>

        <DataTable
          testId="evidence-table"
          columns={[
            { key: "type", label: "Type", render: (r) => <span className="mono" style={{ fontSize: 11 }}>{r.type}</span> },
            { key: "severity", label: "Sev", render: (r) => <StateChip state={r.severity} /> },
            { key: "ref", label: "Reference", render: (r) => <span className="mono">{r.ref}</span> },
            { key: "scope", label: "Scope/Account" },
            { key: "hash", label: "Result hash", render: (r) => shortHash(r.hash, 12) },
            { key: "correlation", label: "Correlation", render: (r) => r.correlation || "—" },
            { key: "kind", label: "Kind", render: (r) => (r.plan ? <span className="mono" style={planTag} data-testid="evidence-plan-tag">PLAN ONLY — NO AUTOMATIC REPAIR PATH EXISTS</span> : (r.immutable ? <span className="mono" style={{ fontSize: 10, color: "#10C98A" }}>immutable</span> : "—")) },
            { key: "ts", label: "When", render: (r) => fmtTs(r.ts) },
            { key: "open", label: "", render: (r) => (r.href ? <Link href={r.href} className="mono" style={{ color: "#5B8CFF", textDecoration: "none", fontSize: 11 }}>open →</Link> : null) },
          ]}
          rows={pageRows} getKey={(r) => `${r.type}-${r.ref}`}
          empty="No evidence records" />

        {filtered.length > PAGE ? (
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 10 }}>
            <button className="mono" style={chip(false)} disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>← Prev</button>
            <Text tone="muted" size="xs">Page {page + 1} / {pages} · {filtered.length} records</Text>
            <button className="mono" style={chip(false)} disabled={page >= pages - 1} onClick={() => setPage((p) => Math.min(pages - 1, p + 1))}>Next →</button>
          </div>
        ) : null}

        <Text tone="muted" size="xs" as="p" style={{ marginTop: 12 }}>
          Evidence is read-only. This view offers no mutation controls. Repair plans are advisory metadata — no automatic repair path exists.
        </Text>
      </SignInGate>
    </div>
  );
}

function mk(type, ts, ref, severity, scope, hash, correlation, extra = {}) {
  return { type, ts, ref, severity: severity || "INFO", scope: scope || "—", hash: hash || "", correlation: correlation || "", ...extra };
}
const planTag = { fontSize: 9.5, color: "#F5A623", border: "1px solid color-mix(in srgb,#F5A623 45%,transparent)", background: "color-mix(in srgb,#F5A623 10%,transparent)", borderRadius: 5, padding: "1px 5px" };
function chip(active) {
  return { fontSize: 11, padding: "5px 10px", borderRadius: 8, cursor: "pointer",
    color: active ? "var(--text-primary)" : "var(--text-muted)",
    background: active ? "color-mix(in srgb,#5B8CFF 16%,transparent)" : "transparent",
    border: active ? "1px solid color-mix(in srgb,#5B8CFF 45%,transparent)" : "1px solid var(--border-subtle,#20242e)" };
}
