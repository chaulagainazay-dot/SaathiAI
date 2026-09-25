"use client";
/**
 * Swarm Prediction — a simulated investor crowd (persona archetypes) reads real evidence and
 * herds over rounds into an emergent direction. Deterministic port of the MiroFish idea; no
 * external services. Research/education only — a model crowd's opinion, not advice.
 */
import { useCallback, useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Button, Badge, Text, Spinner, EmptyState } from "@/components/ui";

function api(path, opts = {}) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store", headers: { "content-type": "application/json", ...(opts.headers || {}) }, ...opts })
    .then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, status: r.status, body: b }; });
}
const DIR = { UP: "#2ee27a", DOWN: "#ff4d4d", SIDEWAYS: "#ffab3d" };
const LEAN = { BUY: "#2ee27a", SELL: "#ff4d4d", HOLD: "#8f8288" };

function Spark({ traj }) {
  if (!traj || traj.length < 2) return null;
  const w = 180, h = 40, pad = 4;
  const xs = traj.map((_, i) => pad + (i * (w - 2 * pad)) / (traj.length - 1));
  const ys = traj.map((v) => h / 2 - (v * (h / 2 - pad))); // v in [-1,1] → y
  const d = xs.map((x, i) => `${i ? "L" : "M"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
  const last = traj[traj.length - 1];
  const col = last > 0.15 ? DIR.UP : last < -0.15 ? DIR.DOWN : DIR.SIDEWAYS;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} style={{ display: "block" }}>
      <line x1={pad} y1={h / 2} x2={w - pad} y2={h / 2} stroke="rgba(255,255,255,.12)" strokeWidth="1" />
      <path d={d} fill="none" stroke={col} strokeWidth="2" />
      <circle cx={xs[xs.length - 1]} cy={ys[ys.length - 1]} r="3" fill={col} />
    </svg>
  );
}

export default function SwarmPrediction({ market: marketProp, symbol: symbolProp, auto = false }) {
  const controlled = symbolProp != null;
  const [market, setMarket] = useState(marketProp || "NEPSE");
  const [symbol, setSymbol] = useState(symbolProp || "NABIL");
  const [input, setInput] = useState(symbolProp || "NABIL");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { if (marketProp) setMarket(marketProp); }, [marketProp]);
  useEffect(() => { if (symbolProp != null) { setSymbol(symbolProp); setInput(symbolProp); } }, [symbolProp]);

  const run = useCallback(async (mkt, sym) => {
    if (!sym) return;
    setLoading(true); setData(null);
    const r = await api("/api/v1/market/predict/swarm", { method: "POST", body: JSON.stringify({ market: mkt, symbol: sym }) });
    setData(r.ok ? r.body : { available: false, error: r.body?.error || `HTTP ${r.status}` });
    setLoading(false);
  }, []);

  useEffect(() => { if (auto && symbol) run(market, symbol); }, [auto, market, symbol, run]);

  const d = data;
  return (
    <div style={{ padding: 14 }}>
      {!controlled && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
          <div style={{ display: "flex", gap: 4 }}>
            {["NEPSE", "CRYPTO"].map((m) => (
              <button key={m} onClick={() => { setMarket(m); const v = m === "NEPSE" ? "NABIL" : "BTC"; setSymbol(v); setInput(v); }}
                style={{ fontFamily: "inherit", fontSize: 12, padding: "6px 12px", borderRadius: 8, cursor: "pointer", border: "1px solid rgba(255,64,64,.25)", background: m === market ? "#ff2a2a" : "transparent", color: m === market ? "#08060a" : "#b7a8ad", fontWeight: m === market ? 700 : 400 }}>{m}</button>
            ))}
          </div>
          <input value={input} onChange={(e) => setInput(e.target.value.toUpperCase())} onKeyDown={(e) => { if (e.key === "Enter") setSymbol(input.trim()); }}
            placeholder={market === "NEPSE" ? "NABIL, HDL…" : "BTC, ETH…"}
            style={{ fontFamily: "inherit", fontSize: 13, padding: "7px 10px", borderRadius: 8, width: 150, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" }} />
          <Button size="sm" onClick={() => setSymbol(input.trim())} disabled={loading}>{loading ? "Simulating…" : "Simulate crowd"}</Button>
        </div>
      )}
      {controlled && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <span style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288" }}>SWARM PREDICTION · {market} {symbol}</span>
          <div style={{ flexGrow: 1 }} />
          <Button size="sm" variant="secondary" onClick={() => run(market, symbol)} disabled={loading}>{loading ? "…" : "Re-run"}</Button>
        </div>
      )}

      {loading && <div style={{ display: "flex", gap: 8, alignItems: "center" }}><Spinner size={14} /><Text tone="muted" size="sm">A model crowd is reading {symbol}…</Text></div>}
      {!loading && d && !d.available && <EmptyState title="Simulation unavailable" description={`${symbol}: ${d.error || "no data"}.`} />}

      {!loading && d?.available && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", background: "#0b0709", border: `1px solid ${DIR[d.direction] || "#8f8288"}55`, borderRadius: 10, padding: "12px 14px" }}>
            <div>
              <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288" }}>EMERGENT DIRECTION</div>
              <div style={{ fontSize: 22, fontWeight: 800, color: DIR[d.direction] || "#f2e8ea" }}>{d.direction}</div>
            </div>
            <div style={{ display: "flex", gap: 16, fontVariantNumeric: "tabular-nums" }}>
              <Stat k="Sentiment" v={d.sentiment > 0 ? `+${d.sentiment}` : d.sentiment} c={DIR[d.direction]} />
              <Stat k="Confidence" v={`${Math.round(d.confidence * 100)}%`} />
              <Stat k="Agreement" v={`${Math.round(d.agreement * 100)}%`} />
              <Stat k="Rounds" v={d.rounds} />
            </div>
            <div style={{ flexGrow: 1 }} />
            <div>
              <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 2 }}>SENTIMENT PATH</div>
              <Spark traj={d.trajectory} />
            </div>
          </div>

          {d.catalyst?.label && (
            <div style={{ marginTop: 10 }}>
              <Badge variant="soft" color={d.catalyst.sign < 0 ? "#ff4d4d" : d.catalyst.sign > 0 ? "#2ee27a" : "#8f8288"}
                label={`${d.catalyst.sign < 0 ? "⚠ supply/bear" : d.catalyst.sign > 0 ? "bull" : "neutral"} catalyst`} />
              <Text tone="muted" size="xs" style={{ display: "inline", marginLeft: 8 }}>{d.catalyst.label}</Text>
            </div>
          )}

          {d.drivers?.length > 0 && (
            <ul style={{ margin: "10px 0 0", paddingLeft: 16 }}>
              {d.drivers.map((x, i) => <li key={i} style={{ fontSize: 12, color: "#dccfd3", lineHeight: 1.6 }}>{x}</li>)}
            </ul>
          )}

          <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", margin: "14px 0 6px" }}>THE CROWD · {d.agents.length} archetypes</div>
          {d.agents.map((a) => (
            <div key={a.persona} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0", borderBottom: "1px solid rgba(255,64,64,.07)" }}>
              <span style={{ minWidth: 150, fontSize: 12, color: "#f2e8ea" }}>{a.persona}</span>
              <Badge variant="soft" color={LEAN[a.lean]} label={a.lean} />
              <div style={{ flex: 1, height: 6, background: "#140e15", borderRadius: 100, position: "relative", overflow: "hidden" }}>
                <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "rgba(255,255,255,.15)" }} />
                <div style={{ position: "absolute", top: 0, bottom: 0,
                  left: a.stance >= 0 ? "50%" : `${50 + a.stance * 50}%`,
                  width: `${Math.abs(a.stance) * 50}%`, background: a.stance >= 0 ? LEAN.BUY : LEAN.SELL }} />
              </div>
              <span style={{ fontSize: 11, color: "#8f8288", minWidth: 44, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{a.stance}</span>
            </div>
          ))}

          <Text tone="muted" size="xs" style={{ display: "block", marginTop: 12, lineHeight: 1.6 }}>{d.narrative}</Text>
          <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 6 }}>{d.disclaimer}</Text>
        </>
      )}
    </div>
  );
}

function Stat({ k, v, c }) {
  return (
    <div>
      <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288" }}>{k}</div>
      <div style={{ fontSize: 15, fontWeight: 700, color: c || "#f2e8ea" }}>{v}</div>
    </div>
  );
}
