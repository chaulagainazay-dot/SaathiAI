"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchMissionDetail } from "@/lib/api";

const DEPT_COLOR = {
  ai_studio: "#FF8A3D", pielts: "#6C3FCF", travel: "#5FC8FF", hcg: "#FF5A5A", cafeteria: "#4FD07A",
};
const TEAL = "#00BFA5", AMBER = "#E8B84B", RED = "#FF5A5A";

export default function MissionDetail() {
  const { id } = useParams();
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { fetchMissionDetail(id).then(setD).catch((e) => setErr(String(e))); }, [id]);

  if (err) return <div className="only-desktop" style={{ padding: 40, opacity: 0.6 }}>{err}</div>;
  if (!d || !d.mission) return <div className="only-desktop" style={{ padding: 40, opacity: 0.5 }}>Loading mission…</div>;

  const m = d.mission;
  const color = DEPT_COLOR[m.department] || "#9B6BFF";
  const k = d.kpis;
  const pct = (x) => `${Math.round((x || 0) * 100)}%`;

  return (
    <div className="only-desktop" style={{ maxWidth: 1080, margin: "0 auto", paddingBottom: 60 }}>
      <a href="/missions" style={{ fontSize: 12, opacity: 0.5, textDecoration: "none", color: "inherit" }}>← Missions</a>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 8 }}>
        <div style={{ width: 12, height: 12, borderRadius: "50%", background: color }} />
        <div style={{ fontSize: 28, fontWeight: 600 }}>{m.name}</div>
        <span className="mono" style={{ fontSize: 11, padding: "2px 10px", borderRadius: 999,
          background: `${color}22`, color }}>{m.type}</span>
      </div>
      <div className="mono" style={{ fontSize: 11.5, opacity: 0.5, marginTop: 4 }}>
        {m.key} · {m.department} · {m.status}
      </div>

      {/* KPI strip */}
      <div style={{ display: "flex", gap: 12, margin: "18px 0", flexWrap: "wrap" }}>
        {[["Evidence", k.evidence], ["Events", k.events], ["Avg Confidence", pct(k.avg_confidence)],
          ["Cost", `$${k.cost}`], ["Pending Recs", k.pending_recommendations]].map(([lbl, v]) => (
          <div key={lbl} className="glass" style={{ padding: "12px 18px", borderRadius: 12, minWidth: 120 }}>
            <div style={{ fontSize: 22, fontWeight: 600, color }}>{v}</div>
            <div style={{ fontSize: 11, opacity: 0.55 }}>{lbl}</div>
          </div>
        ))}
      </div>

      {/* Business Digital Twin — Executive Strategist briefing + confidence + reports */}
      {d.twin && (
        <Panel style={{ padding: 18, marginBottom: 16, borderLeft: `3px solid ${color}` }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <Eyebrow style={{ color }}>Business Digital Twin · Executive Briefing</Eyebrow>
            <span className="mono" style={{ fontSize: 12 }}>
              Health <b style={{ color: (d.twin.briefing?.health || 0) >= 0.6 ? TEAL : AMBER }}>
                {pct(d.twin.briefing?.health)}</b>
              {"  ·  "}Confidence <b style={{ color: (d.twin.confidence?.overall || 0) >= 0.6 ? TEAL : AMBER }}>
                {pct(d.twin.confidence?.overall)}</b></span>
          </div>

          {/* confidence dimensions — how much we actually know */}
          {d.twin.confidence?.dimensions && (
            <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
              {Object.entries(d.twin.confidence.dimensions).map(([dim, v]) => (
                <div key={dim} style={{ fontSize: 10.5 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", opacity: 0.6 }}>
                    <span style={{ textTransform: "capitalize" }}>{dim}</span><span>{pct(v)}</span>
                  </div>
                  <div style={{ height: 4, borderRadius: 3, background: "rgba(255,255,255,0.07)", marginTop: 2 }}>
                    <div style={{ width: pct(v), height: "100%", borderRadius: 3,
                      background: v >= 0.6 ? TEAL : v > 0 ? AMBER : "rgba(255,255,255,0.1)" }} />
                  </div>
                </div>
              ))}
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, marginTop: 14 }}>
            <div>
              <div style={{ fontSize: 11, opacity: 0.5, color: RED }}>TOP RISKS</div>
              {(d.twin.briefing?.top_risks || []).map((s, i) => <div key={i} style={{ fontSize: 12.5, padding: "2px 0" }}>⚠ {s}</div>)}
              {(d.twin.briefing?.top_risks || []).length === 0 && <div style={{ fontSize: 12, opacity: 0.4 }}>none flagged</div>}
              <div style={{ fontSize: 11, opacity: 0.5, color: TEAL, marginTop: 8 }}>QUICK WINS</div>
              {(d.twin.briefing?.quick_wins || []).map((s, i) => <div key={i} style={{ fontSize: 12.5, padding: "2px 0" }}>✓ {s}</div>)}
            </div>
            <div>
              <div style={{ fontSize: 11, opacity: 0.5, color: AMBER }}>TOP OPPORTUNITIES</div>
              {(d.twin.briefing?.top_opportunities || []).map((s, i) => <div key={i} style={{ fontSize: 12.5, padding: "2px 0" }}>{i + 1}. {s}</div>)}
              <div style={{ fontSize: 11, opacity: 0.5, marginTop: 8 }}>ESTIMATED ROI</div>
              {Object.entries(d.twin.briefing?.roi || {}).map(([area, stars]) => (
                <div key={area} style={{ fontSize: 12.5, padding: "1px 0" }}>
                  {area} <span style={{ color: AMBER }}>{"★".repeat(stars)}{"☆".repeat(5 - stars)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* research reports summary */}
          {d.twin.reports && (
            <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap", fontSize: 11 }}>
              <span className="mono" style={{ padding: "3px 10px", borderRadius: 999, background: "rgba(255,255,255,0.06)" }}>
                SEO {d.twin.reports.seo?.score}/100 ({d.twin.reports.seo?.scope})</span>
              <span className="mono" style={{ padding: "3px 10px", borderRadius: 999, background: "rgba(255,255,255,0.06)" }}>
                Social {d.twin.reports.social?.count} channels</span>
              <span className="mono" style={{ padding: "3px 10px", borderRadius: 999, background: "rgba(255,255,255,0.06)" }}>
                Competitors {d.twin.reports.competitors?.count} {d.twin.reports.competitors?.gathered ? "" : "(source not wired)"}</span>
            </div>
          )}
          {d.twin.briefing?.biggest_revenue_opportunity && (
            <div style={{ marginTop: 10, fontSize: 12.5 }}>
              <span style={{ opacity: 0.5 }}>💰 Biggest revenue opportunity: </span>{d.twin.briefing.biggest_revenue_opportunity}
            </div>
          )}
          {/* departments */}
          <div style={{ fontSize: 11, opacity: 0.5, marginTop: 14 }}>DEPARTMENTS · {d.twin.template} template</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
            {(d.twin.departments || []).map((dep) => (
              <span key={dep} className="mono" style={{ fontSize: 10.5, padding: "3px 9px", borderRadius: 999,
                background: "rgba(255,255,255,0.06)" }}>{dep}</span>
            ))}
          </div>
          {/* roadmap — 30-day (weeks) + 90-day (months) */}
          <div style={{ fontSize: 11, opacity: 0.5, marginTop: 14 }}>30-DAY ROADMAP</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10, marginTop: 6 }}>
            {Object.entries(d.twin.roadmap?.["30-day"] || {}).map(([wk, items]) => (
              <div key={wk}>
                <div style={{ fontSize: 11.5, fontWeight: 600, color }}>{wk}</div>
                {(items || []).map((it, i) => <div key={i} style={{ fontSize: 11, opacity: 0.65, padding: "1px 0" }}>◦ {it}</div>)}
              </div>
            ))}
          </div>
          <div style={{ fontSize: 11, opacity: 0.5, marginTop: 12 }}>90-DAY PLAN</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginTop: 6 }}>
            {Object.entries(d.twin.roadmap?.["90-day"] || {}).map(([mo, items]) => (
              <div key={mo}>
                <div style={{ fontSize: 11.5, fontWeight: 600, color }}>{mo}</div>
                {(items || []).map((it, i) => <div key={i} style={{ fontSize: 11, opacity: 0.65, padding: "1px 0" }}>◦ {it}</div>)}
              </div>
            ))}
          </div>
        </Panel>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* identity + objectives + directors */}
        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color }}>Identity & Objectives</Eyebrow>
          <div style={{ marginTop: 10 }}>
            {Object.entries(m.identity || {}).map(([key, val]) => (
              <div key={key} style={{ fontSize: 12.5, padding: "3px 0", display: "flex", gap: 8 }}>
                <span style={{ opacity: 0.5, width: 90, textTransform: "capitalize" }}>{key}</span>
                <span>{String(val)}</span>
              </div>
            ))}
          </div>
          {m.objectives?.length > 0 && <>
            <div style={{ fontSize: 11, opacity: 0.5, marginTop: 12 }}>OBJECTIVES</div>
            {m.objectives.map((o, i) => <div key={i} style={{ fontSize: 12.5, padding: "2px 0" }}>◦ {o}</div>)}
          </>}
          {m.directors?.length > 0 && <>
            <div style={{ fontSize: 11, opacity: 0.5, marginTop: 12 }}>DIRECTORS</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
              {m.directors.map((dir) => (
                <span key={dir} className="mono" style={{ fontSize: 10.5, padding: "3px 9px", borderRadius: 999,
                  background: "rgba(255,255,255,0.06)" }}>{dir}</span>
              ))}
            </div>
          </>}
        </Panel>

        {/* learning recommendations for this mission */}
        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color }}>Learning · recommendations</Eyebrow>
          <div style={{ marginTop: 10 }}>
            {(d.recommendations || []).length === 0 && (
              <div style={{ fontSize: 12.5, opacity: 0.4 }}>No recommendations yet — evidence still accumulating.</div>
            )}
            {(d.recommendations || []).map((r) => (
              <div key={r.id} style={{ padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <span className="mono" style={{ fontSize: 9.5, padding: "1px 7px", borderRadius: 999,
                    background: r.priority === "high" ? `${RED}22` : `${AMBER}22`,
                    color: r.priority === "high" ? RED : AMBER }}>{r.priority}</span>
                  <span style={{ fontSize: 12, opacity: 0.5 }}>{r.affected_director}</span>
                  <span className="mono" style={{ marginLeft: "auto", fontSize: 10.5, color: TEAL }}>{pct(r.confidence)}</span>
                </div>
                <div style={{ fontSize: 12.5, marginTop: 3 }}>{r.problem}</div>
                <div style={{ fontSize: 12, opacity: 0.7, marginTop: 2 }}>→ {r.recommendation}</div>
              </div>
            ))}
          </div>
          <a href="/learning" style={{ fontSize: 11.5, color, textDecoration: "none", display: "inline-block", marginTop: 10 }}>
            open Learning inbox →</a>
        </Panel>

        {/* recent evidence */}
        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color }}>Recent Evidence</Eyebrow>
          <div style={{ marginTop: 10 }}>
            {(d.recent_evidence || []).map((e) => (
              <div key={e.id} style={{ display: "flex", gap: 8, padding: "4px 0", fontSize: 12,
                borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                <span style={{ flex: 1, opacity: 0.7 }}>{e.episode || "—"} · {e.director}</span>
                <span className="mono" style={{ opacity: 0.5, fontSize: 10.5 }}>{pct(e.confidence)}</span>
              </div>
            ))}
            {(d.recent_evidence || []).length === 0 && <div style={{ fontSize: 12.5, opacity: 0.4 }}>none yet</div>}
          </div>
        </Panel>

        {/* recent events */}
        <Panel style={{ padding: 18 }}>
          <Eyebrow style={{ color }}>Recent Events</Eyebrow>
          <div style={{ marginTop: 10 }}>
            {(d.recent_events || []).map((e) => (
              <div key={e.id} style={{ display: "flex", gap: 8, padding: "4px 0", fontSize: 12,
                borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                <span className="mono" style={{ color }}>{e.type}</span>
                <span style={{ flex: 1, opacity: 0.5 }}>{e.subject}</span>
              </div>
            ))}
            {(d.recent_events || []).length === 0 && <div style={{ fontSize: 12.5, opacity: 0.4 }}>none yet</div>}
          </div>
        </Panel>
      </div>

      {/* Timeline — the append-only business record */}
      <Panel style={{ padding: 18, marginTop: 16 }}>
        <Eyebrow style={{ color }}>Timeline · business history</Eyebrow>
        <div style={{ marginTop: 12 }}>
          {(d.timeline || []).map((t) => (
            <div key={t.id} style={{ display: "flex", gap: 10, padding: "6px 0",
              borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, marginTop: 5, flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12.5 }}>{t.title}</div>
                {t.detail && <div style={{ fontSize: 11, opacity: 0.5 }}>{t.detail}</div>}
              </div>
              <span className="mono" style={{ fontSize: 9.5, padding: "1px 7px", borderRadius: 999,
                background: "rgba(255,255,255,0.06)", height: "fit-content", opacity: 0.6 }}>{t.kind}</span>
              <span className="mono" style={{ fontSize: 10, opacity: 0.4, whiteSpace: "nowrap" }}>
                {new Date((t.timestamp || 0) * 1000).toLocaleDateString()}</span>
            </div>
          ))}
          {(d.timeline || []).length === 0 && <div style={{ fontSize: 12.5, opacity: 0.4 }}>no history yet</div>}
        </div>
      </Panel>
    </div>
  );
}
