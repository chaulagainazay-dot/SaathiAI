"use client";
// M60 Workstream 2 — Guided mission creation. LIVE: mission create is
// POST /missions (real). Requires a project (fetched; can be created via
// POST /projects). Local draft autosave; server submit + reconcile from server;
// never an optimistic "created" state.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { WorkflowStepper, DraftRecoveryBanner, ServerReconciliationState, RoleBoundaryNotice } from "@/components/spatial/GuidedWorkflow";
import { Field, SectionPanel } from "@/components/spatial/primitives";
import { usePlatformData, plat } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { validateMissionDraft, missionCreateBody, normalizeMissionDraft, RISK_LEVELS, actionPermission, classifyError, errorMessage } from "@/lib/operator";
import { lsGet, lsSet, lsRemove, LS_KEYS } from "@/lib/local-store";

const STEPS = [
  { id: "intent", title: "Intent" },
  { id: "scope", title: "Scope" },
  { id: "details", title: "Objective & risk" },
  { id: "review", title: "Review" },
];

export default function MissionNewPage() {
  const d = usePlatformData();
  const router = useRouter();
  const [projects, setProjects] = useState([]);
  const [draft, setDraft] = useState(normalizeMissionDraft({}));
  const [hasDraft, setHasDraft] = useState(false);
  const [activeId, setActiveId] = useState("intent");
  const [recon, setRecon] = useState("idle");
  const [err, setErr] = useState(null);
  const [created, setCreated] = useState(null);
  const [newProjectName, setNewProjectName] = useState("");

  const loadProjects = useCallback(async () => {
    if (!d.token) return;
    try { const r = await plat("/projects", { token: d.token }); setProjects(r?.projects || []); } catch { /* */ }
  }, [d.token]);

  useEffect(() => { loadProjects(); }, [loadProjects]);
  useEffect(() => {
    const saved = lsGet(LS_KEYS.missionDraft, null);
    if (saved && (saved.title || saved.objective)) { setDraft(normalizeMissionDraft(saved)); setHasDraft(true); }
  }, []);

  const update = (patch) => {
    const next = normalizeMissionDraft({ ...draft, ...patch, savedAt: nowLabel() });
    setDraft(next);
    lsSet(LS_KEYS.missionDraft, next);
  };
  const discardDraft = () => { lsRemove(LS_KEYS.missionDraft); setDraft(normalizeMissionDraft({})); setHasDraft(false); };

  const role = d.me?.context?.role;
  const perm = actionPermission(role, "create_mission");
  const validation = useMemo(() => validateMissionDraft(draft), [draft]);
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";

  const createProject = async () => {
    if (!newProjectName.trim()) return;
    setErr(null);
    try {
      const r = await plat("/projects", { method: "POST", token: d.token, body: { name: newProjectName.trim() } });
      const pid = r?.project?.project_id || r?.project_id;
      await loadProjects();
      if (pid) update({ projectId: pid });
      setNewProjectName("");
    } catch (e) { setErr(errorMessage(classifyError(e))); }
  };

  const submit = async () => {
    if (!validation.valid || perm !== "permitted") return;
    setRecon("submitting");
    setErr(null);
    try {
      const body = missionCreateBody(draft);
      const res = await plat("/missions", { method: "POST", token: d.token, body });
      setRecon("server_accepted");
      // reconcile: refetch missions and confirm the created mission exists server-side
      const list = await plat("/missions", { token: d.token }).catch(() => ({ missions: [] }));
      const mid = res?.mission?.mission_id || res?.mission_id;
      const found = (list.missions || []).find((m) => m.mission_id === mid);
      if (found) {
        setRecon("reconciled");
        setCreated(found);
        lsRemove(LS_KEYS.missionDraft);
      } else {
        setRecon("unknown");
      }
    } catch (e) {
      setRecon("server_rejected");
      setErr(errorMessage(classifyError(e)) + (e?.message ? ` — ${String(e.message).slice(0, 120)}` : ""));
    }
  };

  return (
    <SpatialWorkspaceShell
      title="Create a mission"
      subtitle="A guided, governed mission-creation flow. Mission creation is a real server action; scope, agents, approvals, and execution stay server-owned."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Missions", href: "/platform/missions" }, { label: "New" }]}
      signal={cSignal}
      health={d.health}
      loading={d.loading}
      error={d.error}
      paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        {created ? (
          <SectionPanel title="Mission created" signal="active">
            <p style={{ color: "var(--text-secondary)" }}>Reconciled with server. The mission now exists.</p>
            <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
              <Field label="Name" value={created.name} />
              <Field label="Key" value={created.key} mono />
              <Field label="Id" value={created.mission_id} mono />
              <Field label="Status" value={created.status} />
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
              <button className="ws-chip" onClick={() => router.push(`/platform/missions/${created.mission_id}/plan`)}>Open mission plan →</button>
              <button className="ws-chip" onClick={() => router.push(`/platform/missions/${created.mission_id}`)}>Open mission →</button>
            </div>
          </SectionPanel>
        ) : (
          <div style={{ display: "grid", gap: "var(--space-4)" }}>
            {hasDraft && <DraftRecoveryBanner savedAt={draft.savedAt} onResume={() => setHasDraft(false)} onDiscard={discardDraft} label="mission draft" />}
            <WorkflowStepper steps={STEPS.map((s) => ({ ...s, complete: stepComplete(s.id, draft, validation) }))} activeId={activeId} onSelect={setActiveId} />
            <RoleBoundaryNotice role={role} permission={perm} action="create mission" />
            {err && <div className="glass-frame glass-frame--danger" style={{ padding: 12 }} role="alert"><span style={{ color: "var(--text-secondary)" }}>{err}</span></div>}

            <SectionPanel title={STEPS.find((s) => s.id === activeId).title} signal="active">
              {activeId === "intent" && (
                <div style={{ display: "grid", gap: 12 }}>
                  <Labeled label="Mission title *"><input value={draft.title} onChange={(e) => update({ title: e.target.value })} className="mono" style={inp} aria-label="Mission title" /></Labeled>
                  <Labeled label="Objective *"><textarea value={draft.objective} onChange={(e) => update({ objective: e.target.value })} style={{ ...inp, minHeight: 70 }} aria-label="Objective" /></Labeled>
                  <Labeled label="Desired outcome"><input value={draft.outcome} onChange={(e) => update({ outcome: e.target.value })} style={inp} aria-label="Desired outcome" /></Labeled>
                  <Labeled label="Operator notes"><input value={draft.notes} onChange={(e) => update({ notes: e.target.value })} style={inp} aria-label="Operator notes" /></Labeled>
                </div>
              )}
              {activeId === "scope" && (
                <div style={{ display: "grid", gap: 10 }}>
                  <Field label="Organization" value={d.me?.context?.org_id || "Unavailable"} mono />
                  <Field label="Workspace" value={d.me?.context?.workspace_id || "Unavailable"} mono />
                  <Field label="Owner / role" value={`${d.me?.user?.email || "—"} · ${role || "unknown"}`} />
                  <Labeled label="Project *">
                    <select value={draft.projectId} onChange={(e) => update({ projectId: e.target.value })} style={inp} aria-label="Project">
                      <option value="">— select project —</option>
                      {projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.name} ({p.project_id})</option>)}
                    </select>
                  </Labeled>
                  {projects.length === 0 && <p className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>No projects yet — create one:</p>}
                  <div style={{ display: "flex", gap: 8 }}>
                    <input value={newProjectName} onChange={(e) => setNewProjectName(e.target.value)} placeholder="New project name" className="mono" style={{ ...inp, maxWidth: 260 }} aria-label="New project name" />
                    <button className="ws-chip" onClick={createProject}>Create project</button>
                  </div>
                </div>
              )}
              {activeId === "details" && (
                <div style={{ display: "grid", gap: 12 }}>
                  <Labeled label="Constraints"><input value={draft.constraints} onChange={(e) => update({ constraints: e.target.value })} style={inp} aria-label="Constraints" /></Labeled>
                  <Labeled label="Deadline"><input value={draft.deadline} onChange={(e) => update({ deadline: e.target.value })} placeholder="e.g. 2026-08-01" style={inp} aria-label="Deadline" /></Labeled>
                  <Labeled label="Priority">
                    <select value={draft.priority} onChange={(e) => update({ priority: e.target.value })} style={inp} aria-label="Priority">
                      <option value="low">low</option><option value="normal">normal</option><option value="high">high</option>
                    </select>
                  </Labeled>
                  <Labeled label="Risk (operator-selected — not an authoritative policy result)">
                    <select value={draft.risk} onChange={(e) => update({ risk: e.target.value })} style={inp} aria-label="Risk">
                      {RISK_LEVELS.map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </Labeled>
                </div>
              )}
              {activeId === "review" && (
                <div style={{ display: "grid", gap: 8 }}>
                  <Field label="Title" value={draft.title || "—"} />
                  <Field label="Objective" value={draft.objective || "—"} />
                  <Field label="Project" value={draft.projectId || "— (required)"} mono />
                  <Field label="Priority / risk" value={`${draft.priority} · ${draft.risk}`} />
                  <Field label="Server body" value={JSON.stringify(missionCreateBody(draft))} mono />
                  {!validation.valid && (
                    <ul style={{ margin: "6px 0 0", paddingLeft: 18, color: "var(--signal-danger)", fontSize: "var(--fs-2xs)" }}>
                      {validation.errors.map((e, i) => <li key={i}>{e.message}</li>)}
                    </ul>
                  )}
                  <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 8, flexWrap: "wrap" }}>
                    <button disabled={!validation.valid || perm !== "permitted" || recon === "submitting"} onClick={submit} style={submitBtn(!validation.valid || perm !== "permitted")}>Create mission (server)</button>
                    <ServerReconciliationState state={recon} />
                  </div>
                </div>
              )}
              <StepNav activeId={activeId} setActiveId={setActiveId} />
            </SectionPanel>
          </div>
        )}
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}

