"use client";
import { useState, useEffect } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchProjects, createProject, fetchProject, updateProject, researchProject } from "@/lib/api";

const PURPLE = "#6C3FCF", TEAL = "#00BFA5";
const field = { width: "100%", padding: "10px 12px", borderRadius: 10, fontSize: 14, marginTop: 6,
  border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)", color: "inherit" };
const dot = (s) => ({ ready: TEAL, submitted: "#E8B84B", researching: "#8FB4FF", draft: "#8B98B4" }[s] || "#8B98B4");

const JOURNEY = [["Capture","📋"],["Research","🔎"],["Analyze","📊"],["Strategy","🎯"],["Roadmap","🗺️"],["Plan","🗓️"],["Execute","🚀"]];
const WHATYOUGET = [["Research Report","Company, industry, competitors & audience"],
  ["Strategic Direction","Positioning, value prop, goals"],["Roadmap & Timeline","Phased plan with milestones"],
  ["Content & Channel Plan","Pillars, calendar & channels"],["Execution Ready","Organized in SaathiAI"]];
const DELIVERABLES = ["Research Report","Strategy Document","Roadmap Timeline","Content Calendar",
  "Competitor Analysis","Website Mockup","Ad Campaign Plan","Monthly Reports"];

function L({ label, children }) {
  return <label style={{ display: "block", fontSize: 12, opacity: 0.6 }}>{label}{children}</label>;
}
function Chips({ title, items, color }) {
  if (!items?.length) return null;
  return <div style={{ marginTop: 12 }}>
    <div style={{ fontSize: 11, opacity: 0.5, marginBottom: 6 }}>{title}</div>
    {items.map((x, i) => <div key={i} style={{ fontSize: 13, padding: "3px 0", color: color || "inherit" }}>• {typeof x === "string" ? x : (x.name || JSON.stringify(x))}</div>)}
  </div>;
}

