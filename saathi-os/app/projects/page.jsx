"use client";
import { useState, useEffect } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchProjects, createProject, fetchProject, updateProject, researchProject } from "@/lib/api";

const PURPLE = "#6C3FCF", TEAL = "#00BFA5";
const field = { width: "100%", padding: "10px 12px", borderRadius: 10, fontSize: 14, marginTop: 6,
  border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)", color: "inherit" };
const dot = (s) => ({ ready: TEAL, submitted: "#E8B84B", researching: "#8FB4FF", draft: "#8B98B4" }[s] || "#8B98B4");

function L({ label, children }) {
  return <label style={{ display: "block", fontSize: 12, opacity: 0.6 }}>{label}{children}</label>;
}

export default function Projects() {
  const [projects, setProjects] = useState([]);
  const [cur, setCur] = useState(null);       // open project (edit/view)
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const load = () => fetchProjects().then((d) => setProjects(d.projects || [])).catch(() => {});
  useEffect(() => { load(); }, []);

  const open = (id) => fetchProject(id).then(setCur).catch(() => {});
  const startNew = async () => { const p = await createProject({}); setCur(p); load(); };

  const setField = (path, value) => {
    setCur((c) => {
      const d = { ...c.data };
      if (path.length === 2) d[path[0]] = { ...(d[path[0]] || {}), [path[1]]: value };
      else d[path[0]] = value;
      return { ...c, data: d };
    });
  };
  const save = async (status) => {
    setBusy(true);
    try { const p = await updateProject(cur.id, cur.data, status); setCur({ ...p, share_url: cur.share_url }); load(); }
    finally { setBusy(false); }
  };
  const runResearch = async () => {
    setBusy(true);
    try { const p = await researchProject(cur.id); setCur({ ...p, share_url: cur.share_url }); load(); }
    finally { setBusy(false); }
  };

  // ── list view ──
  if (!cur) return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: "0 4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20 }}>
        <div>
          <Eyebrow style={{ color: PURPLE }}>Projects</Eyebrow>
          <div style={{ fontSize: 26, fontWeight: 600, marginTop: 4 }}>Create New Project</div>
          <div style={{ fontSize: 13, opacity: 0.5 }}>Capture a company → AI research → strategy → workspace.</div>
        </div>
        <button onClick={startNew} style={{ padding: "10px 20px", borderRadius: 12, border: "none",
          cursor: "pointer", fontWeight: 600, color: "#fff", background: PURPLE }}>+ New Project</button>
      </div>
      {projects.length === 0
        ? <Panel style={{ padding: 40, textAlign: "center", opacity: 0.5 }}>No projects yet — create your first.</Panel>
        : <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 14 }}>
            {projects.map((p) => (
              <Panel key={p.id} style={{ padding: 18, cursor: "pointer" }} onClick={() => open(p.id)}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>{p.name}</div>
                  <span style={{ fontSize: 11, color: dot(p.status) }}>● {p.status}</span>
                </div>
                <div style={{ fontSize: 12, opacity: 0.5, marginTop: 4 }}>
                  {(p.data.company?.industry) || "—"} · {p.strategy ? "strategy ready" : "awaiting research"}
                </div>
              </Panel>
            ))}
          </div>}
    </div>
  );

  // ── edit / workspace view ──
  const co = cur.data.company || {};
  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: "0 4px" }}>
      <button onClick={() => setCur(null)} style={{ background: "none", border: "none", color: "inherit",
        opacity: 0.6, cursor: "pointer", fontSize: 13, marginBottom: 12 }}>← All projects</button>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 16 }}>
        <div style={{ fontSize: 22, fontWeight: 600 }}>{cur.name}</div>
        <span style={{ fontSize: 12, color: dot(cur.status) }}>● {cur.status}</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 16 }}>
        {/* capture form */}
        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color: PURPLE }}>Company Information</Eyebrow>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
            <L label="Company Name"><input style={field} value={co.name || ""} onChange={(e) => setField(["company","name"], e.target.value)} /></L>
            <L label="Website"><input style={field} value={co.website || ""} onChange={(e) => setField(["company","website"], e.target.value)} /></L>
            <L label="Industry / Niche"><input style={field} value={co.industry || ""} onChange={(e) => setField(["company","industry"], e.target.value)} /></L>
            <L label="Location"><input style={field} value={co.location || ""} onChange={(e) => setField(["company","location"], e.target.value)} /></L>
            <L label="Contact Person"><input style={field} value={co.contact || ""} onChange={(e) => setField(["company","contact"], e.target.value)} /></L>
            <L label="Email"><input style={field} value={co.email || ""} onChange={(e) => setField(["company","email"], e.target.value)} /></L>
          </div>
          <L label="Company Description"><textarea style={{ ...field, minHeight: 60 }} value={co.description || ""} onChange={(e) => setField(["company","description"], e.target.value)} /></L>

          <Eyebrow style={{ color: PURPLE, marginTop: 18, display: "block" }}>Goals · Audience · Services · Budget</Eyebrow>
          <L label="Goals"><textarea style={{ ...field, minHeight: 48 }} value={cur.data.goals || ""} onChange={(e) => setField(["goals"], e.target.value)} /></L>
          <L label="Target Audience"><textarea style={{ ...field, minHeight: 48 }} value={cur.data.audience || ""} onChange={(e) => setField(["audience"], e.target.value)} /></L>
          <L label="Services"><textarea style={{ ...field, minHeight: 48 }} value={cur.data.services || ""} onChange={(e) => setField(["services"], e.target.value)} /></L>
          <L label="Budget & Timeline"><input style={field} value={cur.data.budget || ""} onChange={(e) => setField(["budget"], e.target.value)} /></L>

          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button onClick={() => save()} disabled={busy} style={{ padding: "10px 18px", borderRadius: 10,
              border: "1px solid rgba(255,255,255,0.15)", background: "transparent", color: "inherit", cursor: "pointer" }}>Save</button>
            <button onClick={runResearch} disabled={busy} style={{ padding: "10px 18px", borderRadius: 10, border: "none",
              fontWeight: 600, color: "#fff", background: PURPLE, cursor: "pointer" }}>
              {busy ? "Researching…" : "⚡ Run AI Research"}</button>
          </div>
        </Panel>

        {/* capture links + what happens next */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Panel style={{ padding: 16 }}>
            <Eyebrow>Smart Form — share with client</Eyebrow>
            <div style={{ fontSize: 11, opacity: 0.5, margin: "6px 0 10px" }}>They fill it, you get structured data.</div>
            <input readOnly value={cur.share_url || ""} style={{ ...field, fontSize: 11, marginTop: 0 }} />
            <button onClick={() => { navigator.clipboard?.writeText(cur.share_url || ""); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
              style={{ width: "100%", marginTop: 8, padding: "10px", borderRadius: 10, border: "none",
                fontWeight: 600, color: "#fff", background: copied ? TEAL : PURPLE, cursor: "pointer" }}>
              {copied ? "✓ Copied" : "Copy Link"}</button>
          </Panel>
          <Panel style={{ padding: 16 }}>
            <Eyebrow>What happens next</Eyebrow>
            {["🔎 AI researches company, industry, competitors",
              "📊 Analyses opportunities, gaps, positioning",
              "🎯 Strategy: direction, content ideas, plan",
              "📁 Everything organised in the workspace"].map((t) => (
              <div key={t} style={{ fontSize: 12.5, opacity: 0.7, padding: "6px 0" }}>{t}</div>
            ))}
          </Panel>
        </div>
      </div>

      {/* research + strategy result */}
      {cur.strategy && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 16, marginTop: 16 }}>
          <Panel style={{ padding: 18 }}>
            <Eyebrow style={{ color: TEAL }}>AI Research</Eyebrow>
            <p style={{ fontSize: 13.5, opacity: 0.85, marginTop: 8 }}>{cur.research?.summary}</p>
            {[["Opportunities", cur.research?.opportunities], ["Gaps", cur.research?.gaps],
              ["Competitors", cur.research?.competitors]].map(([t, arr]) => (arr?.length > 0) && (
              <div key={t} style={{ marginTop: 10 }}>
                <div style={{ fontSize: 11, opacity: 0.5 }}>{t}</div>
                {arr.map((x, i) => <div key={i} style={{ fontSize: 13, padding: "3px 0" }}>• {typeof x === "string" ? x : JSON.stringify(x)}</div>)}
              </div>
            ))}
          </Panel>
          <Panel style={{ padding: 18 }}>
            <Eyebrow style={{ color: PURPLE }}>Strategy & Direction</Eyebrow>
            <p style={{ fontSize: 13.5, opacity: 0.85, marginTop: 8 }}>{cur.strategy?.direction}</p>
            {cur.strategy?.content_ideas?.length > 0 && <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 11, opacity: 0.5 }}>Content ideas</div>
              {cur.strategy.content_ideas.map((x, i) => <div key={i} style={{ fontSize: 13, padding: "3px 0" }}>• {x}</div>)}</div>}
            {cur.strategy?.marketing_plan && <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 11, opacity: 0.5 }}>Marketing plan</div>
              <div style={{ fontSize: 13, opacity: 0.85 }}>{cur.strategy.marketing_plan}</div></div>}
            {cur.strategy?.next_steps?.length > 0 && <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 11, opacity: 0.5 }}>Next steps</div>
              {cur.strategy.next_steps.map((x, i) => <div key={i} style={{ fontSize: 13, padding: "3px 0" }}>{i + 1}. {x}</div>)}</div>}
          </Panel>
        </div>
      )}

      {/* wire: strategy → AI Studio content plan */}
      {cur.strategy?.content_ideas?.length > 0 && (
        <Panel style={{ padding: 18, marginTop: 16, border: "1px solid rgba(255,138,61,0.3)" }}>
          <Eyebrow style={{ color: "#FF8A3D" }}>🎬 Produce in AI Studio</Eyebrow>
          <div style={{ fontSize: 12, opacity: 0.5, margin: "6px 0 12px" }}>
            These content ideas are ready as AI Studio topics for this client. Runs are tagged to the project.
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {cur.strategy.content_ideas.map((t, i) => (
              <span key={i} style={{ fontSize: 12.5, padding: "7px 12px", borderRadius: 999,
                background: "rgba(255,138,61,0.12)", border: "1px solid rgba(255,138,61,0.3)" }}>🎥 {t}</span>
            ))}
          </div>
          <div className="mono" style={{ fontSize: 11, opacity: 0.5, marginTop: 12 }}>
            Run (Mac): <code>scripts/studio_from_project.py {cur.id} --generate</code>
          </div>
        </Panel>
      )}
    </div>
  );
}
