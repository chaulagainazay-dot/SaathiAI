"use client";
// M13.5 AI Studio workspace — real backend only (/api/v1/studio-os/*).
// No mock/sample data: every panel reflects genuine API responses, honest
// empty/loading/error states, provider health from the real capability matrix,
// storage preflight from the real disk report. Terminal states handled.
import { useCallback, useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";

const CONTENT_TYPES = ["script_only", "social_post", "short_video", "long_video",
                       "avatar", "repurpose"];
const PLATFORMS = ["youtube", "tiktok", "facebook", "instagram", "linkedin",
                   "reddit", "website"];

const STATE_COLOR = {
  draft: "#8fa0c4", planning: "#8fa0c4", running: "#5ea1ff",
  awaiting_review: "#ffb04f", awaiting_approval: "#ffb04f", approved: "#4fe3cb",
  rendering: "#5ea1ff", completed: "#4fe3cb", partially_completed: "#ffb04f",
  cancelled: "#8fa0c4", failed: "#ff5a5a",
};

const S = {
  wrap: { display: "flex", height: "calc(100vh - 60px)", color: "#e8ecf5" },
  side: { width: 280, borderRight: "1px solid rgba(255,255,255,.08)", padding: 12,
          overflowY: "auto", display: "flex", flexDirection: "column", gap: 8 },
  main: { flex: 1, display: "flex", flexDirection: "column", minWidth: 0, overflowY: "auto" },
  panel: { width: 300, borderLeft: "1px solid rgba(255,255,255,.08)", padding: 12,
           overflowY: "auto", fontSize: 12 },
  input: { width: "100%", background: "rgba(255,255,255,.05)", color: "#e8ecf5",
           border: "1px solid rgba(255,255,255,.1)", borderRadius: 10,
           padding: "8px 10px", fontSize: 13, marginBottom: 8 },
  btn: (c = "#4fe3cb") => ({ background: `${c}18`, color: c, border: `1px solid ${c}55`,
        borderRadius: 10, padding: "8px 12px", fontSize: 13, cursor: "pointer" }),
  badge: (c) => ({ display: "inline-block", padding: "2px 9px", borderRadius: 999,
        fontSize: 10, background: `${c}22`, color: c, border: `1px solid ${c}55` }),
  card: { padding: 10, borderRadius: 10, background: "rgba(255,255,255,.04)",
          border: "1px solid rgba(255,255,255,.06)", marginBottom: 8, cursor: "pointer" },
  row: { padding: "6px 8px", borderRadius: 8, background: "rgba(255,255,255,.03)",
         marginBottom: 6, fontSize: 12 },
  head: { fontSize: 10, opacity: .5, letterSpacing: ".14em", margin: "12px 0 6px" },
};

export default function StudioWorkspace() {
  const [projects, setProjects] = useState([]);
  const [active, setActive] = useState(null);
  const [detail, setDetail] = useState(null);
  const [providers, setProviders] = useState(null);
  const [storage, setStorage] = useState(null);
  const [form, setForm] = useState({ title: "", objective: "",
    content_type: "short_video", budget_usd: 5, platforms: ["youtube"] });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadProjects = useCallback(async () => {
    try {
      const r = await afetch(`${API_BASE}/api/v1/studio-os/projects`, { cache: "no-store" });
      const j = await r.json();
      setProjects(j.projects || []);
      setError("");
    } catch { setError("Backend unreachable — is the SaathiAI server running?"); }
  }, []);

  const loadDetail = useCallback(async (pid) => {
    if (!pid) { setDetail(null); return; }
    try {
      const r = await afetch(`${API_BASE}/api/v1/studio-os/projects/${pid}`, { cache: "no-store" });
      setDetail(await r.json());
    } catch { /* keep last */ }
  }, []);

  const loadMeta = useCallback(async () => {
    try {
      const [p, s] = await Promise.all([
        afetch(`${API_BASE}/api/v1/studio-os/providers`, { cache: "no-store" }),
        afetch(`${API_BASE}/api/v1/studio-os/storage/health`, { cache: "no-store" }),
      ]);
      setProviders(await p.json());
      setStorage(await s.json());
    } catch { /* meta optional */ }
  }, []);

  useEffect(() => { loadProjects(); loadMeta(); }, [loadProjects, loadMeta]);
  useEffect(() => { loadDetail(active); }, [active, loadDetail]);

  async function createProject() {
    if (!form.objective.trim()) { setError("Objective is required."); return; }
    setBusy(true);
    try {
      const r = await afetch(`${API_BASE}/api/v1/studio-os/projects`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const j = await r.json();
      if (j.error) setError(j.error);
      else { await loadProjects(); setActive(j.project_id); }
    } catch { setError("Create failed."); }
    setBusy(false);
  }

  async function runProject() {
    if (!active) return;
    setBusy(true);
    try {
      const r = await afetch(`${API_BASE}/api/v1/studio-os/projects/${active}/run`,
        { method: "POST" });
      const j = await r.json();
      if (j.error) setError(j.error);
      await loadDetail(active); await loadProjects(); await loadMeta();
    } catch { setError("Run failed."); }
    setBusy(false);
  }

  async function approveArtifact(aid) {
    await afetch(`${API_BASE}/api/v1/studio-os/artifacts/${aid}/approve?approved=true`,
      { method: "POST" });
    loadDetail(active);
  }

  async function publishDryRun(platform) {
    const r = await afetch(`${API_BASE}/api/v1/studio-os/projects/${active}/publish`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platform, approved: true, live: false }),
    });
    const j = await r.json();
    setError(j.error ? j.error : `Publish ${j.status || "?"}: ${j.detail || ""}`);
    loadDetail(active);
  }

  async function cancelProject() {
    await afetch(`${API_BASE}/api/v1/studio-os/projects/${active}/cancel`, { method: "POST" });
    loadDetail(active); loadProjects();
  }

  const p = detail?.project;
  const stColor = p ? (STATE_COLOR[p.state] || "#8fa0c4") : "#8fa0c4";

  return (
    <div style={S.wrap} role="region" aria-label="AI Studio workspace">
      {/* sidebar: create + project list */}
      <aside style={S.side}>
        <div style={S.head}>NEW PROJECT</div>
        <input style={S.input} placeholder="Title" value={form.title}
               onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <textarea style={{ ...S.input, height: 54, resize: "none" }} placeholder="Objective *"
               value={form.objective}
               onChange={(e) => setForm({ ...form, objective: e.target.value })} />
        <select style={S.input} value={form.content_type}
                onChange={(e) => setForm({ ...form, content_type: e.target.value })}>
          {CONTENT_TYPES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select style={S.input} value={form.platforms[0]}
                onChange={(e) => setForm({ ...form, platforms: [e.target.value] })}>
          {PLATFORMS.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <input style={S.input} type="number" min="0" step="0.5" placeholder="Budget USD"
               value={form.budget_usd}
               onChange={(e) => setForm({ ...form, budget_usd: Number(e.target.value) })} />
        <button style={S.btn()} disabled={busy} onClick={createProject}>＋ Create project</button>

        <div style={S.head}>PROJECTS</div>
        {projects.map((pr) => (
          <div key={pr.id} style={{ ...S.card, borderColor: pr.id === active
                ? "rgba(0,191,165,.4)" : "rgba(255,255,255,.06)" }}
               onClick={() => setActive(pr.id)}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {pr.title || "Untitled"}</span>
              <span style={S.badge(STATE_COLOR[pr.state] || "#8fa0c4")}>{pr.state}</span>
            </div>
            <div style={{ opacity: .5, marginTop: 3 }}>{pr.workflow} · ${pr.cost_usd?.toFixed?.(2) ?? 0}</div>
          </div>))}
        {projects.length === 0 && <div style={{ opacity: .5, fontSize: 12 }}>No projects yet.</div>}
      </aside>

      {/* main: stages + artifacts */}
      <main style={S.main}>
        {error && <div style={{ padding: "8px 16px", color: "#ff8c8c", fontSize: 12 }} role="alert">{error}</div>}
        {!p && <div style={{ margin: "auto", opacity: .6, padding: 40, textAlign: "center" }}>
          Select or create a project. Media is generated locally (Pillow images,
          FFmpeg video, macOS narration); nothing publishes without approval.</div>}
        {p && (
          <div style={{ padding: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <strong style={{ fontSize: 15 }}>{p.title || "Untitled"}</strong>
              <span style={S.badge(stColor)}>{p.state}</span>
              <div style={{ flex: 1 }} />
              {["draft", "planning", "awaiting_review", "partially_completed", "failed"].includes(p.state) &&
                <button style={S.btn()} disabled={busy} onClick={runProject}>▶ Run workflow</button>}
              {!["completed", "cancelled", "failed", "archived"].includes(p.state) &&
                <button style={S.btn("#ff5a5a")} onClick={cancelProject}>✕ Cancel</button>}
            </div>
            <div style={{ opacity: .7, fontSize: 13, marginBottom: 8 }}>{p.objective}</div>

            <div style={S.head}>STAGES ({detail.stages?.length || 0})</div>
            {(detail.stages || []).map((s) => (
              <div key={s.id} style={S.row}>
                <span style={S.badge(s.status === "done" ? "#4fe3cb" :
                  s.status === "failed" ? "#ff5a5a" : "#5ea1ff")}>{s.status}</span>
                {" "}{s.name}{s.detail ? ` — ${s.detail}` : ""}
              </div>))}
            {(detail.stages || []).length === 0 && <div style={{ opacity: .5 }}>No stages yet — run the workflow.</div>}

            <div style={S.head}>ARTIFACTS ({detail.artifacts?.length || 0})</div>
            {(detail.artifacts || []).map((a) => (
              <div key={a.id} style={S.row}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>{a.artifact_type} v{a.version}
                    {a.provider ? ` · ${a.provider}` : ""}</span>
                  {a.file_size > 0
                    ? <span style={{ opacity: .5 }}>{Math.round(a.file_size / 1024)}KB · cs {a.checksum?.slice(0, 6)}</span>
                    : <span style={{ opacity: .5 }}>text</span>}
                </div>
                {a.artifact_type === "final_video" && (
                  <button style={{ ...S.btn(), marginTop: 6, padding: "3px 8px", fontSize: 11 }}
                          onClick={() => approveArtifact(a.id)}>
                    {a.approval_status === "approved" ? "✓ approved" : "Approve"}</button>)}
              </div>))}
            {(detail.artifacts || []).length === 0 && <div style={{ opacity: .5 }}>No artifacts yet.</div>}

            {(detail.artifacts || []).some((a) => a.artifact_type === "final_video"
              && a.approval_status === "approved") && (
              <>
                <div style={S.head}>PUBLISH (dry-run — no external upload)</div>
                {p.spec?.platforms?.map?.((pl) => (
                  <button key={pl} style={{ ...S.btn("#c9b6ff"), marginRight: 6 }}
                          onClick={() => publishDryRun(pl)}>{pl} dry-run</button>
                )) || <button style={S.btn("#c9b6ff")} onClick={() => publishDryRun("youtube")}>youtube dry-run</button>}
              </>)}
          </div>)}
      </main>

      {/* right: cost + storage + providers */}
      <aside style={S.panel} className="only-desktop">
        {p && <>
          <div style={S.head}>COST</div>
          <div style={S.row}>${detail.cost?.total_usd ?? 0} / ${detail.cost?.budget_usd ?? 0} budget</div>
        </>}
        <div style={S.head}>STORAGE</div>
        {storage ? (
          <div style={S.row}>
            <span style={S.badge(storage.healthy ? "#4fe3cb" : "#ff5a5a")}>
              {storage.healthy ? "healthy" : "low"}</span> {storage.free_gb}GB free
          </div>) : <div style={{ opacity: .5 }}>—</div>}
        <div style={S.head}>PROVIDERS (real status)</div>
        {providers ? Object.entries(providers).map(([kind, rows]) => (
          <div key={kind} style={{ marginBottom: 8 }}>
            <div style={{ opacity: .6, textTransform: "uppercase", fontSize: 10 }}>{kind}</div>
            {rows.map((r) => (
              <div key={r.name} style={{ opacity: .85, marginBottom: 2 }}>
                <span style={S.badge(r.available ? "#4fe3cb" : "#8fa0c4")}>
                  {r.available ? "avail" : r.configured ? "cfg" : "off"}</span> {r.name}
                {r.local ? " (local)" : ""}
              </div>))}
          </div>)) : <div style={{ opacity: .5 }}>—</div>}
      </aside>
    </div>
  );
}
