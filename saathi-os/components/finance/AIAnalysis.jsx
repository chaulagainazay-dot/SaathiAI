"use client";
/**
 * AI Analysis desk — technical analysis (agent) + ICT/SMC strategy (15m + IDM) for NEPSE and
 * crypto. Self-contained. Research/education only, never advice or execution.
 */
import { useCallback, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Button, Badge, Text, Spinner, EmptyState } from "@/components/ui";

function api(path, opts = {}) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store", headers: { "content-type": "application/json", ...(opts.headers || {}) }, ...opts })
    .then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, status: r.status, body: b }; });
}
const clean = (s) => String(s || "").replace(/^#+\s*/gm, "").replace(/\*\*/g, "");

export default function AIAnalysis() {
  const [market, setMarket] = useState("NEPSE");
  const [symbol, setSymbol] = useState("NABIL");
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(false);
  const [strat, setStrat] = useState(null);
  const [sLoading, setSLoading] = useState(false);

  const runTA = useCallback(async () => {
    if (!symbol.trim()) return;
    setLoading(true); setRes(null);
    const r = await api("/api/v1/market/analysis/technical", { method: "POST", body: JSON.stringify({ market, symbol: symbol.trim() }) });
    setRes(r.ok ? r.body : { available: false, error: r.body?.error || `HTTP ${r.status}` });
    setLoading(false);
  }, [market, symbol]);

  const runStrategy = useCallback(async () => {
    if (!symbol.trim()) return;
    setSLoading(true); setStrat(null);
    const r = await api("/api/v1/market/analysis/strategy", { method: "POST", body: JSON.stringify({ market, symbol: symbol.trim() }) });
    setStrat(r.ok ? r.body : { available: false, error: r.body?.error || `HTTP ${r.status}` });
    setSLoading(false);
  }, [market, symbol]);

  const e = res?.evidence;
  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ display: "flex", gap: 4 }}>
          {["NEPSE", "CRYPTO"].map((m) => (
            <button key={m} onClick={() => { setMarket(m); setSymbol(m === "NEPSE" ? "NABIL" : "BTC"); }}
              style={{ fontFamily: "inherit", fontSize: 12, padding: "6px 12px", borderRadius: 8, cursor: "pointer", border: "1px solid rgba(255,64,64,.25)", background: m === market ? "#ff2a2a" : "transparent", color: m === market ? "#08060a" : "#b7a8ad", fontWeight: m === market ? 700 : 400 }}>{m}</button>
          ))}
        </div>
        <input value={symbol} onChange={(e2) => setSymbol(e2.target.value.toUpperCase())} onKeyDown={(e2) => { if (e2.key === "Enter") runTA(); }}
          placeholder={market === "NEPSE" ? "NABIL, HDL…" : "BTC, ETH, SOL…"}
          style={{ fontFamily: "inherit", fontSize: 13, padding: "7px 10px", borderRadius: 8, width: 180, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" }} />
        <Button size="sm" onClick={runTA} disabled={loading}>{loading ? "Analyzing…" : "Run analysis"}</Button>
        <Button size="sm" variant="secondary" onClick={runStrategy} disabled={sLoading} title="ICT playbook: 15m structure + IDM (crypto)">{sLoading ? "Building…" : "Strategy (ICT + IDM)"}</Button>
      </div>

      {loading && <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 14 }}><Spinner size={16} /><Text tone="muted" size="sm">The desk is reading {symbol}…</Text></div>}
      {!loading && res && !res.available && <div style={{ marginTop: 12 }}><EmptyState title="Analysis unavailable" description={`${symbol}: ${res.error || "no data"}.`} /></div>}
      {!loading && res?.available && (
        <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "minmax(0,1fr) 260px", gap: 16, alignItems: "start" }}>
          <div style={{ background: "#0b0709", border: "1px solid rgba(255,64,64,.14)", borderRadius: 10, padding: "14px 16px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span style={{ fontWeight: 700, fontSize: 14 }}>{res.market} · {res.symbol}</span>
              <Badge variant="soft" color={e?.trend === "UPTREND" ? "#2ee27a" : e?.trend === "DOWNTREND" ? "#ff4d4d" : "var(--status-neutral)"} label={e?.trend} />
              <div style={{ flexGrow: 1 }} /><Text tone="disabled" size="xs" mono>agent: {res.provider}</Text>
            </div>
            <div style={{ whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.6, color: "#dccfd3" }}>{clean(res.analysis)}</div>
            <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 10 }}>{res.disclaimer}</Text>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288" }}>EVIDENCE</div>
            {[["Last", e?.last], ["Change %", e?.change_pct], ["RSI(14)", e?.rsi14], ["SMA20", e?.sma20], ["SMA50", e?.sma50], ["Support", e?.support], ["Resistance", e?.resistance]].map(([k, v]) => (
              <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "4px 0", borderBottom: "1px solid rgba(255,64,64,.07)", fontVariantNumeric: "tabular-nums" }}>
                <span style={{ color: "#8f8288" }}>{k}</span><span style={{ color: "#dccfd3" }}>{v ?? "—"}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {sLoading && <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 12 }}><Spinner size={16} /><Text tone="muted" size="sm">Building the ICT playbook…</Text></div>}
      {!sLoading && strat && (
        <div style={{ marginTop: 12, background: "#0b0709", border: "1px solid rgba(201,155,255,.3)", borderRadius: 10, padding: "12px 14px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
            <span style={{ color: "#c99bff", fontSize: 11, fontWeight: 700, letterSpacing: ".08em" }}>ICT STRATEGY PLAYBOOK</span>
            {strat.timeframe && <Badge variant="soft" label={strat.timeframe} />}
            {strat.smc?.inducement && <Badge variant="soft" color="#8fb3ff" label={`IDM ${strat.smc.inducement.side} ${strat.smc.inducement.price}`} />}
          </div>
          {strat.available === false ? <Text tone="muted" size="xs">Unavailable: {strat.error}</Text>
            : <div style={{ whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.6, color: "#dccfd3" }}>{clean(strat.strategy)}</div>}
          <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>Education/research only — not advice. Same engine as Ask Saathi chat.</Text>
        </div>
      )}
      {!res && !loading && !strat && !sLoading && <Text tone="muted" size="sm" style={{ display: "block", marginTop: 12 }}>Pick a market + symbol, then Run analysis or build a Strategy (ICT + IDM). Research only.</Text>}
    </div>
  );
}
