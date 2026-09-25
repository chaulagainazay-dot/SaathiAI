"use client";
/**
 * Stock Screener — fundamental + technical filters over the NEPSE reference universe (STOCKS).
 * Client-side, instant, observation-only. Not advice.
 */
import { useMemo, useState } from "react";
import { useNepseUniverse } from "@/lib/useNepseUniverse";
import { Button, Badge, Text } from "@/components/ui";

const COLS = [
  ["symbol", "Symbol"], ["ltp", "LTP"], ["chg", "%Chg"], ["pe", "P/E"], ["pb", "P/B"],
  ["eps", "EPS"], ["rsi", "RSI"], ["marketCap", "Mkt Cap (Cr)"], ["sector", "Sector"],
];

const num = (v) => (Number.isFinite(v) ? v : null);
const cr = (v) => (v == null ? "—" : (v / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 0 }));

export default function StockScreener() {
  const uni = useNepseUniverse();
  const universe = uni.rows;
  const SECTORS = useMemo(() => ["All", ...Array.from(new Set(universe.map((s) => s.sector).filter((x) => x && x !== "—"))).sort()], [universe]);
  const [sector, setSector] = useState("All");
  const [f, setF] = useState({ priceMin: "", priceMax: "", peMax: "", pbMax: "", epsMin: "", rsiMin: "", rsiMax: "", mcapMin: "" });
  const [sortKey, setSortKey] = useState("marketCap");
  const [sortDir, setSortDir] = useState(-1);

  const set = (k, v) => setF((o) => ({ ...o, [k]: v }));
  const clear = () => { setF({ priceMin: "", priceMax: "", peMax: "", pbMax: "", epsMin: "", rsiMin: "", rsiMax: "", mcapMin: "" }); setSector("All"); };

  const rows = useMemo(() => {
    const g = (v) => (v === "" ? null : parseFloat(v));
    const pMin = g(f.priceMin), pMax = g(f.priceMax), peMax = g(f.peMax), pbMax = g(f.pbMax);
    const epsMin = g(f.epsMin), rMin = g(f.rsiMin), rMax = g(f.rsiMax), mMin = g(f.mcapMin);
    let out = universe.map((s) => ({ ...s, chg: s.percentChange ?? (s.prevClose ? ((s.ltp - s.prevClose) / s.prevClose) * 100 : null) }));
    out = out.filter((s) => {
      if (sector !== "All" && s.sector !== sector) return false;
      if (pMin != null && !(s.ltp >= pMin)) return false;
      if (pMax != null && !(s.ltp <= pMax)) return false;
      if (peMax != null && !(num(s.pe) != null && s.pe <= peMax)) return false;
      if (pbMax != null && !(num(s.pb) != null && s.pb <= pbMax)) return false;
      if (epsMin != null && !(num(s.eps) != null && s.eps >= epsMin)) return false;
      if (rMin != null && !(num(s.rsi) != null && s.rsi >= rMin)) return false;
      if (rMax != null && !(num(s.rsi) != null && s.rsi <= rMax)) return false;
      if (mMin != null && !(num(s.marketCap) != null && s.marketCap / 1e7 >= mMin)) return false;
      return true;
    });
    out.sort((a, b) => { const x = a[sortKey], y = b[sortKey]; if (x == null) return 1; if (y == null) return -1; return (x < y ? -1 : x > y ? 1 : 0) * sortDir; });
    return out;
  }, [f, sector, sortKey, sortDir, universe]);

  const inp = { fontFamily: "inherit", fontSize: 12, padding: "6px 8px", borderRadius: 6, width: 74, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.22)", outline: "none" };

  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        <select value={sector} onChange={(e) => setSector(e.target.value)} style={{ ...inp, width: "auto" }}>
          {SECTORS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <input style={inp} placeholder="Price ≥" value={f.priceMin} onChange={(e) => set("priceMin", e.target.value)} />
        <input style={inp} placeholder="Price ≤" value={f.priceMax} onChange={(e) => set("priceMax", e.target.value)} />
        <input style={inp} placeholder="P/E ≤" value={f.peMax} onChange={(e) => set("peMax", e.target.value)} />
        <input style={inp} placeholder="P/B ≤" value={f.pbMax} onChange={(e) => set("pbMax", e.target.value)} />
        <input style={inp} placeholder="EPS ≥" value={f.epsMin} onChange={(e) => set("epsMin", e.target.value)} />
        <input style={inp} placeholder="RSI ≥" value={f.rsiMin} onChange={(e) => set("rsiMin", e.target.value)} />
        <input style={inp} placeholder="RSI ≤" value={f.rsiMax} onChange={(e) => set("rsiMax", e.target.value)} />
        <input style={inp} placeholder="MCap≥Cr" value={f.mcapMin} onChange={(e) => set("mcapMin", e.target.value)} />
        <Button size="sm" variant="ghost" onClick={clear}>Clear</Button>
        <div style={{ flexGrow: 1 }} />
        <Badge variant="soft" color={uni.live ? "#2ee27a" : "var(--status-neutral)"} label={uni.live ? `LIVE · ${uni.count}` : uni.loading ? "loading…" : "reference"} />
        <Badge variant="soft" label={`${rows.length} / ${universe.length} match`} />
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr>{COLS.map(([k, label], i) => (
            <th key={k} onClick={() => { if (sortKey === k) setSortDir((d) => -d); else { setSortKey(k); setSortDir(-1); } }}
              style={{ textAlign: i === 0 || k === "sector" ? "left" : "right", fontSize: 10, letterSpacing: ".06em", textTransform: "uppercase", color: sortKey === k ? "#ff5757" : "#8f8288", fontWeight: 600, padding: "8px 10px", borderBottom: "1px solid rgba(255,64,64,.14)", cursor: "pointer", whiteSpace: "nowrap" }}>
              {label}{sortKey === k ? (sortDir < 0 ? " ↓" : " ↑") : ""}
            </th>
          ))}</tr></thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.symbol}>
                <td style={{ padding: "8px 10px", fontWeight: 600, borderBottom: "1px solid rgba(255,64,64,.07)" }}>{s.symbol}</td>
                <Cell>{s.ltp}</Cell>
                <td style={{ padding: "8px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: (s.chg ?? 0) >= 0 ? "#2ee27a" : "#ff4d4d", borderBottom: "1px solid rgba(255,64,64,.07)" }}>{s.chg == null ? "—" : `${s.chg >= 0 ? "+" : ""}${s.chg.toFixed(2)}%`}</td>
                <Cell>{s.pe ?? "—"}</Cell><Cell>{s.pb ?? "—"}</Cell><Cell>{s.eps ?? "—"}</Cell>
                <td style={{ padding: "8px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: s.rsi > 70 ? "#ff4d4d" : s.rsi < 30 ? "#2ee27a" : "#dccfd3", borderBottom: "1px solid rgba(255,64,64,.07)" }}>{s.rsi ?? "—"}</td>
                <Cell>{cr(s.marketCap)}</Cell>
                <td style={{ padding: "8px 10px", fontSize: 11, color: "#8f8288", borderBottom: "1px solid rgba(255,64,64,.07)", whiteSpace: "nowrap" }}>{s.sector}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>
        {uni.live ? `Live full market · ${uni.source}` : "Reference universe"} · fundamentals (P/E, P/B, EPS, sector) shown where known · research only, not advice.
      </Text>
    </div>
  );
}

function Cell({ children }) {
  return <td style={{ padding: "8px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#dccfd3", borderBottom: "1px solid rgba(255,64,64,.07)" }}>{children}</td>;
}