function stepComplete(id, draft, validation) {
  if (id === "intent") return !!(draft.title && draft.objective);
  if (id === "scope") return !!draft.projectId;
  if (id === "details") return true;
  if (id === "review") return validation.valid;
  return false;
}
function StepNav({ activeId, setActiveId }) {
  const ids = ["intent", "scope", "details", "review"];
  const i = ids.indexOf(activeId);
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
      {i > 0 && <button className="ws-chip" onClick={() => setActiveId(ids[i - 1])}>← Back</button>}
      {i < ids.length - 1 && <button className="ws-chip" onClick={() => setActiveId(ids[i + 1])} style={{ marginLeft: "auto" }}>Next →</button>}
    </div>
  );
}
function Labeled({ label, children }) {
  return <label className="eyebrow" style={{ color: "var(--text-muted)", display: "grid", gap: 4 }}>{label}{children}</label>;
}
function nowLabel() {
  try { return new Date().toISOString().slice(0, 16).replace("T", " "); } catch { return "recently"; }
}
const inp = { background: "transparent", border: "1px solid var(--glass-frame-border)", borderRadius: 8, color: "var(--text-primary)", padding: "7px 10px", font: "inherit", width: "100%", boxSizing: "border-box" };
const submitBtn = (disabled) => ({ background: disabled ? "transparent" : "color-mix(in srgb, var(--signal-active) 18%, transparent)", border: `1px solid ${disabled ? "var(--glass-frame-border)" : "color-mix(in srgb, var(--signal-active) 50%, transparent)"}`, color: disabled ? "var(--text-muted)" : "var(--text-primary)", borderRadius: 10, padding: "8px 16px", cursor: disabled ? "not-allowed" : "pointer" });
