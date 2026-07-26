"use client";
// M60 Workstream 11 — Cross-workspace search. SEARCHING_AUTHORIZED_LOADED_RECORDS:
// client-side over records already fetched through authorized APIs. No
// unauthorized indexing, no secret-bearing snippets. Recent history is local-only.
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { usePlatformData, plat } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { searchAuthorizedRecords } from "@/lib/operator";
import { lsGet, lsSet, LS_KEYS } from "@/lib/local-store";

const TYPES = ["all", "mission", "agent", "approval", "attention", "execution", "project"];

export default function SearchPage() {
  const d = usePlatformData();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [type, setType] = useState("all");
  const [projects, setProjects] = useState([]);
  const [approvalsAll, setApprovalsAll] = useState([]);
  const [history, setHistory] = useState([]);

  useEffect(() => { setHistory(lsGet(LS_KEYS.searchHistory, [])); }, []);
  useEffect(() => {
    if (!d.token) return;
    plat("/projects", { token: d.token }).then((r) => setProjects(r?.projects || [])).catch(() => {});
    plat("/approvals?status=", { token: d.token }).then((r) => setApprovalsAll(r?.approvals || [])).catch(() => {});
  }, [d.token]);

  const results = useMemo(() => searchAuthorizedRecords(q, {
    missions: d.missions, bindings: d.bindings, approvals: approvalsAll.length ? approvalsAll : d.approvals,
    attention: d.attention, executions: d.executions, projects,
  }, type), [q, d.missions, d.bindings, d.approvals, approvalsAll, d.attention, d.executions, projects, type]);

  const grouped = useMemo(() => { const g = {}; for (const r of results) (g[r.type] ||= []).push(r); return g; }, [results]);
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";

  const commit = (val) => {
    const v = val.trim();
    if (!v) return;
    const next = [v, ...history.filter((h) => h !== v)].slice(0, 8);
    setHistory(next); lsSet(LS_KEYS.searchHistory, next);
  };

  return (
    <SpatialWorkspaceShell
      title="Cross-workspace search"
      subtitle="Search across your authorized loaded records — missions, agents, approvals, attention, executions, projects."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Search" }]}
      signal={cSignal}
      health={d.health}
      loading={d.loading}
      error={d.error}
      paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <div className="ws-toolbar" style={{ marginBottom: 8 }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} onBlur={(e) => commit(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") commit(q); }}
            placeholder="Search…" aria-label="Search" autoFocus className="mono"
            style={{ background: "transparent", border: "1px solid var(--glass-frame-border)", borderRadius: 10, color: "var(--text-primary)", padding: "8px 14px", minWidth: 260 }} />
          <div role="group" aria-label="Type filter" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {TYPES.map((t) => <button key={t} className="ws-chip" aria-pressed={type === t} onClick={() => setType(t)}>{t}</button>)}
          </div>
        </div>
        <p className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginBottom: 12 }}>SEARCHING_AUTHORIZED_LOADED_RECORDS — not a complete server-side global search.</p>

        {history.length > 0 && !q && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
            <span className="eyebrow" style={{ color: "var(--text-muted)" }}>Recent</span>
            {history.map((h) => <button key={h} className="ws-chip" onClick={() => setQ(h)}>{h}</button>)}
          </div>
        )}

        {q && results.length === 0 && <div className="glass-frame" style={{ padding: "var(--space-5)" }}><p style={{ color: "var(--text-muted)" }}>No matches in authorized loaded records.</p></div>}

        <div style={{ display: "grid", gap: "var(--space-4)" }}>
          {Object.entries(grouped).map(([t, list]) => (
            <section key={t} className="glass-frame" style={{ padding: "var(--space-4)" }} aria-label={t}>
              <div className="eyebrow" style={{ color: "var(--text-muted)", marginBottom: 8 }}>{t} · {list.length}</div>
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 6 }}>
                {list.map((r) => (
                  <li key={r.id} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ color: "var(--text-primary)", fontSize: "var(--fs-sm)" }}>{r.label}</span>
                    <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{r.id}</span>
                    <button className="ws-chip" style={{ marginLeft: "auto" }} onClick={() => router.push(r.route)}>Open →</button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}
