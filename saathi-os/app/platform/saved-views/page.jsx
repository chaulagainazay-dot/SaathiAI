"use client";
// M60 Workstream 10 — Saved workspace views (SAVED_VIEWS_LOCAL_ONLY). Stores only
// non-sensitive view preferences (route, filters, sort). validateSavedView
// strips any forbidden field (token/credential/authority/secret/permission).
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { SectionPanel } from "@/components/spatial/primitives";
import { usePlatformData } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { validateSavedView } from "@/lib/operator";
import { lsGet, lsSet, LS_KEYS } from "@/lib/local-store";

const PRESETS = [
  { name: "High-risk approvals", route: "/platform/approvals", filters: { risk: "high", lifecycle: "pending" } },
  { name: "Blocked missions", route: "/platform/missions", filters: { status: "blocked" } },
  { name: "Critical attention", route: "/platform/attention", filters: { severity: "critical" } },
  { name: "Operator action queue", route: "/platform/actions", filters: {} },
];

export default function SavedViewsPage() {
  const d = usePlatformData();
  const router = useRouter();
  const [views, setViews] = useState([]);
  const [name, setName] = useState("");
  const [route, setRoute] = useState("/platform/missions");
  const [err, setErr] = useState(null);

  useEffect(() => { setViews(lsGet(LS_KEYS.savedViews, [])); }, []);
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";

  const persist = (next) => { setViews(next); lsSet(LS_KEYS.savedViews, next); };
  const add = (raw) => {
    const v = validateSavedView({ ...raw, savedAt: nowLabel() });
    if (!v.valid) { setErr(v.errors.map((e) => e.message).join("; ")); return; }
    setErr(null);
    persist([...views.filter((x) => x.name !== v.view.name), { ...v.view, id: v.view.name.toLowerCase().replace(/\s+/g, "-") }]);
  };
  const remove = (id) => persist(views.filter((v) => v.id !== id));

  return (
    <SpatialWorkspaceShell
      title="Saved views"
      subtitle="Save safe view preferences (route, filters, sort). Local-only — no credentials, authority, or secrets are ever stored."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Saved views" }]}
      signal={cSignal} health={d.health} loading={d.loading} error={d.error} paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <SectionPanel title="Create a saved view">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="View name" className="mono" style={inp} aria-label="View name" />
            <select value={route} onChange={(e) => setRoute(e.target.value)} style={inp} aria-label="Route">
              {["/platform/missions", "/platform/agents", "/platform/approvals", "/platform/attention", "/platform/actions", "/platform/evidence"].map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <button className="ws-chip" onClick={() => add({ name, route })}>Save view</button>
          </div>
          {err && <p style={{ color: "var(--signal-danger)", fontSize: "var(--fs-2xs)", marginTop: 8 }}>{err}</p>}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 12 }}>
            <span className="eyebrow" style={{ color: "var(--text-muted)" }}>Presets</span>
            {PRESETS.map((p) => <button key={p.name} className="ws-chip" onClick={() => add(p)}>{p.name}</button>)}
          </div>
          <p className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginTop: 10 }}>SAVED_VIEWS_LOCAL_ONLY</p>
        </SectionPanel>

        <div style={{ marginTop: "var(--space-4)" }}>
          {views.length === 0 ? <div className="glass-frame" style={{ padding: "var(--space-5)" }}><p style={{ color: "var(--text-muted)" }}>No saved views yet.</p></div> : (
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
              {views.map((v) => (
                <li key={v.id} className="glass-frame" style={{ padding: "12px 14px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                  <span style={{ color: "var(--text-primary)" }}>{v.name}</span>
                  <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{v.route} · {v.filters ? JSON.stringify(v.filters) : "no filters"}</span>
                  <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                    <button className="ws-chip" onClick={() => router.push(v.route)}>Open →</button>
                    <button className="ws-chip" onClick={() => remove(v.id)}>Delete</button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}

function nowLabel() { try { return new Date().toISOString().slice(0, 16).replace("T", " "); } catch { return "recently"; } }
const inp = { background: "transparent", border: "1px solid var(--glass-frame-border)", borderRadius: 8, color: "var(--text-primary)", padding: "7px 10px", font: "inherit" };
