"use client";
/**
 * Pro Trading Strategy Playbook — the owner's crypto-signal-bot strategies (van de Poppe,
 * Pentoshi, Plan B, …) now running live against SaathiOS evidence for NEPSE + crypto.
 * Live scan of a symbol against every rule set + the full reference catalog.
 * Research/education only — never advice or an order.
 */
import { useCallback, useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Button, Badge, Text, Spinner, EmptyState } from "@/components/ui";

function api(path, opts = {}) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store", headers: { "content-type": "application/json", ...(opts.headers || {}) }, ...opts })
    .then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, status: r.status, body: b }; });
}
const GRADE = { A: "#2ee27a", B: "#ffab3d", C: "#ff8a3d" };

export default function StrategyPlaybook({ market: marketProp, symbol: symbolProp, compact = false }) {
  const controlled = symbolProp != null;
  const [market, setMarket] = useState(marketProp || "NEPSE");
  const [symbol, setSymbol] = useState(symbolProp || "NABIL");
  const [input, setInput] = useState(symbolProp || "NABIL");
  const [scan, setScan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [catalog, setCatalog] = useState([]);

  useEffect(() => { if (marketProp) setMarket(marketProp); }, [marketProp]);
  useEffect(() => { if (symbolProp != null) { setSymbol(symbolProp); setInput(symbolProp); } }, [symbolProp]);

  useEffect(() => { (async () => { const r = await api("/api/v1/market/strategies"); if (r.ok) setCatalog(r.body.strategies || []); })(); }, []);

  const runScan = useCallback(async (mkt, sym) => {
    if (!sym) return;
    setLoading(true); setScan(null);
    const r = await api("/api/v1/market/strategies/scan", { method: "POST", body: JSON.stringify({ market: mkt, symbol: sym }) });
    setScan(r.ok ? r.body : { available: false, error: r.body?.error || `HTTP ${r.status}` });
    setLoading(false);
  }, []);

  useEffect(() => { runScan(market, symbol); }, [market, symbol, runScan]);

  const matches = scan?.matches || [];

  return (
    <div style={{ padding: 14 }}>
      {!controlled && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
          <div style={{ display: "flex", gap: 4 }}>
            {["NEPSE", "CRYPTO"].map((m) => (
              <button key={m} onClick={() => { setMarket(m); const d = m === "NEPSE" ? "NABIL" : "BTC"; setSymbol(d); setInput(d); }}
                style={{ fontFamily: "inherit", fontSize: 12, padding: "6px 12px", borderRadius: 8, cursor: "pointer", border: "1px solid rgba(255,64,64,.25)", background: m === market ? "#ff2a2a" : "transparent", color: m === market ? "#08060a" : "#b7a8ad", fontWeight: m === market ? 700 : 400 }}>{m}</button>
            ))}
          </div>
          <input value={input} onChange={(e) => setInput(e.target.value.toUpperCase())} onKeyDown={(e) => { if (e.key === "Enter") setSymbol(input.trim()); }}
            placeholder={market === "NEPSE" ? "NABIL, HDL…" : "BTC, ETH…"}
            style={{ fontFamily: "inherit", fontSize: 13, padding: "7px 10px", borderRadius: 8, width: 150, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" }} />
          <Button size="sm" onClick={() => setSymbol(input.trim())} disabled={loading}>{loading ? "Scanning…" : "Scan"}</Button>
        </div>
      )}

      {/* Live matches */}
      <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 8 }}>
        LIVE SETUPS · {market} {symbol}{scan?.match_count != null ? ` · ${scan.match_count} active` : ""}
      </div>
      {loading && <div style={{ display: "flex", gap: 8, alignItems: "center" }}><Spinner size={14} /><Text tone="muted" size="sm">Scanning {symbol} against the playbook…</Text></div>}
      {!loading && scan && !scan.available && <EmptyState title="Scan unavailable" description={`${symbol}: ${scan.error || "no data"}.`} />}
      {!loading && scan?.available && matches.length === 0 && (
        <EmptyState title="No active setups" description="No strategy's confluences are met right now — markets may be ranging. Wait for a cleaner setup." />
      )}
      {!loading && matches.map((m) => (
        <div key={m.id} style={{ background: "#0b0709", border: `1px solid ${GRADE[m.grade] || "#8f8288"}44`, borderRadius: 10, padding: "10px 12px", marginBottom: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13, fontWeight: 800, color: GRADE[m.grade] || "#f2e8ea" }}>{m.grade}</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: "#f2e8ea" }}>{m.name}</span>
            <Badge variant="soft" color={m.side === "LONG" ? "#2ee27a" : "#ff4d4d"} label={m.side} />
            <Badge variant="soft" label={m.style} />
            <div style={{ flexGrow: 1 }} />
            <Text tone="disabled" size="xs" mono>score {Math.round(m.score * 100)}%</Text>
          </div>
          <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 2 }}>👤 {m.trader}</Text>
          <ul style={{ margin: "6px 0 0", paddingLeft: 16 }}>
            {(m.reasons || []).slice(0, 4).map((r, i) => <li key={i} style={{ fontSize: 12, color: "#dccfd3", lineHeight: 1.5 }}>{r}</li>)}
          </ul>
          <div style={{ display: "flex", gap: 12, marginTop: 8, fontVariantNumeric: "tabular-nums", fontSize: 12 }}>
            <span style={{ color: "#8f8288" }}>Entry <b style={{ color: "#dccfd3" }}>{m.entry}</b></span>
            <span style={{ color: "#8f8288" }}>Stop <b style={{ color: "#ff8a8a" }}>{m.stop}</b></span>
            <span style={{ color: "#8f8288" }}>Target <b style={{ color: "#8fe6a8" }}>{m.target}</b></span>
          </div>
        </div>
      ))}
      {!loading && matches.length > 0 && <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 4 }}>{scan?.disclaimer}</Text>}

      {/* Reference catalog */}
      {!compact && catalog.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 8 }}>PLAYBOOK · {catalog.length} STRATEGIES</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 10 }}>
            {catalog.map((s) => {
              const active = matches.some((m) => m.id === s.id);
              return (
                <div key={s.id} style={{ background: "#0b0709", border: `1px solid ${active ? "rgba(46,226,122,.4)" : "rgba(255,64,64,.12)"}`, borderRadius: 10, padding: "10px 12px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 12.5, fontWeight: 700, color: "#f2e8ea" }}>{s.name}</span>
                    {active && <Badge variant="soft" color="#2ee27a" label="ACTIVE" />}
                    {s.manual && <Badge variant="soft" color="#8f8288" label="manual" />}
                  </div>
                  <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 2 }}>👤 {s.trader} · {s.style} · {s.tf}</Text>
                  <Text tone="muted" size="xs" style={{ display: "block", marginTop: 5, lineHeight: 1.5 }}>{s.desc}</Text>
                  {s.rules && (
                    <div style={{ marginTop: 6, fontSize: 11, color: "#b7a8ad", lineHeight: 1.6 }}>
                      <div><span style={{ color: "#8f8288" }}>Entry:</span> {s.rules.entry}</div>
                      <div><span style={{ color: "#8f8288" }}>SL:</span> {s.rules.sl} · <span style={{ color: "#8f8288" }}>TP:</span> {s.rules.tp}</div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>Ported from your signal-bot playbook · deterministic scan over real OHLC · research only, not advice.</Text>
        </div>
      )}
    </div>
  );
}
