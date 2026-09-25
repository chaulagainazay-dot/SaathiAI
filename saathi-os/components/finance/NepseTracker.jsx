"use client";
/**
 * NEPSE Tracker — index + breadth (licensed snapshot when available), free-source movers,
 * and the full live market table. Observation-only.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { useNepseUniverse } from "@/lib/useNepseUniverse";
import { Badge, Text, Spinner } from "@/components/ui";

function api(path) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store" }).then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, body: b }; });
}
const numOr = (v) => { const n = typeof v === "number" ? v : parseFloat(String(v ?? "").replace(/,/g, "")); return Number.isFinite(n) ? n : null; };

export default function NepseTracker() {
  const uni = useNepseUniverse();
  const [nepse, setNepse] = useState(null);
  const [movers, setMovers] = useState(null);
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    const [n, m] = await Promise.all([api("/api/v1/market/nepse/live/full"), api("/api/v1/market/free/movers?top=6")]);
    if (n.ok) setNepse(n.body);
    if (m.ok && m.body?.available) setMovers(m.body);
  }, []);
  useEffect(() => { load(); const id = setInterval(load, 60000); return () => clearInterval(id); }, [load]);

  const idx = numOr(nepse?.nepse_index), idxChg = numOr(nepse?.index_change), idxPct = numOr(nepse?.index_change_percent);
  const adv = numOr(nepse?.advancers), dec = numOr(nepse?.decliners), unch = numOr(nepse?.unchanged);
  const rows = useMemo(() => {
    let r = uni.rows;
    if (q.trim()) r = r.filter((s) => s.symbol.includes(q.trim().toUpperCase()));
    return [...r].sort((a, b) => (b.volume || 0) - (a.volume || 0));
  }, [uni.rows, q]);

  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 14 }}>
        <div>
          <Text tone="muted" size="xs" mono>NEPSE INDEX</Text>
          <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{idx != null ? idx.toLocaleString("en-IN") : "—"}</div>
          <span style={{ color: idxPct >= 0 ? "#2ee27a" : "#ff4d4d", fontSize: 13, fontWeight: 600 }}>
            {idxChg != null ? `${idxChg >= 0 ? "▲" : "▼"} ${Math.abs(idxChg).toFixed(2)}` : ""} {idxPct != null ? `${idxPct >= 0 ? "+" : ""}${idxPct}%` : ""}
          </span>
        </div>
        {(adv != null || dec != null) && (
          <div style={{ minWidth: 200 }}>
            <div style={{ display: "flex", height: 8, borderRadius: 100, overflow: "hidden", border: "1px solid rgba(255,64,64,.14)" }}>
              <div style={{ width: `${(adv / ((adv || 0) + (unch || 0) + (dec || 0) || 1)) * 100}%`, background: "#2ee27a" }} />
              <div style={{ width: `${(unch / ((adv || 0) + (unch || 0) + (dec || 0) || 1)) * 100}%`, background: "#8f8288" }} />
              <div style={{ width: `${(dec / ((adv || 0) + (unch || 0) + (dec || 0) || 1)) * 100}%`, background: "#ff4d4d" }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginTop: 4, color: "#8f8288" }}>
              <span style={{ color: "#2ee27a" }}>{adv ?? "—"} adv</span><span>{unch ?? "—"} unch</span><span style={{ color: "#ff4d4d" }}>{dec ?? "—"} dec</span>
            </div>
          </div>
        )}
        <div style={{ flexGrow: 1 }} />
        <Badge variant="soft" color={uni.live ? "#2ee27a" : "var(--status-neutral)"} label={uni.live ? `LIVE · ${uni.count}` : "loading"} />
      </div>

      {movers && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 14 }}>
          {[["TOP GAINERS", movers.gainers, "#2ee27a"], ["TOP LOSERS", movers.losers, "#ff4d4d"]].map(([title, list, col]) => (
            <div key={title} style={{ background: "#0b0709", border: "1px solid rgba(255,64,64,.12)", borderRadius: 8, padding: "10px 12px" }}>
              <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 6 }}>{title}</div>
              {(list || []).slice(0, 5).map((g, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "3px 0", fontVariantNumeric: "tabular-nums" }}>
                  <span>{g.symbol}</span><span style={{ color: col }}>{g.percent_change >= 0 ? "+" : ""}{g.percent_change}%</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      <input value={q} onChange={(e) => setQ(e.target.value.toUpperCase())} placeholder="Search symbol…"
        style={{ fontFamily: "inherit", fontSize: 12, padding: "6px 10px", borderRadius: 8, width: 180, marginBottom: 8, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.22)", outline: "none" }} />
      {uni.loading && <div style={{ display: "flex", justifyContent: "center", padding: 20 }}><Spinner size={16} /></div>}
      <div style={{ overflowX: "auto", maxHeight: 460, overflowY: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr>{["Symbol", "LTP", "%Chg", "High", "Low", "Volume"].map((h, i) => (
            <th key={h} style={{ position: "sticky", top: 0, background: "#0f0b10", textAlign: i === 0 ? "left" : "right", fontSize: 10, letterSpacing: ".05em", textTransform: "uppercase", color: "#8f8288", fontWeight: 600, padding: "8px 10px", borderBottom: "1px solid rgba(255,64,64,.14)" }}>{h}</th>
          ))}</tr></thead>
          <tbody>
            {rows.slice(0, 100).map((s) => (
              <tr key={s.symbol}>
                <td style={{ padding: "7px 10px", fontWeight: 600, borderBottom: "1px solid rgba(255,64,64,.06)" }}>{s.symbol}</td>
                <td style={{ padding: "7px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#dccfd3", borderBottom: "1px solid rgba(255,64,64,.06)" }}>{s.ltp ?? "—"}</td>
                <td style={{ padding: "7px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: (s.percentChange ?? 0) >= 0 ? "#2ee27a" : "#ff4d4d", borderBottom: "1px solid rgba(255,64,64,.06)" }}>{s.percentChange == null ? "—" : `${s.percentChange >= 0 ? "+" : ""}${s.percentChange}%`}</td>
                <td style={{ padding: "7px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#8f8288", borderBottom: "1px solid rgba(255,64,64,.06)" }}>{s.high ?? "—"}</td>
                <td style={{ padding: "7px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#8f8288", borderBottom: "1px solid rgba(255,64,64,.06)" }}>{s.low ?? "—"}</td>
                <td style={{ padding: "7px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#b7a8ad", borderBottom: "1px solid rgba(255,64,64,.06)" }}>{s.volume != null ? s.volume.toLocaleString("en-IN") : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>Index/breadth from the licensed snapshot; movers + full market from the free public source · observation-only.</Text>
    </div>
  );
}
