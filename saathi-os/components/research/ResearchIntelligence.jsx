"use client";
// Central Command — Research Intelligence tile. READ-ONLY. Renders the backend
// research projection (overview, events by RESEARCH_PRIORITY, source health,
// daily brief). All authority/clustering/reconciliation lives in the backend;
// this component only presents. No execution or order controls of any kind.
import { useCallback, useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";

const R = (p) => `${API_BASE}/api/v1/research${p}`;

const FRESH_LABEL = {
  REALTIME: "real-time", NEAR_REALTIME: "near real-time", TODAY: "today",
  RECENT: "recent", STALE: "stale", UNKNOWN: "date unknown",
};
const HEALTH_TEXT = {
  AVAILABLE: "available", DEGRADED: "degraded", SCHEMA_CHANGED: "schema changed",
  TOKEN_FLOW_CHANGED: "token flow changed", UNAVAILABLE: "unavailable", UNKNOWN: "unknown",
};

async function getJSON(url) {
  const r = await afetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export default function ResearchIntelligence() {
  const [state, setState] = useState("LOADING"); // LOADING|OK|EMPTY|DEGRADED|ERROR
  const [intel, setIntel] = useState(null);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);

  const load = useCallback(async () => {
    setState("LOADING");
    try {
      const data = await getJSON(R("/intelligence"));
      setIntel(data);
      const health = data.source_health || {};
      const anyDegraded = Object.values(health).some(
        (h) => h && h.status && !["AVAILABLE", "UNKNOWN"].includes(h.status));
      if (!data.overview || data.state === "EMPTY") setState("EMPTY");
      else setState(anyDegraded ? "DEGRADED" : "OK");
    } catch (e) {
      setState("ERROR");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openEvent = useCallback(async (id) => {
    setSelected(id); setDetail(null);
    try { setDetail(await getJSON(R(`/events/${id}`))); }
    catch { setDetail({ error: "EVENT_NOT_FOUND" }); }
  }, []);

  if (state === "LOADING")
    return <section className="ri" aria-busy="true"><p className="ri-msg">Research intelligence loading…</p></section>;
  if (state === "ERROR")
    return (
      <section className="ri">
        <p className="ri-msg ri-err" role="alert">Unable to retrieve research intelligence.</p>
        <button className="ri-btn" onClick={load}>Retry</button>
      </section>
    );

  const ov = intel?.overview || {};
  const health = intel?.source_health || {};
  const events = intel?.latest_events || [];

  return (
    <section className="ri" aria-label="Research intelligence">
      <header className="ri-head">
        <h2>Research Intelligence</h2>
        <button className="ri-btn" onClick={load} aria-label="Refresh research intelligence">Refresh</button>
      </header>

      {state === "DEGRADED" && (
        <p className="ri-note" role="status">Research intelligence is available with source limitations.</p>
      )}
      {state === "EMPTY" ? (
        <p className="ri-msg">No supported research evidence is currently available.</p>
      ) : (
        <>
          <ul className="ri-overview">
            <li><b>{ov.events ?? 0}</b> official events</li>
            <li><b>{ov.new_today ?? 0}</b> new today</li>
            <li><b>{ov.official_events ?? 0}</b> official-source</li>
            <li><b>{ov.contradictions ?? 0}</b> contradictions</li>
            <li><b>{ov.documents ?? 0}</b> documents</li>
          </ul>

          <ul className="ri-health" aria-label="Source health">
            {["nepse", "sebon", "nrb", "documents"].map((k) => {
              const s = (health[k] && health[k].status) || "UNKNOWN";
              return (
                <li key={k} data-status={s}>
                  <span className="ri-src">{k.toUpperCase()}</span>
                  <span className="ri-stat">{HEALTH_TEXT[s] || s}</span>
                  {health[k]?.token_gated_note && (
                    <span className="ri-tg">{health[k].token_gated_note}</span>
                  )}
                </li>
              );
            })}
          </ul>

          <ol className="ri-events">
            {events.map((e) => (
              <li key={e.event_id ?? e.headline}>
                <button className="ri-event" onClick={() => openEvent(e.event_id)}
                        aria-expanded={selected === e.event_id}>
                  <span className="ri-etype">{e.type?.replace(/_/g, " ")}</span>
                  {e.symbol ? <span className="ri-sym">{e.symbol}</span> : null}
                  <span className="ri-hl">{e.headline}</span>
                  <span className="ri-meta">
                    {e.date || "—"} · {e.authority?.replace(/_/g, " ").toLowerCase()} ·{" "}
                    {FRESH_LABEL[e.freshness] || e.freshness} · {e.evidence_count} evidence
                    {e.portfolio_relevant ? " · portfolio-relevant" : ""}
                  </span>
                </button>
                {selected === e.event_id && detail && (
                  <div className="ri-detail">
                    {detail.error ? <p>Event not found.</p> : (
                      <>
                        <p className="ri-sum">{detail.summary || detail.headline}</p>
                        <dl>
                          <dt>Confidence</dt><dd>{detail.confidence}</dd>
                          <dt>Freshness</dt><dd>{FRESH_LABEL[detail.freshness] || detail.freshness}</dd>
                          <dt>Source authority</dt><dd>{detail.source_tier?.replace(/_/g, " ")}</dd>
                          <dt>Evidence</dt><dd>{(detail.evidence_refs || []).length} reference(s)</dd>
                          <dt>Documents</dt><dd>{(detail.document_refs || []).length}</dd>
                          {detail.contradiction_state !== "NONE" && (
                            <><dt>Contradiction</dt><dd>{detail.contradiction_note || detail.contradiction_state}</dd></>
                          )}
                        </dl>
                      </>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
