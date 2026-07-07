"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchLibrary, importRepo, fetchReadingQueue } from "@/lib/api";

const ACCENT = "#3E7BFF", TEAL = "#00BFA5", RED = "#FF5A5A";

export default function KnowledgeLibrary() {
  const [d, setD] = useState(null);
  const [q, setQ] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [queue, setQueue] = useState([]);
  const load = (query = "") => fetchLibrary({ q: query }).then(setD).catch((e) => setErr(String(e)));
  useEffect(() => { load(); fetchReadingQueue().then((d) => setQueue(d.queue || [])).catch(() => {}); }, []);
  const stars = (n) => "★".repeat(n || 0) + "☆".repeat(5 - (n || 0));

  const doImport = async () => {
    if (!url.trim()) return;
    setBusy(true); setErr(null);
    try { const r = await importRepo(url); if (!r.ok) setErr(r.error || "import failed"); setUrl(""); load(); }
    catch (e) { setErr(`${e} — login may be required`); } finally { setBusy(false); }
  };

  if (!d) return <div className="page" style={{ padding: 40, opacity: 0.5 }}>{err || "Loading library…"}</div>;

  return (
    <div className="page" style={{ maxWidth: 940, margin: "0 auto", paddingBottom: 60 }}>
      <Eyebrow style={{ color: ACCENT }}>SaathiOS · Knowledge Library</Eyebrow>
      <div style={{ fontSize: 28, fontWeight: 600, margin: "4px 0 4px" }}>The learning source for every Director</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 16 }}>
        Books, GitHub repos, papers, docs, SOPs — ingested once, searchable by every Director across every Mission.
      </div>

      {/* search + import */}
      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load(q)}
          placeholder="Search sources (e.g. planning multi-agent, evaluation)…"
          style={{ flex: 1, minWidth: 240, padding: "10px 14px", borderRadius: 10, fontSize: 13,
            border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)", color: "inherit" }} />
        <button onClick={() => load(q)} style={{ padding: "0 18px", borderRadius: 10, border: "none",
          cursor: "pointer", fontWeight: 600, color: "#fff", background: ACCENT }}>Search</button>
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input value={url} onChange={(e) => setUrl(e.target.value)}
          placeholder="Import GitHub repo URL (reads the real README)…"
          style={{ flex: 1, padding: "9px 12px", borderRadius: 10, fontSize: 12.5,
            border: "1px dashed rgba(62,123,255,0.4)", background: "transparent", color: "inherit" }} />
        <button onClick={doImport} disabled={busy} style={{ padding: "0 16px", borderRadius: 10, border: `1px solid ${ACCENT}`,
          cursor: "pointer", fontWeight: 600, color: ACCENT, background: "transparent", opacity: busy ? 0.6 : 1 }}>
          {busy ? "Importing…" : "＋ Import"}</button>
      </div>
      {err && <div style={{ fontSize: 12, color: RED, marginBottom: 10 }}>{err}</div>}

      {/* reading queue — the AI-engineering curriculum backlog */}
      {queue.length > 0 && (
        <Panel style={{ padding: 14, marginBottom: 14, borderLeft: "3px solid #E8B84B" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <Eyebrow style={{ color: "#E8B84B" }}>Reading Queue · curriculum</Eyebrow>
            <span className="mono" style={{ fontSize: 11, opacity: 0.5 }}>
              {queue.filter((q) => q.status === "imported").length}/{queue.length} imported</span>
          </div>
          <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 3 }}>
            {queue.slice(0, 12).map((q) => (
              <div key={q.id} style={{ display: "flex", gap: 8, fontSize: 12, alignItems: "center" }}>
                <span style={{ color: "#E8B84B", fontSize: 10 }}>{stars(q.priority)}</span>
                <span style={{ flex: 1, opacity: q.status === "imported" ? 0.5 : 0.85 }}>
                  {q.status === "imported" ? "✓ " : "○ "}{q.title}</span>
                <span className="mono" style={{ fontSize: 10, opacity: 0.4 }}>{q.category}</span>
                {q.url && q.status !== "imported" && (
                  <button onClick={() => { setUrl(q.url); }} style={{ fontSize: 10, padding: "2px 8px",
                    borderRadius: 6, cursor: "pointer", border: `1px solid ${ACCENT}66`, background: "transparent", color: ACCENT }}>
                    load ↑</button>)}
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* categories */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        {Object.entries(d.categories || {}).map(([cat, n]) => (
          <span key={cat} className="mono" style={{ fontSize: 11, padding: "4px 11px", borderRadius: 999,
            background: `${ACCENT}18`, color: ACCENT }}>{cat} · {n}</span>
        ))}
      </div>

      {/* sources */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {(d.sources || []).length === 0 && <div style={{ opacity: 0.4, fontSize: 13 }}>no sources match</div>}
        {(d.sources || []).map((s) => (
          <Panel key={s.id} style={{ padding: 16, borderLeft: `3px solid ${ACCENT}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <div style={{ fontSize: 15, fontWeight: 600 }}>{s.title}</div>
              <span className="mono" style={{ fontSize: 10, opacity: 0.5 }}>{s.source_type} · {s.difficulty}</span>
            </div>
            <div style={{ display: "flex", gap: 12, marginTop: 4, fontSize: 11, alignItems: "center" }}>
              <span title="trust" style={{ color: "#E8B84B" }}>{stars(s.trust)}</span>
              <span className="mono" style={{ padding: "2px 8px", borderRadius: 999,
                background: s.status === "director_ready" ? `${TEAL}22` : "rgba(255,255,255,0.06)",
                color: s.status === "director_ready" ? TEAL : "inherit" }}>{s.status}</span>
              {s.influence > 0 && <span style={{ opacity: 0.55 }}>influenced {s.influence} report{s.influence === 1 ? "" : "s"}</span>}
            </div>
            <div className="mono" style={{ fontSize: 10.5, opacity: 0.5, marginTop: 2 }}>
              {s.author}{s.category ? ` · ${s.category}` : ""}{s.url ? " · " : ""}
              {s.url && <a href={s.url} target="_blank" rel="noreferrer" style={{ color: ACCENT }}>source ↗</a>}
            </div>
            {s.summary && <div style={{ fontSize: 12.5, opacity: 0.8, marginTop: 8 }}>{s.summary}</div>}
            {s.tags?.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
                {s.tags.map((t) => <span key={t} className="mono" style={{ fontSize: 10, padding: "2px 8px",
                  borderRadius: 999, background: "rgba(255,255,255,0.06)" }}>{t}</span>)}
              </div>
            )}
            <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 11 }}>
              {s.related_directors?.length > 0 && <div style={{ opacity: 0.6 }}>
                useful for: <b style={{ color: TEAL }}>{s.related_directors.join(", ")}</b></div>}
            </div>
            {s.key_lessons?.length > 0 && (
              <div style={{ marginTop: 6, fontSize: 11.5, opacity: 0.7 }}>
                {s.key_lessons.slice(0, 6).map((l, i) => <div key={i}>· {l}</div>)}
              </div>
            )}
          </Panel>
        ))}
      </div>
    </div>
  );
}
