"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { controlOverview, controlSearch } from "@/lib/api";

const ACCENT = "#7CF5E4", TEAL = "#00BFA5", AMBER = "#E8B84B", RED = "#FF5A5A", GREY = "#8890A0";
const SEV = { critical: RED, high: AMBER, medium: AMBER, info: GREY };
const STATUS = { ok: TEAL, degraded: AMBER, unavailable: RED };

function age(cell) {
  if (!cell || cell.age_sec == null) return "";
  return `${Math.round(cell.age_sec)}s ago`;
}

export default function ControlCenter() {
  const [ov, setOv] = useState(null);
  const [err, setErr] = useState(null);
  const [authed, setAuthed] = useState(true);
  const [q, setQ] = useState("");
  const [results, setResults] = useState(null);

  const load = () => controlOverview().then(setOv).catch((e) => { setErr(String(e)); setAuthed(false); });
  useEffect(() => {
    load();
    const iv = setInterval(() => { if (!document.hidden) load(); }, 30000); // bounded refresh, paused when hidden
    return () => clearInterval(iv);
  }, []);

  const doSearch = async (e) => {
    e.preventDefault();
    if (!q.trim()) return setResults(null);
    try { setResults(await controlSearch(q)); } catch (er) { setErr(String(er)); }
  };

  const sec = ov?.security?.value, rel = ov?.release_readiness?.value, health = ov?.platform_health?.value;

  return (
    <div className="page" style={{ maxWidth: 1080, margin: "0 auto", paddingBottom: 60 }}>
      <Eyebrow style={{ color: ACCENT }}>SaathiOS · Control Center (M16)</Eyebrow>
      <div style={{ fontSize: 28, fontWeight: 600, margin: "4px 0" }}>Control Center</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 16 }}>
        One command layer over the real platform. Read-only aggregation with source + freshness;
        every action routes through its canonical subsystem. Honest when a source is unavailable.
      </div>

      {!authed && (
        <Panel style={{ padding: 14, marginBottom: 14, border: "1px solid rgba(232,184,75,0.4)" }}>
          <div style={{ fontSize: 13, color: AMBER }}>⚠ Sign in to view the Control Center.</div>
        </Panel>
      )}
      {err && <div style={{ fontSize: 12, color: RED, marginBottom: 10 }}>{err}</div>}

      {/* global search */}
      <form onSubmit={doSearch} style={{ marginBottom: 16 }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search connectors · operations · accounts · approvals · executions"
          style={{ width: "100%", padding: "10px 13px", borderRadius: 10, fontSize: 13,
            border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)", color: "inherit" }} />
      </form>
      {results && (
        <Panel style={{ padding: 14, marginBottom: 16 }}>
          <Eyebrow style={{ color: ACCENT }}>Results · {results.total}</Eyebrow>
          {results.results.length === 0 && <div style={{ fontSize: 12.5, opacity: 0.4, marginTop: 6 }}>no matches</div>}
          {results.results.map((r, i) => (
            <div key={i} style={{ display: "flex", gap: 8, padding: "6px 0", fontSize: 12.5, borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
              <span className="mono" style={{ opacity: 0.5, minWidth: 90 }}>{r.entity_type}</span>
              <b>{r.title}</b><span style={{ opacity: 0.5 }}>{r.summary}</span>
              <span className="mono" style={{ marginLeft: "auto", opacity: 0.4 }}>{Math.round(r.relevance * 100)}%</span>
            </div>
          ))}
        </Panel>
      )}

      {ov == null && <div style={{ fontSize: 12.5, opacity: 0.4 }}>loading…</div>}

      {ov && (
        <>
          {/* requires attention */}
          <Panel style={{ padding: 16, marginBottom: 16 }}>
            <Eyebrow style={{ color: ACCENT }}>Requires attention · {ov.requires_attention.length}</Eyebrow>
            {ov.requires_attention.length === 0 && <div style={{ fontSize: 12.5, opacity: 0.4, marginTop: 8 }}>all clear</div>}
            {ov.requires_attention.map((a, i) => (
              <a key={i} href={a.link} style={{ display: "flex", gap: 8, alignItems: "center", padding: "8px 0",
                borderBottom: "1px solid rgba(255,255,255,0.05)", textDecoration: "none", color: "inherit" }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: SEV[a.severity] || GREY }} />
                <span className="mono" style={{ fontSize: 10.5, opacity: 0.5, minWidth: 70 }}>{a.severity}</span>
                <span style={{ fontSize: 13 }}>{a.message}</span>
                <span className="mono" style={{ marginLeft: "auto", fontSize: 10.5, color: ACCENT }}>{a.kind} →</span>
              </a>
            ))}
          </Panel>

          {/* platform health cells with source + freshness */}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
            {[["Security", sec?.verdict, ov.security],
              ["Release gate", rel ? (rel.exit_code === 0 ? "passing" : `exit ${rel.exit_code}`) : "—", ov.release_readiness],
              ["Connectors", health ? `${health.total} · ${(health.summary || {})["live-tested"] || 0} live` : "—", ov.platform_health],
              ["Pending approvals", (ov.pending_approvals.value || []).length, ov.pending_approvals]]
              .map(([k, v, cell]) => (
              <div key={k} className="glass" style={{ padding: "12px 18px", borderRadius: 12, minWidth: 170 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 7, height: 7, borderRadius: "50%", background: STATUS[cell.status] || GREY }} />
                  <div style={{ fontSize: 11, opacity: 0.55 }}>{k}</div>
                </div>
                <div style={{ fontSize: 18, fontWeight: 600, color: ACCENT, marginTop: 4 }}>
                  {cell.status === "unavailable" ? "unavailable" : String(v)}</div>
                <div className="mono" style={{ fontSize: 9.5, opacity: 0.4 }}>{cell.source} · {age(cell)}</div>
              </div>
            ))}
          </div>

          {/* recent timeline */}
          <Panel style={{ padding: 16 }}>
            <Eyebrow style={{ color: ACCENT }}>Recent activity</Eyebrow>
            {(ov.recent_timeline.value || []).length === 0 && <div style={{ fontSize: 12.5, opacity: 0.4, marginTop: 8 }}>no recent events</div>}
            {(ov.recent_timeline.value || []).map((e, i) => (
              <div key={i} style={{ display: "flex", gap: 8, padding: "6px 0", fontSize: 12, borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                <span className="mono" style={{ opacity: 0.6 }}>{e.type}</span>
                <span className="mono" style={{ opacity: 0.4 }}>{e.source}</span>
                {e.summary && <span style={{ opacity: 0.6 }}>{e.summary}</span>}
              </div>
            ))}
            {ov.degraded_sources.length > 0 && (
              <div style={{ fontSize: 11, color: AMBER, marginTop: 10 }}>
                ⚠ degraded sources: {ov.degraded_sources.join(", ")} — shown honestly, not hidden.
              </div>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
