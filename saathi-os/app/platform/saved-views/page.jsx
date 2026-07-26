"use client";
// M61 — Saved workspace views: now SERVER_PERSISTED (was M60 LOCAL_ONLY).
// CRUD round-trips to /api/v1/platform/workflow/saved-views; the server strips
// forbidden fields and versions each view. Interaction model unchanged from M60.
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { SectionPanel } from "@/components/spatial/primitives";
import { usePlatformData } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { validateSavedView, actionPermission } from "@/lib/operator";
import { listViews, createView, deleteView } from "@/lib/workflow-api";
import { classifyError, errorMessage } from "@/lib/operator";

const PRESETS = [
  { name: "High-risk approvals", route: "/platform/approvals", config: { risk: "high", lifecycle: "pending" } },
  { name: "Blocked missions", route: "/platform/missions", config: { status: "blocked" } },
  { name: "Critical attention", route: "/platform/attention", config: { severity: "critical" } },
  { name: "Operator action queue", route: "/platform/actions", config: {} },
];

export default function SavedViewsPage() {
  const d = usePlatformData();
  const router = useRouter();
  const [views, setViews] = useState([]);
  const [name, setName] = useState("");
  const [route, setRoute] = useState("/platform/missions");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!d.token) return;
    // Cold-start resilience: a concurrent cold request can transiently 401/network-
    // fail; retry a few times before surfacing an error (consistent with M57/M58).
    for (let i = 0; i < 6; i += 1) {
      try { setViews(await listViews(d.token)); setErr(null); return; }
      catch (e) {
        const transient = /Failed to fetch|NetworkError|load failed|session expired|SESSION_INVALID|401/i.test(String(e?.message || e)) || e?.status === 401;
        if (i === 5 || !transient) { setErr(errorMessage(classifyError(e))); return; }
        await new Promise((r) => setTimeout(r, Math.min(2000, 400 * (i + 1))));
      }
    }
  }, [d.token]);
  useEffect(() => { load(); }, [load]);

  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";
  const perm = actionPermission(d.me?.context?.role, "create_mission");

  const add = async (raw) => {
    const v = validateSavedView(raw);
    if (!v.valid) { setErr(v.errors.map((e) => e.message).join("; ")); return; }
    setBusy(true); setErr(null);
    try { await createView({ name: v.view.name, route: v.view.route, config: v.view.filters || raw.config || {} }, d.token); await load(); setName(""); }
    catch (e) { setErr(errorMessage(classifyError(e))); }
    finally { setBusy(false); }
  };
  const remove = async (id) => { setBusy(true); try { await deleteView(id, d.token); await load(); } catch (e) { setErr(errorMessage(classifyError(e))); } finally { setBusy(false); } };

  return (
    <SpatialWorkspaceShell
      title="Saved views"
      subtitle="Save safe view preferences (route, filters). Server-persisted and versioned; no credentials, authority, or secrets are ever stored."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Saved views" }]}
      signal={cSignal} health={d.health} loading={d.loading || busy} error={d.error} paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <SectionPanel title="Create a saved view">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="View name" className="mono" style={inp} aria-label="View name" />
            <select value={route} onChange={(e) => setRoute(e.target.value)} style={inp} aria-label="Route">
              {["/platform/missions", "/platform/agents", "/platform/approvals", "/platform/attention", "/platform/actions", "/platform/evidence"].map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <button className="ws-chip" disabled={perm !== "permitted"} onClick={() => add({ name, route, config: {} })}>Save view</button>
          </div>
          {err && <p style={{ color: "var(--signal-danger)", fontSize: "var(--fs-2xs)", marginTop: 8 }}>{err}</p>}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 12 }}>
            <span className="eyebrow" style={{ color: "var(--text-muted)" }}>Presets</span>
            {PRESETS.map((p) => <button key={p.name} className="ws-chip" disabled={perm !== "permitted"} onClick={() => add(p)}>{p.name}</button>)}
          </div>
          <p className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginTop: 10 }}>SERVER_PERSISTED · versioned · tenant-scoped</p>
        </SectionPanel>

        <div style={{ marginTop: "var(--space-4)" }}>
          {views.length === 0 ? <div className="glass-frame" style={{ padding: "var(--space-5)" }}><p style={{ color: "var(--text-muted)" }}>No saved views yet.</p></div> : (
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
              {views.map((v) => (
                <li key={v.view_id} className="glass-frame" style={{ padding: "12px 14px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                  <span style={{ color: "var(--text-primary)" }}>{v.name}</span>
                  <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{v.route} · v{v.version} · {v.config && Object.keys(v.config).length ? JSON.stringify(v.config) : "no filters"}</span>
                  <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                    <button className="ws-chip" onClick={() => router.push(v.route)}>Open →</button>
                    <button className="ws-chip" onClick={() => remove(v.view_id)}>Delete</button>
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

const inp = { background: "transparent", border: "1px solid var(--glass-frame-border)", borderRadius: 8, color: "var(--text-primary)", padding: "7px 10px", font: "inherit" };
