"use client";
/**
 * Company fundamentals — reference fundamentals (STOCKS) enriched with the tracker's
 * fundamentals + dividends when reachable. Observation-only.
 */
import { useCallback, useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { getStock } from "@/lib/nepse/data";
import { Button, Badge, Text } from "@/components/ui";

function api(path) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store" })
    .then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, status: r.status, body: b }; });
}
const cr = (v) => (v == null ? "—" : (v / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 0 }) + " Cr");

export default function CompanyCard({ symbol: symbolProp }) {
  const [symbolState, setSymbol] = useState("NABIL");
  const symbol = symbolProp ?? symbolState;
  const controlled = symbolProp != null;
  const [input, setInput] = useState("");
  const [divs, setDivs] = useState(null);
  const [live, setLive] = useState(null);   // free quote
  const [co, setCo] = useState(null);       // free company page (52w, sector)

  const load = useCallback(async (sym) => {
    setDivs(null); setLive(null); setCo(null);
    const [d, q, c] = await Promise.all([
      api(`/api/v1/market/tracker/dividends?symbol=${encodeURIComponent(sym)}`),
      api(`/api/v1/market/free/quote?symbol=${encodeURIComponent(sym)}`),
      api(`/api/v1/market/free/company?symbol=${encodeURIComponent(sym)}`),
    ]);
    setDivs(d.ok ? d.body : null);
    setLive(q.ok && q.body?.available ? q.body.quote : null);
    setCo(c.ok && c.body?.available ? c.body : null);
  }, []);
  useEffect(() => { load(symbol); }, [symbol, load]);

  const s = getStock(symbol) || {};                       // reference fundamentals (where known)
  const known = getStock(symbol) != null || live != null || co != null;
  const ltp = live?.ltp ?? s.ltp ?? null;
  const w52h = co?.week52_high ?? s.high52 ?? null;
  const w52l = co?.week52_low ?? s.low52 ?? null;
  const rows = known ? [
    ["Sector", s.sector ?? co?.sector ?? "—"], ["LTP", ltp], ["Day %", live?.percent_change != null ? `${live.percent_change >= 0 ? "+" : ""}${live.percent_change}%` : "—"],
    ["EPS", s.eps ?? "—"], ["P/E", s.pe ?? "—"], ["P/B", s.pb ?? "—"],
    ["Book value", s.bookValue ?? "—"], ["Paid-up (Cr)", s.paidUp != null ? (s.paidUp / 100).toFixed(0) : "—"],
    ["Market cap", s.marketCap != null ? cr(s.marketCap) : "—"], ["52W high", w52h ?? "—"], ["52W low", w52l ?? "—"], ["RSI", s.rsi ?? "—"],
  ] : [];
  const latestDiv = (divs?.dividends || [])[0];

  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        {!controlled && (
          <>
            <input value={input} onChange={(e) => setInput(e.target.value.toUpperCase())}
              onKeyDown={(e) => { if (e.key === "Enter" && input.trim()) { setSymbol(input.trim()); setInput(""); } }}
              placeholder="Company symbol (NABIL, SCB…)"
              style={{ fontFamily: "inherit", fontSize: 12, padding: "7px 10px", borderRadius: 8, width: 200, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" }} />
            <Button size="sm" variant="secondary" onClick={() => { if (input.trim()) { setSymbol(input.trim()); setInput(""); } }}>Load</Button>
          </>
        )}
        <div style={{ flexGrow: 1 }} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>{symbol}</span>
        {s.name && <Badge variant="soft" label={s.name} />}
        {live && <Badge variant="soft" color="#2ee27a" label="LIVE" />}
      </div>
      {!known ? (
        <Text tone="muted" size="sm">No data for {symbol} — not listed or the free source is unreachable.</Text>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 8 }}>
          {rows.map(([k, v]) => (
            <div key={k} style={{ background: "#0b0709", border: "1px solid rgba(255,64,64,.1)", borderRadius: 8, padding: "8px 10px" }}>
              <div style={{ fontSize: 10, letterSpacing: ".08em", color: "#8f8288", textTransform: "uppercase" }}>{k}</div>
              <div style={{ fontSize: 14, fontWeight: 700, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>{v ?? "—"}</div>
            </div>
          ))}
        </div>
      )}
      {latestDiv && (
        <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 10 }}>
          Latest dividend {latestDiv.fiscal_year ? `(FY ${latestDiv.fiscal_year})` : ""}: cash {latestDiv.cash_dividend ?? "—"}, bonus {latestDiv.bonus_dividend ?? "—"}.
        </Text>
      )}
      <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 6 }}>
        Live LTP + 52-week from the free public source; P/E, P/B, EPS shown where known · research only, not advice.
      </Text>
    </div>
  );
}