export default function Projects() {
  const [projects, setProjects] = useState([]);
  const [cur, setCur] = useState(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const load = () => fetchProjects().then((d) => setProjects(d.projects || [])).catch(() => {});
  useEffect(() => { load(); }, []);

  const open = (id) => fetchProject(id).then(setCur).catch(() => {});
  const startNew = async () => { const p = await createProject({}); setCur(p); load(); };
  const setField = (path, value) => setCur((c) => {
    const d = { ...c.data };
    if (path.length === 2) d[path[0]] = { ...(d[path[0]] || {}), [path[1]]: value }; else d[path[0]] = value;
    return { ...c, data: d };
  });
  const save = async () => { setBusy(true); try { const p = await updateProject(cur.id, cur.data); setCur({ ...p, share_url: cur.share_url }); load(); } finally { setBusy(false); } };
  const runResearch = async () => { setBusy(true); try { const p = await researchProject(cur.id); setCur({ ...p, share_url: cur.share_url }); load(); } finally { setBusy(false); } };

  // ── LIST ──
  if (!cur) return (
    <div style={{ maxWidth: 1040, margin: "0 auto", padding: "0 4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 18 }}>
        <div>
          <Eyebrow style={{ color: PURPLE }}>Projects</Eyebrow>
          <div style={{ fontSize: 26, fontWeight: 700, marginTop: 4 }}>Create New Project</div>
          <div style={{ fontSize: 13, opacity: 0.5 }}>From client info to clear direction. All in one smart flow.</div>
        </div>
        <button onClick={startNew} style={{ padding: "10px 20px", borderRadius: 12, border: "none",
          cursor: "pointer", fontWeight: 600, color: "#fff", background: PURPLE }}>+ Create Project</button>
      </div>

      {/* the complete journey */}
      <Panel style={{ padding: 16, marginBottom: 16 }}>
        <Eyebrow style={{ color: PURPLE }}>The Complete Journey</Eyebrow>
        <div style={{ display: "flex", gap: 6, marginTop: 12, flexWrap: "wrap", alignItems: "center" }}>
          {JOURNEY.map(([label, icon], i) => (
            <div key={label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ textAlign: "center", minWidth: 74 }}>
                <div style={{ fontSize: 20 }}>{icon}</div>
                <div style={{ fontSize: 11, opacity: 0.7 }}>{label}</div>
              </div>
              {i < JOURNEY.length - 1 && <span style={{ opacity: 0.3 }}>→</span>}
            </div>
          ))}
        </div>
      </Panel>

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
                  {(p.data.company?.industry) || "—"} · {p.strategy ? "strategy ready" : p.status === "submitted" ? "client submitted — review" : "awaiting research"}
                </div>
              </Panel>
            ))}
          </div>}

      {/* what you get */}
      <div style={{ fontSize: 13, opacity: 0.6, margin: "22px 0 10px" }}>What You Get After Submission</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12 }}>
        {WHATYOUGET.map(([t, d]) => (
          <Panel key={t} style={{ padding: 14 }}>
            <div style={{ fontSize: 13.5, fontWeight: 600 }}>{t}</div>
            <div style={{ fontSize: 11.5, opacity: 0.5, marginTop: 4 }}>{d}</div>
          </Panel>
        ))}
      </div>
      <div style={{ fontSize: 13, opacity: 0.6, margin: "22px 0 10px" }}>Deliverables You Will Receive</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {DELIVERABLES.map((d) => <span key={d} style={{ fontSize: 12, padding: "6px 12px", borderRadius: 999,
          background: "rgba(108,63,207,0.1)", border: "1px solid rgba(108,63,207,0.3)" }}>📄 {d}</span>)}
      </div>
    </div>
  );

  // ── WORKSPACE ──
  const co = cur.data.company || {};
  const R = cur.research || {}, S = cur.strategy || {};
  return (
    <div style={{ maxWidth: 1040, margin: "0 auto", padding: "0 4px" }}>
      <button onClick={() => setCur(null)} style={{ background: "none", border: "none", color: "inherit", opacity: 0.6, cursor: "pointer", fontSize: 13, marginBottom: 12 }}>← All projects</button>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
        <div style={{ fontSize: 22, fontWeight: 600 }}>{cur.name}</div>
        <span style={{ fontSize: 12, color: dot(cur.status) }}>● {cur.status}</span>
      </div>

      {cur.status === "submitted" && (
        <Panel style={{ padding: 12, marginBottom: 14, border: "1px solid rgba(232,184,75,0.4)", background: "rgba(232,184,75,0.08)" }}>
          <span style={{ fontSize: 13 }}>✅ Your client submitted this form. Review the details below, then <b>Run AI Research</b>.</span>
        </Panel>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 16 }}>
        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color: PURPLE }}>Company Information</Eyebrow>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
            {[["Company Name","name"],["Website","website"],["Industry / Niche","industry"],["Location","location"],["Contact Person","contact"],["Email","email"],["Phone","phone"],["Founded Year","founded"]].map(([lab,k]) => (
              <L key={k} label={lab}><input style={field} value={co[k] || ""} onChange={(e) => setField(["company",k], e.target.value)} /></L>
            ))}
          </div>
          <L label="Company Description"><textarea style={{ ...field, minHeight: 56 }} value={co.description || cur.data.description || ""} onChange={(e) => setField(["company","description"], e.target.value)} /></L>
          <Eyebrow style={{ color: PURPLE, marginTop: 18, display: "block" }}>Goals · Audience · Services · Budget</Eyebrow>
          {[["Goals","goals"],["Target Audience","audience"],["Services","services"]].map(([lab,k]) => (
            <L key={k} label={lab}><textarea style={{ ...field, minHeight: 44 }} value={cur.data[k] || ""} onChange={(e) => setField([k], e.target.value)} /></L>
          ))}
          <L label="Budget & Timeline"><input style={field} value={cur.data.budget || ""} onChange={(e) => setField(["budget"], e.target.value)} /></L>
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button onClick={save} disabled={busy} style={{ padding: "10px 18px", borderRadius: 10, border: "1px solid rgba(255,255,255,0.15)", background: "transparent", color: "inherit", cursor: "pointer" }}>Save</button>
            <button onClick={runResearch} disabled={busy} style={{ padding: "10px 18px", borderRadius: 10, border: "none", fontWeight: 600, color: "#fff", background: PURPLE, cursor: "pointer" }}>{busy ? "Researching…" : "⚡ Run AI Research"}</button>
          </div>
        </Panel>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Panel style={{ padding: 16 }}>
            <Eyebrow>Smart Form — share with client</Eyebrow>
            <div style={{ fontSize: 11, opacity: 0.5, margin: "6px 0 10px" }}>Send this link; the client fills it, you get structured data.</div>
            <input readOnly value={cur.share_url || ""} style={{ ...field, fontSize: 11, marginTop: 0 }} />
            <button onClick={() => { navigator.clipboard?.writeText(cur.share_url || ""); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
              style={{ width: "100%", marginTop: 8, padding: "10px", borderRadius: 10, border: "none", fontWeight: 600, color: "#fff", background: copied ? TEAL : PURPLE, cursor: "pointer" }}>{copied ? "✓ Copied" : "Copy Link"}</button>
            {cur.share_url && <a href={cur.share_url} target="_blank" rel="noreferrer" style={{ display: "block", textAlign: "center", marginTop: 8, fontSize: 12, color: TEAL }}>↗ Open client form</a>}
          </Panel>
        </div>
      </div>

      {/* rich research + strategy output */}
      {cur.strategy && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: 16, marginTop: 16 }}>
          <Panel style={{ padding: 18 }}>
            <Eyebrow style={{ color: TEAL }}>Research Output</Eyebrow>
            {R.website && (
              <div style={{ fontSize: 11.5, opacity: 0.6, marginTop: 8, padding: "8px 10px", borderRadius: 8, background: "rgba(0,191,165,0.08)" }}>
                {R.website.ok
                  ? <>🌐 Live site crawled: <b>{R.website.title || R.website.url}</b>
                      {R.socials_found?.length > 0 && <> · socials: {R.socials_found.join(", ")}</>}</>
                  : <>🌐 Site not reachable ({R.website.error?.slice(0, 40)})</>}
              </div>
            )}
            <p style={{ fontSize: 13.5, opacity: 0.85, marginTop: 8 }}>{R.company_overview || R.summary}</p>
            <Chips title="Strengths" items={R.strengths} color="#8FE0A8" />
            <Chips title="Areas to Improve" items={R.areas_to_improve} color="#FF9B9B" />
            <Chips title="Top Competitors" items={R.competitors} />
            <Chips title="Market Opportunity" items={R.market_opportunity} color={TEAL} />
          </Panel>
          <Panel style={{ padding: 18 }}>
            <Eyebrow style={{ color: PURPLE }}>Strategic Direction</Eyebrow>
            <p style={{ fontSize: 13.5, opacity: 0.85, marginTop: 8 }}>{S.direction}</p>
            <Chips title="Content Ideas" items={S.content_ideas} />
            {S.marketing_plan && <div style={{ marginTop: 12 }}><div style={{ fontSize: 11, opacity: 0.5 }}>Marketing Plan</div><div style={{ fontSize: 13, opacity: 0.85 }}>{S.marketing_plan}</div></div>}
            {S.channels?.length > 0 && <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 11, opacity: 0.5, marginBottom: 6 }}>Recommended Channels</div>
              {S.channels.map((c, i) => <div key={i} style={{ fontSize: 13, padding: "2px 0" }}>📡 <b>{c.name || c}</b>{c.why ? <span style={{ opacity: 0.55 }}> — {c.why}</span> : ""}</div>)}
            </div>}
          </Panel>
          {S.roadmap?.length > 0 && (
            <Panel style={{ padding: 18, gridColumn: "1 / -1" }}>
              <Eyebrow style={{ color: PURPLE }}>Roadmap</Eyebrow>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12, marginTop: 12 }}>
                {S.roadmap.map((ph, i) => (
                  <div key={i} style={{ padding: 12, borderRadius: 10, background: "rgba(255,255,255,0.03)", borderLeft: `3px solid ${["#6C3FCF","#8FB4FF","#00BFA5","#E8B84B","#FF7A5A"][i % 5]}` }}>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{ph.phase}</div>
                    <div style={{ fontSize: 10.5, opacity: 0.5, marginBottom: 6 }}>{ph.focus || ph.timeframe}</div>
                    {(ph.items || []).map((it, j) => <div key={j} style={{ fontSize: 12, padding: "2px 0", opacity: 0.85 }}>✓ {it}</div>)}
                  </div>
                ))}
              </div>
            </Panel>
          )}
        </div>
      )}
    </div>
  );
}
