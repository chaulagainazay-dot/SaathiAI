"use client";
/**
 * Live Market Tape — retro auto-scrolling observation tape (OBSERVATION-ONLY).
 * Feeds strictly from read-only sources: NEPSE live market snapshot (public) + owner
 * Financial Memory MARKET_OBSERVATION rows. Never fabricates trades: when there is no
 * per-symbol feed (e.g. market closed) it shows the real index strip + an honest
 * "○ NO FEED / MARKET CLOSED" status. No trading, no order controls.
 */
import { useEffect, useRef, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";

function api(p) {
  return afetch(`${API_BASE}${p}`, { cache: "no-store" })
    .then(async (r) => { try { return await r.json(); } catch { return {}; } })
    .catch(() => ({}));
}
function pctColor(v) {
  const n = parseFloat(v);
  if (isNaN(n)) return "var(--text-muted)";
  return n >= 0 ? "var(--status-success)" : "var(--status-danger)";
}

export default function MarketTape() {
  const [snap, setSnap] = useState(null);
  const [rows, setRows] = useState([]);
  const aliveRef = useRef(true);
  const pollRef = useRef(null);

  useEffect(() => {
    aliveRef.current = true;
    async function tick() {
      if (!aliveRef.current) return;
      const [live, mem] = await Promise.all([
        api("/api/v1/market/nepse/live"),
        api("/api/v1/finance/memory/latest?evidence_type=MARKET_OBSERVATION&limit=40"),
      ]);
      if (!aliveRef.current) return;
      setSnap(live && !live.error ? live : null);
      let rws = [];
      const lr = (live && (live.rows || live.symbols)) || [];
      if (Array.isArray(lr) && lr.length) {
        rws = lr.map((x) => ({ sym: x.symbol || x.sym, ltp: x.ltp ?? x.last ?? x.price,
                               chg: x.change_percent ?? x.pct ?? x.percent_change, src: "NEPSE LIVE" }));
      } else {
        const ev = (mem && mem.evidence) || [];
        rws = ev.map((e) => ({ sym: e.instrument_id || e.payload?.symbol || "—",
                               ltp: e.payload?.ltp, chg: null, src: e.source_type || "OBSERVED" }));
      }
      setRows(rws.filter((r) => r.sym));
      pollRef.current = setTimeout(tick, 15000);   // market data changes slowly (esp. closed)
    }
    tick();
    return () => { aliveRef.current = false; if (pollRef.current) clearTimeout(pollRef.current); };
  }, []);

  const closed = !snap || String(snap.market_status || "").toUpperCase() !== "OPEN";
  const idxChg = snap?.index_change_percent;
  const strip = snap ? [
    ["NEPSE", `${snap.nepse_index ?? "—"}`, idxChg],
    ["ADV", snap.advancers ?? "—", null],
    ["DEC", snap.decliners ?? "—", null],
    ["TURNOVER", snap.total_turnover ?? "—", null],
    ["VOLUME", snap.total_volume ?? "—", null],
  ] : [];

  return (
    <section className="retro-panel" style={{ borderRadius: 6, marginTop: 4, marginBottom: 18, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, padding: "12px 16px 10px",
                    borderBottom: "1px solid rgba(255,42,42,.14)", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 12, letterSpacing: ".32em", textTransform: "uppercase",
                     color: "var(--accent)", fontFamily: "var(--font-mono)" }} className="retro-glow">
          Live Market Tape
        </h2>
        <span style={{ fontSize: 10, letterSpacing: ".2em", color: "var(--text-disabled)", textTransform: "uppercase" }}>
          nepse · {snap?.data_class || "observed"}
        </span>
        <div style={{ flex: 1 }} />
        <span style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 10,
                       letterSpacing: ".2em", textTransform: "uppercase",
                       color: closed ? "var(--text-muted)" : "#ffd7d7" }}>
          <span className={closed ? "" : "retro-live"} style={closed ? {
            width: 8, height: 8, borderRadius: "50%", background: "var(--text-disabled)" } : undefined} />
          {closed ? (snap ? "Market closed · no feed" : "No feed") : "Streaming"}
        </span>
      </div>

      {/* real index strip — marquee (moving) */}
      {snap && (
        <div className="mtape-hstrip" style={{ padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,.04)" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 12.5, fontVariantNumeric: "tabular-nums" }}>
            {strip.map(([k, v, chg], i) => (
              <span key={i} style={{ marginRight: 34 }}>
                <span style={{ color: "var(--text-disabled)", letterSpacing: ".14em" }}>{k} </span>
                <span style={{ color: "var(--text-primary)" }}>{v}</span>
                {chg != null && <span style={{ color: pctColor(chg), marginLeft: 6 }}>
                  {parseFloat(chg) >= 0 ? "▲" : "▼"} {chg}%</span>}
              </span>
            ))}
          </span>
        </div>
      )}

      {/* per-symbol tape — auto-scroll when a real feed exists, else honest empty */}
      <div className="mtape" style={{ height: rows.length ? 220 : "auto" }}>
        {rows.length ? (
          <div className="mtape-track">
            {[...rows, ...rows].map((r, i) => {
              const up = r.chg == null ? null : parseFloat(r.chg) >= 0;
              return (
                <div className="mtape-row" key={i}>
                  <span style={{ fontSize: 11, color: up == null ? "var(--text-muted)" : (up ? "var(--status-success)" : "var(--status-danger)") }}>
                    {up == null ? "·" : (up ? "▲" : "▼")}
                  </span>
                  <span style={{ letterSpacing: ".06em" }}>{r.sym}</span>
                  <span style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{r.ltp ?? "—"}</span>
                  <span style={{ textAlign: "right", fontSize: 10, letterSpacing: ".14em",
                                 color: "var(--text-disabled)", textTransform: "uppercase" }}>{r.src}</span>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ padding: "18px 16px", fontSize: 12, color: "var(--text-muted)", letterSpacing: ".04em" }}>
            ○ No per-symbol feed — {snap ? "market is closed; showing last settled index above." :
              "awaiting owner-authorized observations (Read Portfolio populates market memory)."}
          </div>
        )}
      </div>
    </section>
  );
}
