"use client";
/**
 * S-R Screener — stocks nearest support / resistance across the NEPSE reference universe.
 * Support/resistance referenced from the 52-week range (labelled as such). Observation-only.
 */
import { useMemo, useState } from "react";
import { STOCKS } from "@/lib/nepse/data";
import { Text, Badge } from "@/components/ui";

const SECTORS = ["All sectors", ...Array.from(new Set(STOCKS.map((s) => s.sector))).sort()];
const band = (v) => (v == null ? "—" : `${Math.round(v * 0.98)} – ${Math.round(v)}`);

export default function SRScreener() {
  const [mode, setMode] = useState("support");   // support | resistance
  const [sector, setSector] = useState("All sectors");
  const [q, setQ] = useState("");

  const rows = useMemo(() => {
    let out = STOCKS.map((s) => ({
      ...s,
      nearSupport: s.low52 ? ((s.ltp - s.low52) / s.low52) * 100 : null,
      nearResistance: s.high52 ? ((s.high52 - s.ltp) / s.high52) * 100 : null,
    }));
    if (sector !== "All sectors") out = out.filter((s) => s.sector === sector);
    if (q.trim()) out = out.filter((s) => s.symbol.includes(q.trim().toUpperCase()) || (s.name || "").toUpperCase().includes(q.trim().toUpperCase()));
    const key = mode === "support" ? "nearSupport" : "nearResistance";
    out.sort((a, b) => { const x = a[key], y = b[key]; if (x == null) return 1; if (y == null) return -1; return x - y; });
    return out;
  }, [mode, sector, q]);

  const inp = { fontFamily: "inherit", fontSize: 12, padding: "6px 10px", borderRadius: 8, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.22)", outline: "none" };

  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
        {[["support", "Near Support"], ["resistance", "Near Resistance"]].map(([k, label]) => (
          <button key={k} onClick={() => setMode(k)}
            style={{ flex: 1, fontFamily: "inherit", fontSize: 12, padding: "8px 0", borderRadius: 8, cursor: "pointer", border: "1px solid rgba(255,64,64,.25)", background: mode === k ? (k === "support" ? "#2ee27a" : "#ff2a2a") : "transparent", color: mode === k ? "#08060a" : "#b7a8ad", fontWeight: mode === k ? 700 : 400 }}>{label}</button>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
        <select style={{ ...inp, width: "auto" }} value={sector} onChange={(e) => setSector(e.target.value)}>{SECTORS.map((s) => <option key={s}>{s}</option>)}</select>
        <input style={{ ...inp, flexGrow: 1, minWidth: 120 }} placeholder="Search company…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr>{["Company", "Close", mode === "support" ? "% Near Support" : "% Near Resistance", "Support (52W)", "Resistance (52W)"].map((h, i) => (
            <th key={h} style={{ textAlign: i === 0 ? "left" : "right", fontSize: 10, letterSpacing: ".05em", textTransform: "uppercase", color: "#8f8288", fontWeight: 600, padding: "8px 10px", borderBottom: "1px solid rgba(255,64,64,.14)", whiteSpace: "nowrap" }}>{h}</th>
          ))}</tr></thead>
          <tbody>
            {rows.slice(0, 40).map((s) => {
              const nearPct = mode === "support" ? s.nearSupport : s.nearResistance;
              const hot = nearPct != null && nearPct <= 3;
              return (
                <tr key={s.symbol}>
                  <td style={{ padding: "8px 10px", fontWeight: 600, borderBottom: "1px solid rgba(255,64,64,.07)" }}>{s.symbol}</td>
                  <td style={{ padding: "8px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#dccfd3", borderBottom: "1px solid rgba(255,64,64,.07)" }}>{s.ltp}</td>
                  <td style={{ padding: "8px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: hot ? 700 : 400, color: hot ? (mode === "support" ? "#2ee27a" : "#ff4d4d") : "#b7a8ad", borderBottom: "1px solid rgba(255,64,64,.07)" }}>{nearPct == null ? "—" : `${nearPct.toFixed(1)}%`}</td>
                  <td style={{ padding: "8px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#2ee27a", background: mode === "support" ? "rgba(46,226,122,.06)" : "transparent", borderBottom: "1px solid rgba(255,64,64,.07)" }}>{band(s.low52)}</td>
                  <td style={{ padding: "8px 10px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#ff6a6a", background: mode === "resistance" ? "rgba(255,106,106,.06)" : "transparent", borderBottom: "1px solid rgba(255,64,64,.07)" }}>{band(s.high52)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>
        Support/resistance referenced from the 52-week range · nearest first · research only, not advice.
      </Text>
    </div>
  );
}
