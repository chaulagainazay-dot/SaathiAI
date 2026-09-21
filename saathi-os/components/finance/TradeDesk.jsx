"use client";
/**
 * Trade Desk — Smart-Charts-style read for one symbol: trade setup (entry/SL/target/RR +
 * possible loss%/profit%), volume strength meter (buyer vs seller by period), and S/R zones.
 * Deterministic, observation-only — not advice, no orders.
 */
import { useCallback, useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Button, Badge, Text, Spinner, EmptyState } from "@/components/ui";
import StrategyPlaybook from "@/components/finance/StrategyPlaybook";

function api(path, opts = {}) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store", headers: { "content-type": "application/json", ...(opts.headers || {}) }, ...opts })
    .then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, status: r.status, body: b }; });
}

export default function TradeDesk({ market: marketProp, symbol: symbolProp }) {
  const [marketState, setMarket] = useState("NEPSE");
  const [symbolState, setSymbol] = useState("NABIL");
  const market = marketProp ?? marketState;
  const symbol = symbolProp ?? symbolState;
  const controlled = symbolProp != null;
  const [input, setInput] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (mk, sym) => {
    setLoading(true);
    const r = await api("/api/v1/market/analysis/desk", { method: "POST", body: JSON.stringify({ market: mk, symbol: sym }) });
    setData(r.ok ? r.body : { available: false, error: r.body?.error || `HTTP ${r.status}` });
    setLoading(false);
  }, []);
  useEffect(() => { load(market, symbol); }, [market, symbol, load]);

  const ts = data?.trade_setup;
  const vs = data?.volume_strength;
  const zones = data?.sr_zones || {};
  const zoneRows = ["R3", "R2", "R1", "S1", "S2", "S3"].filter((k) => zones[k]).map((k) => ({ k, ...zones[k] }));

  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        {!controlled && (
          <>
            <div style={{ display: "flex", gap: 4 }}>
              {["NEPSE", "CRYPTO"].map((m) => (
                <button key={m} onClick={() => { setMarket(m); setSymbol(m === "NEPSE" ? "NABIL" : "BTC"); }}
                  style={{ fontFamily: "inherit", fontSize: 12, padding: "6px 12px", borderRadius: 8, cursor: "pointer", border: "1px solid rgba(255,64,64,.25)", background: m === market ? "#ff2a2a" : "transparent", color: m === market ? "#08060a" : "#b7a8ad", fontWeight: m === market ? 700 : 400 }}>{m}</button>
              ))}
            </div>
            <input value={input} onChange={(e) => setInput(e.target.value.toUpperCase())}
              onKeyDown={(e) => { if (e.key === "Enter" && input.trim()) { setSymbol(input.trim()); setInput(""); } }}
              placeholder={market === "NEPSE" ? "NABIL, HDL…" : "BTC, ETH, SOL…"}
              style={{ fontFamily: "inherit", fontSize: 13, padding: "7px 10px", borderRadius: 8, width: 160, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" }} />
          </>
        )}
        <Button size="sm" variant="secondary" onClick={() => load(market, symbol)} disabled={loading}>{loading ? "…" : "Refresh"}</Button>
        <div style={{ flexGrow: 1 }} />
        {data?.available && <Badge variant="soft" color={data.trend === "UPTREND" ? "#2ee27a" : data.trend === "DOWNTREND" ? "#ff4d4d" : "var(--status-neutral)"} label={`${symbol} · ${data.trend}`} />}
      </div>

      {loading && <div style={{ display: "flex", justifyContent: "center", padding: 24 }}><Spinner size={16} /></div>}
      {!loading && data && !data.available && <EmptyState title="Desk unavailable" description={`${symbol}: ${data.error || "no data"}.`} />}

      {!loading && data?.available && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 12 }}>
          {/* Trade setup */}
          <div style={{ background: "#0b0709", border: "1px solid rgba(255,64,64,.14)", borderRadius: 10, padding: "12px 14px" }}>
            <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 8 }}>TRADE SETUP</div>
            {ts?.setup ? (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <Badge variant="soft" color={ts.side === "LONG" ? "#2ee27a" : "#ff4d4d"} label={ts.side} />
                  <span style={{ fontSize: 12, color: "#8f8288" }}>{ts.strategy}</span>
                </div>
                <Row k="Entry" v={ts.entry} />
                <Row k="Stop" v={ts.stop} c="#ff4d4d" />
                <Row k="Target" v={ts.target} c="#2ee27a" />
                <Row k="R : R" v={`1 : ${ts.rr}`} />
                <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                  <span style={{ flex: 1, textAlign: "center", background: "rgba(255,77,77,.12)", color: "#ff6a6a", borderRadius: 6, padding: "5px 0", fontSize: 12, fontWeight: 700 }}>−{ts.possible_loss_pct}%</span>
                  <span style={{ flex: 1, textAlign: "center", background: "rgba(46,226,122,.12)", color: "#2ee27a", borderRadius: 6, padding: "5px 0", fontSize: 12, fontWeight: 700 }}>+{ts.possible_profit_pct}%</span>
                </div>
                <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>Simulated setup · not advice.</Text>
              </>
            ) : <Text tone="muted" size="xs">No clean setup: {ts?.reason || "—"}</Text>}
          </div>

          {/* Volume strength meter */}
          <div style={{ background: "#0b0709", border: "1px solid rgba(255,64,64,.14)", borderRadius: 10, padding: "12px 14px" }}>
            <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 8 }}>VOLUME STRENGTH · buyer vs seller</div>
            {(vs?.periods || []).map((p) => (
              <div key={p.period} style={{ marginBottom: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 3 }}>
                  <span style={{ color: "#8f8288" }}>{p.period}</span>
                  <span><span style={{ color: "#2ee27a" }}>{p.buyer ?? "—"}%</span> <span style={{ color: "#8f8288" }}>/</span> <span style={{ color: "#ff4d4d" }}>{p.seller ?? "—"}%</span></span>
                </div>
                <div style={{ display: "flex", height: 6, borderRadius: 100, overflow: "hidden", background: "#140e15" }}>
                  <div style={{ width: `${p.buyer ?? 0}%`, background: "#2ee27a" }} />
                  <div style={{ width: `${p.seller ?? 0}%`, background: "#ff4d4d" }} />
                </div>
              </div>
            ))}
            <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 4 }}>{vs?.method}</Text>
          </div>

          {/* S/R zones */}
          <div style={{ background: "#0b0709", border: "1px solid rgba(255,64,64,.14)", borderRadius: 10, padding: "12px 14px" }}>
            <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 8 }}>SUPPORT / RESISTANCE ZONES</div>
            {zoneRows.length === 0 && <Text tone="muted" size="xs">No clear zones.</Text>}
            {zoneRows.map((z) => (
              <div key={z.k} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "5px 0", borderBottom: "1px solid rgba(255,64,64,.07)", fontVariantNumeric: "tabular-nums" }}>
                <span style={{ color: z.k[0] === "R" ? "#ff6a6a" : "#2ee27a", fontWeight: 700 }}>{z.k}</span>
                <span style={{ color: "#dccfd3" }}>{z.low === z.high ? z.low : `${z.low} – ${z.high}`}</span>
              </div>
            ))}
            <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 6 }}>Zones from swing extrema · price often reacts here.</Text>
          </div>
        </div>
      )}

      {/* Strategy playbook — live matches for this symbol */}
      {!loading && data?.available && (
        <div style={{ marginTop: 14, borderTop: "1px solid rgba(255,64,64,.12)", paddingTop: 6 }}>
          <StrategyPlaybook market={market} symbol={symbol} compact />
        </div>
      )}
    </div>
  );
}

function Row({ k, v, c }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, padding: "3px 0", fontVariantNumeric: "tabular-nums" }}>
      <span style={{ color: "#8f8288" }}>{k}</span>
      <span style={{ color: c || "#f2e8ea", fontWeight: 600 }}>{v}</span>
    </div>
  );
}
