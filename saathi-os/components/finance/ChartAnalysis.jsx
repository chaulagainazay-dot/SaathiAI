"use client";
/**
 * Chart Analysis — self-contained NEPSE chart: stock search, timeframe, auto ICT/SMC with
 * numbers, volume desk with buy/sell signals, and a full-screen view. Reused by the Command
 * Deck (compact) and the dedicated /command-deck/chart page (expanded). Research only.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Badge, Text, Spinner, EmptyState } from "@/components/ui";

const CHART_SYMBOLS = ["NABIL", "HDL", "UPPER", "GBIME", "NRIC"];

function api(path, opts = {}) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store", headers: { "content-type": "application/json", ...(opts.headers || {}) }, ...opts })
    .then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, status: r.status, body: b }; });
}
const numOr = (v, d = null) => { const n = typeof v === "number" ? v : parseFloat(String(v ?? "").replace(/,/g, "")); return Number.isFinite(n) ? n : d; };
const pct = (n, dp = 2) => (n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(dp)}%`);
function sma(c, p) { const o = []; let s = 0; for (let i = 0; i < c.length; i++) { s += c[i]; if (i >= p) s -= c[i - p]; o.push(i >= p - 1 ? s / p : null); } return o; }
function rsi14(c) { if (c.length < 15) return null; let g = 0, l = 0; for (let i = 1; i <= 14; i++) { const d = c[i] - c[i - 1]; if (d >= 0) g += d; else l -= d; } g /= 14; l /= 14; for (let i = 15; i < c.length; i++) { const d = c[i] - c[i - 1]; g = (g * 13 + (d > 0 ? d : 0)) / 14; l = (l * 13 + (d < 0 ? -d : 0)) / 14; } if (l === 0) return 100; return 100 - 100 / (1 + g / l); }

export default function ChartAnalysis({ expanded = false, onTech }) {
  const [symbol, setSymbol] = useState("NABIL");
  const [symInput, setSymInput] = useState("");
  const [tfRange, setTfRange] = useState("3M");
  const [chart, setChart] = useState(null);
  const [loading, setLoading] = useState(true);
  const [smcOn, setSmcOn] = useState(true);
  const [smcData, setSmcData] = useState(null);
  const [deskData, setDeskData] = useState(null);
  const [full, setFull] = useState(false);

  const loadChart = useCallback(async (sym, range) => {
    setLoading(true);
    const r = await api(`/api/v1/market/tracker/chart?symbol=${encodeURIComponent(sym)}&range=${encodeURIComponent(range)}`);
    setChart(r.ok ? r.body : { available: false, error: r.body?.error || `HTTP ${r.status}` });
    setLoading(false);
  }, []);
  const loadSMC = useCallback(async (sym) => {
    const r = await api("/api/v1/market/analysis/smc", { method: "POST", body: JSON.stringify({ market: "NEPSE", symbol: sym }) });
    setSmcData(r.ok ? r.body : null);
  }, []);
  const loadDesk = useCallback(async (sym) => {
    const r = await api("/api/v1/market/analysis/desk", { method: "POST", body: JSON.stringify({ market: "NEPSE", symbol: sym }) });
    setDeskData(r.ok ? r.body : null);
  }, []);
  useEffect(() => { loadChart(symbol, tfRange); }, [symbol, tfRange, loadChart]);
  useEffect(() => { if (smcOn) loadSMC(symbol); }, [smcOn, symbol, loadSMC]);
  useEffect(() => { loadDesk(symbol); }, [symbol, loadDesk]);

  const deskTrade = deskData?.trade_setup?.setup ? { entry: deskData.trade_setup.entry, stop: deskData.trade_setup.stop, target: deskData.trade_setup.target } : null;
  const deskZones = deskData?.sr_zones || null;

  const tech = useMemo(() => {
    const pts = (chart?.ohlc || []).map((p) => ({ d: p.business_date, o: numOr(p.open), h: numOr(p.high), l: numOr(p.low), c: numOr(p.close) })).filter((p) => p.c != null);
    if (pts.length < 5) return { available: false };
    const closes = pts.map((p) => p.c);
    const s20 = sma(closes, 20), s50 = sma(closes, 50);
    const last = closes[closes.length - 1], prev = closes[closes.length - 2];
    const day = prev ? ((last - prev) / prev) * 100 : null;
    const l20 = s20[s20.length - 1], l50 = s50[s50.length - 1];
    const rsi = rsi14(closes);
    const trend = l20 != null && l50 != null ? (last > l20 && l20 >= l50 ? "UPTREND" : last < l20 && l20 <= l50 ? "DOWNTREND" : "SIDEWAYS") : "INSUFFICIENT";
    const win = pts.slice(-48);
    const support = Math.min(...win.map((p) => p.l ?? p.c));
    const resistance = Math.max(...win.map((p) => p.h ?? p.c));
    const volAll = (chart?.volume || []).map((v) => numOr(v.volume) || 0);
    const vols = volAll.slice(-48);
    const avgVol = vols.length ? vols.reduce((a, b) => a + b, 0) / vols.length : 0;
    const volSignals = win.map((p, i) => { const v = vols[i] ?? 0; if (avgVol > 0 && v >= 1.5 * avgVol && p.o != null) return p.c >= p.o ? "BUY" : "SELL"; return null; });
    const lastSig = [...volSignals].reverse().find((s) => s) || null;
    return { pts: win, s20: s20.slice(-48), s50: s50.slice(-48), last, day, rsi, trend, l20, l50, support, resistance, vols, avgVol, volSignals, lastSig, available: true };
  }, [chart]);

  useEffect(() => { if (tech.available && onTech) onTech({ symbol, last: tech.last, day: tech.day, rsi: tech.rsi, trend: tech.trend, support: tech.support, resistance: tech.resistance }); }, [tech, symbol, onTech]);

  const controls = (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
      <input value={symInput} onChange={(e) => setSymInput(e.target.value.toUpperCase())}
        onKeyDown={(e) => { if (e.key === "Enter" && symInput.trim()) { setSymbol(symInput.trim()); setSymInput(""); } }}
        placeholder="Search stock (NABIL, NTC, SCB)…"
        style={{ fontFamily: "inherit", fontSize: 12, padding: "6px 10px", borderRadius: 8, width: 210, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" }} />
      <div style={{ display: "flex", gap: 4 }}>
        {CHART_SYMBOLS.map((s) => (
          <button key={s} onClick={() => setSymbol(s)} style={{ fontFamily: "inherit", fontSize: 11, padding: "4px 8px", borderRadius: 100, cursor: "pointer", border: "1px solid rgba(255,64,64,.2)", background: s === symbol ? "#ff2a2a" : "transparent", color: s === symbol ? "#08060a" : "#8f8288", fontWeight: s === symbol ? 700 : 400 }}>{s}</button>
        ))}
      </div>
      <div style={{ flexGrow: 1 }} />
      <button onClick={() => setSmcOn((v) => !v)} style={{ fontFamily: "inherit", fontSize: 11, padding: "4px 9px", borderRadius: 100, cursor: "pointer", border: "1px solid rgba(79,176,198,.5)", background: smcOn ? "#4fb0c6" : "transparent", color: smcOn ? "#08060a" : "#4fb0c6", fontWeight: 700 }}>SMC/ICT</button>
      <div style={{ display: "flex", gap: 4 }}>
        {["1M", "3M", "6M", "1Y"].map((tf) => (
          <button key={tf} onClick={() => setTfRange(tf)} style={{ fontFamily: "inherit", fontSize: 11, padding: "4px 9px", borderRadius: 6, cursor: "pointer", border: "1px solid rgba(255,64,64,.2)", background: tf === tfRange ? "#140e15" : "transparent", color: tf === tfRange ? "#ff5757" : "#8f8288", fontWeight: tf === tfRange ? 700 : 400 }}>{tf}</button>
        ))}
      </div>
      {!expanded && <button onClick={() => setFull(true)} style={{ fontFamily: "inherit", fontSize: 11, padding: "4px 9px", borderRadius: 6, cursor: "pointer", border: "1px solid rgba(255,64,64,.25)", background: "transparent", color: "#b7a8ad" }}>⤢ Full</button>}
    </div>
  );

  const body = (
    <>
      {loading && <div style={{ display: "flex", justifyContent: "center", padding: 40 }}><Spinner size={18} /></div>}
      {!loading && !tech.available && <EmptyState title="Chart unavailable" description={`No series for ${symbol} (${chart?.status || chart?.error || "unavailable"}).`} />}
      {!loading && tech.available && (
        <>
          <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 8 }}>
            <div style={{ fontSize: 22, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{tech.last?.toFixed(2)}</div>
            <div style={{ color: tech.day >= 0 ? "#2ee27a" : "#ff4d4d", fontSize: 13, fontWeight: 600 }}>{pct(tech.day)}</div>
            <Badge variant="soft" label={`${symbol} · ${tfRange}`} />
          </div>
          <Candles tech={tech} smc={smcOn ? smcData?.smc : null} zones={deskZones} trade={deskTrade} height={expanded ? 480 : 220} />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
            <Badge variant="soft" label={`Trend ${tech.trend}`} color={tech.trend === "UPTREND" ? "#2ee27a" : tech.trend === "DOWNTREND" ? "#ff4d4d" : "var(--status-neutral)"} />
            {tech.rsi != null && <Badge variant="soft" label={`RSI ${tech.rsi.toFixed(0)}`} color={tech.rsi > 70 ? "#ff4d4d" : tech.rsi < 30 ? "#2ee27a" : "#ffab3d"} />}
            {tech.l20 != null && <Badge variant="soft" label={`MA20 ${tech.l20.toFixed(1)}`} />}
            {tech.l50 != null && <Badge variant="soft" label={`MA50 ${tech.l50.toFixed(1)}`} />}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8, background: "#0b0709", border: "1px solid rgba(255,64,64,.12)", borderRadius: 8, padding: "8px 11px" }}>
            <span style={{ fontSize: 10, letterSpacing: ".08em", color: "#8f8288", fontWeight: 700 }}>VOLUME DESK</span>
            <Badge variant="soft" color={tech.lastSig === "BUY" ? "#2ee27a" : tech.lastSig === "SELL" ? "#ff4d4d" : "var(--status-neutral)"} label={tech.lastSig ? `latest signal: ${tech.lastSig}` : "no volume signal"} />
            <Text tone="disabled" size="xs">Signal on a volume spike (&gt;1.5× {tfRange} avg) — BUY up candle, SELL down candle. Drawn as arrows.</Text>
          </div>
          {smcOn && smcData?.smc && (
            <div style={{ marginTop: 8, background: "#0b0709", border: "1px solid rgba(79,176,198,.25)", borderRadius: 8, padding: "10px 12px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
                <span style={{ color: "#4fb0c6", fontSize: 11, fontWeight: 700, letterSpacing: ".08em" }}>ICT / SMC</span>
                <Badge variant="soft" color={smcData.smc.trend === "UP" ? "#2ee27a" : smcData.smc.trend === "DOWN" ? "#ff4d4d" : "var(--status-neutral)"} label={`structure ${smcData.smc.trend}`} />
                {smcData.smc.structure_break && <Badge variant="soft" color="#c99bff" label={`${smcData.smc.structure_break.type} ${smcData.smc.structure_break.dir}`} />}
                {smcData.smc.inducement && <Badge variant="soft" color="#8fb3ff" label={`IDM ${smcData.smc.inducement.side} ${smcData.smc.inducement.price}`} />}
              </div>
              <Text tone="muted" size="xs" style={{ display: "block", lineHeight: 1.6 }}>
                <b style={{ color: "#f2e8ea" }}>FVG</b> gap price revisits · <b style={{ color: "#f2e8ea" }}>OB</b> last opposing candle · <b style={{ color: "#f2e8ea" }}>BOS/CHoCH</b> trend continues/flips · <b style={{ color: "#f2e8ea" }}>IDM</b> liquidity swept first · <b style={{ color: "#f2e8ea" }}>EQ</b> range midpoint ({smcData.smc.premium_discount?.current_zone}).
              </Text>
            </div>
          )}
          <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>Descriptive analytics · research only, not a signal or advice.</Text>
        </>
      )}
    </>
  );

  return (
    <div>
      {controls}
      {body}
      {full && !expanded && (
        <div onClick={() => setFull(false)} style={{ position: "fixed", inset: 0, background: "rgba(4,3,7,0.9)", zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ width: "min(1200px,96vw)", background: "#0f0b10", border: "1px solid rgba(255,64,64,.25)", borderRadius: 12, padding: 18 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <span style={{ fontWeight: 700, fontSize: 16 }}>{symbol} · {tfRange}</span>
              <div style={{ flexGrow: 1 }} />
              <button onClick={() => setFull(false)} style={{ fontFamily: "inherit", fontSize: 12, padding: "5px 12px", borderRadius: 6, cursor: "pointer", border: "1px solid rgba(255,42,42,.4)", background: "transparent", color: "#ff5757" }}>Close ✕</button>
            </div>
            {tech.available ? <Candles tech={tech} smc={smcOn ? smcData?.smc : null} zones={deskZones} trade={deskTrade} height={520} /> : <div style={{ padding: 60, textAlign: "center", color: "#8f8288" }}>Chart unavailable.</div>}
          </div>
        </div>
      )}
    </div>
  );
}

export function Candles({ tech, trade, smc, zones, height = 220 }) {
  const pts = tech.pts;
  const W = 560, pad = 10, padR = 62;
  const volH = Math.round(height * 0.18), gap = 6;
  const cBot = height - volH - gap;
  const highs = pts.map((p) => p.h ?? p.c), lows = pts.map((p) => p.l ?? p.c);
  const zoneList = zones ? Object.entries(zones).map(([k, z]) => ({ k, ...z })) : [];
  const smcVals = smc ? [
    ...(smc.fair_value_gaps || []).flatMap((g) => [g.top, g.bottom]),
    ...(smc.order_blocks || []).flatMap((o) => [o.top, o.bottom]),
    smc.structure_break?.price, smc.inducement?.price,
    ...(smc.liquidity || []).map((q) => q.price),
    smc.premium_discount?.high, smc.premium_discount?.low, smc.premium_discount?.equilibrium,
  ].filter((v) => v != null) : [];
  const zoneVals = zoneList.flatMap((z) => [z.low, z.high]).filter((v) => v != null);
  const extra = [tech.support, tech.resistance, trade?.entry, trade?.stop, trade?.target, ...smcVals, ...zoneVals].filter((v) => v != null);
  const hi = Math.max(...highs, ...extra), lo = Math.min(...lows, ...extra);
  const span = hi - lo || 1;
  const y = (v) => pad + (hi - v) / span * (cBot - pad * 2);
  const n = pts.length, plotW = W - padR, slot = plotW / n, bw = Math.max(2, slot * 0.6);
  const volMax = Math.max(1, ...(tech.vols || []));
  const linePts = (arr) => arr.map((v, i) => v == null ? null : `${(i * slot + slot / 2).toFixed(1)},${y(v).toFixed(1)}`).filter(Boolean).join(" ");
  const HLine = ({ v, color, label, dash = "5 4" }) => (v == null ? null : (
    <g><line x1="0" y1={y(v)} x2={plotW} y2={y(v)} stroke={color} strokeWidth="1" strokeDasharray={dash} opacity="0.9" />
      <text x={plotW + 4} y={y(v) + 3} fill={color} fontSize="9" fontFamily="IBM Plex Mono, monospace">{label} {Math.round(v * 100) / 100}</text></g>
  ));
  const Band = ({ top, bottom, rgb, label, num }) => {
    const yt = y(top), yb = y(bottom);
    return (<g><rect x="0" y={Math.min(yt, yb)} width={plotW} height={Math.max(2, Math.abs(yb - yt))} fill={`rgba(${rgb},0.10)`} stroke={`rgba(${rgb},0.4)`} strokeWidth="0.5" strokeDasharray={label === "OB" ? "3 2" : ""} />
      <text x="3" y={Math.min(yt, yb) + 9} fill={`rgba(${rgb},0.95)`} fontSize="8" fontFamily="IBM Plex Mono, monospace">{label} {num}</text></g>);
  };
  return (
    <svg viewBox={`0 0 ${W} ${height}`} width="100%" height={height} preserveAspectRatio="none" style={{ display: "block", background: "#0b0709", borderRadius: 8, border: "1px solid rgba(255,64,64,.1)" }}>
      {[0.25, 0.5, 0.75].map((g) => <line key={g} x1="0" y1={pad + g * (cBot - pad * 2)} x2={plotW} y2={pad + g * (cBot - pad * 2)} stroke="rgba(255,64,64,.06)" strokeWidth="1" />)}
      {/* S/R zones (drawn first, behind everything) */}
      {zoneList.map((z, i) => {
        const yt = y(z.high), yb = y(z.low), isR = z.k[0] === "R", rgb = isR ? "255,106,106" : "46,226,122";
        return (
          <g key={`z${i}`}>
            <rect x="0" y={Math.min(yt, yb)} width={plotW} height={Math.max(2, Math.abs(yb - yt))} fill={`rgba(${rgb},0.06)`} stroke={`rgba(${rgb},0.45)`} strokeWidth="0.6" strokeDasharray="4 3" />
            <text x={plotW + 4} y={(yt + yb) / 2 + 3} fill={`rgba(${rgb},0.95)`} fontSize="9" fontWeight="700" fontFamily="IBM Plex Mono, monospace">{z.k}</text>
          </g>
        );
      })}
      {smc && (smc.fair_value_gaps || []).map((g, i) => <Band key={`f${i}`} top={g.top} bottom={g.bottom} rgb={g.dir === "bullish" ? "46,226,122" : "255,77,77"} label="FVG" num={g.bottom} />)}
      {smc && (smc.order_blocks || []).map((o, i) => <Band key={`o${i}`} top={o.top} bottom={o.bottom} rgb={o.dir === "bullish" ? "79,176,198" : "255,171,61"} label="OB" num={o.bottom} />)}
      {pts.map((p, i) => {
        const x = i * slot + slot / 2, up = (p.c ?? 0) >= (p.o ?? p.c ?? 0), col = up ? "#2ee27a" : "#ff4d4d";
        const yo = y(p.o ?? p.c), yc = y(p.c), top = Math.min(yo, yc), h = Math.max(1.5, Math.abs(yc - yo));
        return <g key={i}><line x1={x} y1={y(p.h ?? p.c)} x2={x} y2={y(p.l ?? p.c)} stroke={col} strokeWidth="1" /><rect x={x - bw / 2} y={top} width={bw} height={h} fill={col} /></g>;
      })}
      {tech.s50 && <polyline fill="none" stroke="#4fb0c6" strokeWidth="1.2" opacity="0.7" points={linePts(tech.s50)} />}
      {tech.s20 && <polyline fill="none" stroke="#ffab3d" strokeWidth="1.2" opacity="0.85" points={linePts(tech.s20)} />}
      {smc?.structure_break && <HLine v={smc.structure_break.price} color="#c99bff" label={smc.structure_break.type} dash="1 2" />}
      {smc?.inducement && <HLine v={smc.inducement.price} color="#8fb3ff" label="IDM" dash="2 2" />}
      {smc && (smc.liquidity || []).map((q, i) => <HLine key={`l${i}`} v={q.price} color="#8fb3ff" label={q.side === "buy" ? "BSL" : "SSL"} dash="1 3" />)}
      {smc?.premium_discount && <HLine v={smc.premium_discount.equilibrium} color="#8f8288" label="EQ" dash="1 4" />}
      {zoneList.length === 0 && <HLine v={tech.resistance} color="#ff6a6a" label="R" />}
      {zoneList.length === 0 && <HLine v={tech.support} color="#2ee27a" label="S" />}
      {trade && <HLine v={trade.entry} color="#f2e8ea" label="Entry" dash="2 3" />}
      {trade && <HLine v={trade.target} color="#2ee27a" label="Target" dash="6 3" />}
      {trade && <HLine v={trade.stop} color="#ff4d4d" label="Stop" dash="6 3" />}
      {(tech.vols || []).map((v, i) => { const x = i * slot + slot / 2, bh = Math.max(0.5, (v / volMax) * (volH - 2)), up = (pts[i]?.c ?? 0) >= (pts[i]?.o ?? pts[i]?.c ?? 0); return <rect key={`v${i}`} x={x - bw / 2} y={height - bh} width={bw} height={bh} fill={up ? "rgba(46,226,122,0.5)" : "rgba(255,77,77,0.5)"} />; })}
      {(tech.volSignals || []).map((sig, i) => {
        if (!sig) return null;
        const x = i * slot + slot / 2;
        if (sig === "BUY") { const yb = y(pts[i].l ?? pts[i].c) + 4; return <polygon key={`s${i}`} points={`${x - 4},${yb + 7} ${x + 4},${yb + 7} ${x},${yb}`} fill="#2ee27a" />; }
        const yt = y(pts[i].h ?? pts[i].c) - 4; return <polygon key={`s${i}`} points={`${x - 4},${yt - 7} ${x + 4},${yt - 7} ${x},${yt}`} fill="#ff4d4d" />;
      })}
    </svg>
  );
}
