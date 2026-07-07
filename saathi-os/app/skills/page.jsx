"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchSkills } from "@/lib/api";

const ACCENT = "#22D3EE", GOLD = "#E8B84B", TEAL = "#00BFA5";

export default function SkillLibrary() {
  const [d, setD] = useState(null);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [err, setErr] = useState(null);
  const load = (query = "", category = "") => fetchSkills({ q: query, category }).then(setD).catch((e) => setErr(String(e)));
  useEffect(() => { load(); }, []);
  const stars = (n) => "★".repeat(n || 0) + "☆".repeat(5 - (n || 0));

  if (!d) return <div className="page" style={{ padding: 40, opacity: 0.5 }}>{err || "Loading skills…"}</div>;

  return (
    <div className="page" style={{ maxWidth: 940, margin: "0 auto", paddingBottom: 60 }}>
      <Eyebrow style={{ color: ACCENT }}>SaathiOS · Skill Library</Eyebrow>
      <div style={{ fontSize: 28, fontWeight: 600, margin: "4px 0 4px" }}>Reusable skills every Director can call</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 16 }}>
        Named, versioned capabilities with a clear interface (inputs → outputs). One skill, many Directors, every Mission.
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load(q, cat)}
          placeholder="Search skills (e.g. seo, proposal, band)…"
          style={{ flex: 1, minWidth: 220, padding: "10px 14px", borderRadius: 10, fontSize: 13,
            border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)", color: "inherit" }} />
        <button onClick={() => load(q, cat)} style={{ padding: "0 18px", borderRadius: 10, border: "none",
          cursor: "pointer", fontWeight: 600, color: "#000", background: ACCENT }}>Search</button>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        <button onClick={() => { setCat(""); load(q, ""); }} style={chip(!cat)}>All</button>
        {Object.entries(d.categories || {}).map(([c, n]) => (
          <button key={c} onClick={() => { setCat(c); load(q, c); }} style={chip(cat === c)}>{c} · {n}</button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {(d.skills || []).map((s) => (
          <Panel key={s.id} style={{ padding: 16, borderLeft: `3px solid ${ACCENT}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <div style={{ fontSize: 15, fontWeight: 600 }}>{s.name}</div>
              <span className="mono" style={{ fontSize: 10, opacity: 0.5 }}>v{s.version}</span>
            </div>
            <div className="mono" style={{ fontSize: 10.5, opacity: 0.5, marginTop: 2 }}>
              {s.category} · owner: <b style={{ color: TEAL }}>{s.owner_director}</b> · <span style={{ color: GOLD }}>{stars(s.trust)}</span>
            </div>
            {s.description && <div style={{ fontSize: 12.5, opacity: 0.8, marginTop: 8 }}>{s.description}</div>}
            <div className="mono" style={{ fontSize: 11, marginTop: 8, lineHeight: 1.7 }}>
              <span style={{ opacity: 0.5 }}>in:</span> {(s.inputs || []).join(", ") || "—"}<br />
              <span style={{ opacity: 0.5 }}>out:</span> <b style={{ color: TEAL }}>{(s.outputs || []).join(", ") || "—"}</b>
            </div>
            {s.related_directors?.length > 0 && (
              <div style={{ fontSize: 10.5, opacity: 0.55, marginTop: 8 }}>
                callable by: {s.related_directors.join(", ")}</div>
            )}
          </Panel>
        ))}
        {(d.skills || []).length === 0 && <div style={{ opacity: 0.4, fontSize: 13 }}>no skills match</div>}
      </div>
    </div>
  );
}

const chip = (active) => ({
  padding: "6px 12px", borderRadius: 999, cursor: "pointer", fontSize: 12, fontWeight: 600,
  border: `1px solid ${active ? "#22D3EE" : "#22D3EE44"}`, background: active ? "#22D3EE22" : "transparent",
  color: active ? "#22D3EE" : "inherit",
});
