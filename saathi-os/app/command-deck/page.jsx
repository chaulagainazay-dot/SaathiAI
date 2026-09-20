"use client";
/**
 * Command Deck — unified financial intelligence in one frame.
 * Combines the Financial Browser (embedded), NEPSE Tracker, Chart Analysis, Trading Guardian
 * and an AI-company research/plan strip that reads the owner's observed portfolio.
 *
 * STRICT GOVERNANCE: observation-only. Nothing here places trades or moves funds. The AI panel
 * produces deterministic, evidence-labeled RESEARCH + a draft plan the owner reviews — never
 * financial advice and never an execution. All numbers come from real endpoints; when a source
 * is unavailable the panel says so honestly instead of showing fabricated data.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { API_BASE, afetch } from "@/lib/api";
import {
  Panel, Card, Button, Badge, StatusBadge, Heading, Text, Divider, Spinner,
  EmptyState, ErrorState, Pill, Eyebrow,
} from "@/components/ui";
import FinancialBrowserPanel from "@/components/finance/FinancialBrowserPanel";
import { Candles } from "@/components/finance/ChartAnalysis";
import { MarketNews, TradingSignals } from "@/components/finance/NewsSignals";
import TradeDesk from "@/components/finance/TradeDesk";

const CHART_SYMBOLS = ["NABIL", "HDL", "UPPER", "GBIME", "NRIC"];
const NEPSE_POLL_MS = 30000;

function api(path, opts = {}) {
  return afetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: { "content-type": "application/json", ...(opts.headers || {}) },
    ...opts,
  }).then(async (r) => {
    let body = {};
    try { body = await r.json(); } catch { body = {}; }
    return { ok: r.ok, status: r.status, body };
  });
}

// ── pure helpers ────────────────────────────────────────────────────────────
const numOr = (v, d = null) => {
  const n = typeof v === "number" ? v : parseFloat(String(v ?? "").replace(/,/g, ""));
  return Number.isFinite(n) ? n : d;
};
const fmtNpr = (n) =>
  n == null ? "—" : "NPR " + Math.round(n).toLocaleString("en-IN");
const pct = (n, dp = 2) => (n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(dp)}%`);

function sma(closes, period) {
  const out = [];
  let s = 0;
  for (let i = 0; i < closes.length; i++) {
    s += closes[i];
    if (i >= period) s -= closes[i - period];
    out.push(i >= period - 1 ? s / period : null);
  }
  return out;
}
function rsi14(closes) {
  if (closes.length < 15) return null;
  let g = 0, l = 0;
  for (let i = 1; i <= 14; i++) {
    const d = closes[i] - closes[i - 1];
    if (d >= 0) g += d; else l -= d;
  }
  g /= 14; l /= 14;
  for (let i = 15; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    g = (g * 13 + (d > 0 ? d : 0)) / 14;
    l = (l * 13 + (d < 0 ? -d : 0)) / 14;
  }
  if (l === 0) return 100;
  const rs = g / l;
  return 100 - 100 / (1 + rs);
}

export default function CommandDeckPage() {
  const [nepse, setNepse] = useState(null);
  const [nepseErr, setNepseErr] = useState("");
  const [symbol, setSymbol] = useState("NABIL");
  const [chart, setChart] = useState(null);
  const [chartLoading, setChartLoading] = useState(true);
  const [smcOn, setSmcOn] = useState(true);       // auto-draw ICT/SMC by default
  const [smcData, setSmcData] = useState(null);
  const [tfRange, setTfRange] = useState("3M");   // timeframe
  const [symInput, setSymInput] = useState("");   // stock search box
  const [fullChart, setFullChart] = useState(false);
  const [providers, setProviders] = useState(null);
  const [runtimes, setRuntimes] = useState([]);
  const [portfolio, setPortfolio] = useState(null);
  const [booting, setBooting] = useState(true);

  // Technical Analysis Team (agent-assisted; NEPSE + crypto)
  const [taMarket, setTaMarket] = useState("NEPSE");
  const [taSymbol, setTaSymbol] = useState("NABIL");
  const [taResult, setTaResult] = useState(null);
  const [taLoading, setTaLoading] = useState(false);
  const [taStrategy, setTaStrategy] = useState(null);
  const [stratLoading, setStratLoading] = useState(false);

  const runStrategy = useCallback(async (market, sym) => {
    if (!sym.trim()) return;
    setStratLoading(true); setTaStrategy(null);
    const r = await api("/api/v1/market/analysis/strategy", { method: "POST", body: JSON.stringify({ market, symbol: sym.trim() }) });
    setTaStrategy(r.ok ? r.body : { available: false, error: r.body?.error || `HTTP ${r.status}` });
    setStratLoading(false);
  }, []);

  const runTA = useCallback(async (market, sym) => {
    if (!sym.trim()) return;
    setTaLoading(true); setTaResult(null);
    const r = await api("/api/v1/market/analysis/technical", {
      method: "POST", body: JSON.stringify({ market, symbol: sym.trim() }),
    });
    setTaResult(r.ok ? r.body : { available: false, error: r.body?.error || `HTTP ${r.status}` });
    setTaLoading(false);
  }, []);

  // Paper trading agent (SIMULATION ONLY)
  const [journal, setJournal] = useState(null);
  const [paBusy, setPaBusy] = useState("");
  const [paMsg, setPaMsg] = useState("");

  const loadJournal = useCallback(async () => {
    const r = await api("/api/v1/trading/paper/journal?limit=20");
    if (r.ok) setJournal(r.body);
  }, []);

  const runAgent = useCallback(async (market, sym) => {
    setPaBusy("run"); setPaMsg("");
    const r = await api("/api/v1/trading/paper/open", { method: "POST", body: JSON.stringify({ market, symbol: sym }) });
    if (r.ok && r.body?.status === "OPEN") setPaMsg(`Opened dummy ${r.body.side} ${r.body.symbol} @ ${r.body.entry}`);
    else if (r.ok && r.body?.setup === false) setPaMsg(`No clean setup for ${sym}: ${r.body.reason}`);
    else setPaMsg(r.body?.error || "Run failed");
    await loadJournal();
    setPaBusy("");
  }, [loadJournal]);

  const evaluateTrades = useCallback(async () => {
    setPaBusy("eval"); setPaMsg("");
    const r = await api("/api/v1/trading/paper/evaluate", { method: "POST", body: "{}" });
    if (r.ok) setPaMsg(`Evaluated ${r.body.evaluated} open · closed ${r.body.closed?.length || 0}`);
    await loadJournal();
    setPaBusy("");
  }, [loadJournal]);

  const loadNepse = useCallback(async () => {
    const r = await api("/api/v1/market/nepse/live/full");
    if (r.ok) { setNepse(r.body); setNepseErr(""); }
    else setNepseErr(r.body?.error || `HTTP ${r.status}`);
  }, []);

  const loadChart = useCallback(async (sym, range) => {
    setChartLoading(true);
    const r = await api(`/api/v1/market/tracker/chart?symbol=${encodeURIComponent(sym)}&range=${encodeURIComponent(range)}`);
    setChart(r.ok ? r.body : { available: false, error: r.body?.error || `HTTP ${r.status}` });
    setChartLoading(false);
  }, []);

  const loadFinance = useCallback(async () => {
    const [p, rt] = await Promise.all([
      api("/api/v1/finance/providers"),
      api("/api/v1/finance/browser/runtimes"),
    ]);
    if (p.ok) setProviders(p.body);
    const rlist = rt.ok ? (rt.body.runtimes || []) : [];
    setRuntimes(rlist);
    const readable = rlist.find((r) => r.agent_read && r.runtime_state !== "CLOSED");
    if (readable) {
      const pf = await api(`/api/v1/finance/browser/portfolio?runtime_id=${encodeURIComponent(readable.runtime_id)}`);
      if (pf.ok) setPortfolio(pf.body);
    } else {
      setPortfolio(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      await Promise.all([loadNepse(), loadChart(symbol, tfRange), loadFinance(), loadJournal()]);
      setBooting(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const id = setInterval(loadNepse, NEPSE_POLL_MS);
    return () => clearInterval(id);
  }, [loadNepse]);

  useEffect(() => { loadChart(symbol, tfRange); }, [symbol, tfRange, loadChart]);

  const loadSMC = useCallback(async (sym) => {
    const r = await api("/api/v1/market/analysis/smc", { method: "POST", body: JSON.stringify({ market: "NEPSE", symbol: sym }) });
    setSmcData(r.ok ? r.body : null);
  }, []);
  useEffect(() => { if (smcOn) loadSMC(symbol); }, [smcOn, symbol, loadSMC]);

  const [deskData, setDeskData] = useState(null);
  const loadDesk = useCallback(async (sym) => {
    const r = await api("/api/v1/market/analysis/desk", { method: "POST", body: JSON.stringify({ market: "NEPSE", symbol: sym }) });
    setDeskData(r.ok ? r.body : null);
  }, []);
  useEffect(() => { loadDesk(symbol); }, [symbol, loadDesk]);
  const deckDeskTrade = deskData?.trade_setup?.setup ? { entry: deskData.trade_setup.entry, stop: deskData.trade_setup.stop, target: deskData.trade_setup.target } : null;
  const deckDeskZones = deskData?.sr_zones || null;

  // ── derived: chart technicals (deterministic, from real OHLC) ──
  const tech = useMemo(() => {
    const pts = (chart?.ohlc || []).map((p) => ({
      d: p.business_date, o: numOr(p.open), h: numOr(p.high), l: numOr(p.low), c: numOr(p.close),
    })).filter((p) => p.c != null);
    if (pts.length < 5) return { pts: [], available: false };
    const closes = pts.map((p) => p.c);
    const s20 = sma(closes, 20), s50 = sma(closes, 50);
    const last = closes[closes.length - 1];
    const prev = closes[closes.length - 2];
    const day = prev ? ((last - prev) / prev) * 100 : null;
    const l20 = s20[s20.length - 1], l50 = s50[s50.length - 1];
    const rsi = rsi14(closes);
    const trend = l20 != null && l50 != null
      ? (last > l20 && l20 >= l50 ? "UPTREND" : last < l20 && l20 <= l50 ? "DOWNTREND" : "SIDEWAYS")
      : "INSUFFICIENT";
    const win = pts.slice(-48);
    // Support/resistance drawn by the desk: recent swing low / range high in the window.
    const support = Math.min(...win.map((p) => p.l ?? p.c));
    const resistance = Math.max(...win.map((p) => p.h ?? p.c));
    // Volume desk: align volumes to the window, flag spikes (>1.5x avg) as buy/sell by candle dir.
    const volAll = (chart?.volume || []).map((v) => numOr(v.volume) || 0);
    const vols = volAll.slice(-48);
    const avgVol = vols.length ? vols.reduce((a, b) => a + b, 0) / vols.length : 0;
    const volSignals = win.map((p, i) => {
      const v = vols[i] ?? 0;
      if (avgVol > 0 && v >= 1.5 * avgVol && p.o != null) {
        return (p.c >= p.o) ? "BUY" : "SELL";
      }
      return null;
    });
    const lastSig = [...volSignals].reverse().find((s) => s) || null;
    return { pts: win, s20: s20.slice(-48), s50: s50.slice(-48), closes, last, day, rsi, trend, l20, l50,
             support, resistance, vols, avgVol, volSignals, lastSig, available: true };
  }, [chart]);

  // ── derived: portfolio ──
  const pf = useMemo(() => {
    const view = portfolio?.available ? portfolio.view : null;
    const positions = (view?.positions || []).map((p) => ({
      symbol: p.symbol,
      qty: numOr(p.quantity),
      avg: numOr(p.average_cost),
      mv: numOr(p.market_value),
      ltp: numOr(p.current_price),
    }));
    const total = numOr(view?.total_value) ??
      (positions.length ? positions.reduce((a, p) => a + (p.mv || 0), 0) : null);
    const largest = positions.reduce((a, p) => (p.mv || 0) > (a?.mv || 0) ? p : a, null);
    const conc = largest && total ? (largest.mv / total) * 100 : null;
    return { view, positions, total, largest, conc, currency: view?.currency || "NPR", state: portfolio?.state };
  }, [portfolio]);

  // ── derived: guardian (from real capability matrix) ──
  // /api/v1/finance/providers → { providers: { TMS: {agent_actions, ...}, ... }, components, policies }
  const guardian = useMemo(() => {
    const perProvider = providers?.providers || {};
    const actions = Object.values(perProvider)
      .map((v) => (v && typeof v === "object" ? String(v.agent_actions || "") : ""))
      .filter(Boolean);
    const allBlocked = actions.length > 0 && actions.every((a) => /PROHIBIT|UNSUPPORT|NONE/i.test(a));
    return { allBlocked, sample: actions[0] || "PROHIBITED_AGENT_ACTION" };
  }, [providers]);


  // Exact keys from NepseLiveMarketSnapshot.to_public()
  const idx = numOr(nepse?.nepse_index);
  const idxChg = numOr(nepse?.index_change);
  const idxPct = numOr(nepse?.index_change_percent);
  const adv = numOr(nepse?.advancers);
  const dec = numOr(nepse?.decliners);
  const unch = numOr(nepse?.unchanged);
  const marketState = nepse?.market_status;
  // No top_gainers/losers fields — derive movers from per-security rows.
  const { movers, losers } = useMemo(() => {
    const secs = (nepse?.securities || [])
      .map((s) => ({ symbol: s.symbol, pct: numOr(s.percent_change) }))
      .filter((s) => s.symbol && s.pct != null);
    const byPct = [...secs].sort((a, b) => b.pct - a.pct);
    return { movers: byPct.slice(0, 3), losers: byPct.slice(-2).reverse() };
  }, [nepse]);

  return (
    <div style={{ maxWidth: 1440, margin: "0 auto", padding: "24px 24px 56px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <Eyebrow>Finance · Unified</Eyebrow>
          <Heading level={1} size="xl" style={{ marginTop: 4 }}>Command Deck</Heading>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <Pill color="#7CF5E4">Observation-only</Pill>
          <Pill color="#FF5A5A">No BUY · SELL · TRANSFER · WITHDRAW</Pill>
          <StatusBadge status={marketState ? "success" : "neutral"} label={marketState ? `NEPSE · ${marketState}` : "NEPSE"} />
        </div>
      </div>
      <Text tone="muted" size="sm" style={{ display: "block", marginTop: 8, maxWidth: 780 }}>
        One frame: your embedded provider browser, live NEPSE, chart analysis, the Trading Guardian and an
        AI research-and-plan strip that reads your observed portfolio. Research only — never financial advice,
        never an execution. Every figure is live from SaathiOS; unavailable sources say so.
      </Text>

      {booting && <div style={{ display: "flex", justifyContent: "center", padding: 48 }}><Spinner size={22} /></div>}

      {!booting && (
        <>
          {/* KPI row */}
          <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", gap: 12, marginTop: 20 }}>
            <Kpi label="Portfolio value" value={pf.total != null ? fmtNpr(pf.total) : "Awaiting read"} tone={pf.total != null ? "" : "muted"} />
            <Kpi label="Positions" value={pf.positions.length ? String(pf.positions.length) : "—"} />
            <Kpi label="Top concentration" value={pf.conc != null ? `${pf.conc.toFixed(0)}%` : "—"} tone={pf.conc > 35 ? "warn" : ""} />
            <Kpi label="NEPSE index" value={idx != null ? idx.toLocaleString("en-IN") : "—"} sub={idxPct != null ? pct(idxPct) : ""} subTone={idxPct >= 0 ? "up" : "down"} />
            <Kpi label={`${symbol} last`} value={tech.last != null ? tech.last.toFixed(2) : "—"} sub={tech.day != null ? pct(tech.day) : ""} subTone={tech.day >= 0 ? "up" : "down"} />
            <Kpi label="AI agents" value="Research · TA · Risk · Plan" small />
          </section>

          {/* Main grid */}
          <section style={{ display: "grid", gridTemplateColumns: "360px minmax(0,1fr) 372px", gap: 16, marginTop: 16, alignItems: "start" }}>
            {/* LEFT */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* Financial Browser */}
              <Panel style={{ padding: 0, overflow: "hidden" }}>
                <PanelHead title="Financial Browser" right={<StatusBadge status="success" label="EMBEDDED" />} expandHref="/command-deck/browser" />
                <FinancialBrowserPanel onPortfolio={(env) => { if (env?.available) setPortfolio(env); }} />
              </Panel>

              {/* NEPSE Tracker */}
              <Panel style={{ padding: 0 }}>
                <PanelHead title="NEPSE Tracker" right={<Text tone="disabled" size="xs" mono>{nepse?.freshness ? String(nepse.freshness).toLowerCase() : "live"}</Text>} />
                <div style={{ padding: 14 }}>
                  {nepseErr && <Text tone="muted" size="xs">Feed unavailable: {nepseErr}</Text>}
                  {!nepseErr && (
                    <>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
                        <div>
                          <Text tone="muted" size="xs" mono>NEPSE INDEX</Text>
                          <div style={{ fontSize: 24, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                            {idx != null ? idx.toLocaleString("en-IN") : "—"}
                          </div>
                        </div>
                        <div style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                          <span style={{ color: idxPct >= 0 ? "#2ee27a" : "#ff4d4d", fontSize: 13, fontWeight: 600 }}>
                            {idxChg != null ? `${idxChg >= 0 ? "▲" : "▼"} ${Math.abs(idxChg).toFixed(2)}` : ""} {idxPct != null ? pct(idxPct) : ""}
                          </span>
                        </div>
                      </div>
                      {(adv != null || dec != null) && (
                        <div style={{ marginTop: 12 }}>
                          <Breadth adv={adv} unch={unch} dec={dec} />
                        </div>
                      )}
                      <MoversList gainers={movers} losers={losers} />
                    </>
                  )}
                </div>
              </Panel>
            </div>

            {/* CENTER */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <Panel style={{ padding: 0 }}>
                <PanelHead
                  title={`Chart Analysis · ${symbol}`}
                  expandHref="/command-deck/chart"
                  right={
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                      <button onClick={() => setSmcOn((v) => !v)} title="Draw ICT / Smart Money Concepts structure"
                        style={{ fontFamily: "inherit", fontSize: 11, padding: "3px 9px", borderRadius: 100, cursor: "pointer",
                          border: "1px solid rgba(79,176,198,.5)",
                          background: smcOn ? "#4fb0c6" : "transparent", color: smcOn ? "#08060a" : "#4fb0c6", fontWeight: 700 }}>
                        SMC/ICT
                      </button>
                      <button onClick={() => setFullChart(true)} title="Open full chart"
                        style={{ fontFamily: "inherit", fontSize: 11, padding: "3px 9px", borderRadius: 100, cursor: "pointer",
                          border: "1px solid rgba(255,64,64,.25)", background: "transparent", color: "#b7a8ad" }}>
                        ⤢ Full chart
                      </button>
                    </div>
                  }
                />
                <div style={{ padding: 14 }}>
                  {/* Stock search + presets + timeframe */}
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
                    <input
                      value={symInput}
                      onChange={(e) => setSymInput(e.target.value.toUpperCase())}
                      onKeyDown={(e) => { if (e.key === "Enter" && symInput.trim()) { setSymbol(symInput.trim()); setSymInput(""); } }}
                      placeholder="Search stock (e.g. NABIL, NTC, SCB)…"
                      style={{ fontFamily: "inherit", fontSize: 12, padding: "6px 10px", borderRadius: 8, width: 220,
                        background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" }}
                    />
                    <button onClick={() => { if (symInput.trim()) { setSymbol(symInput.trim()); setSymInput(""); } }}
                      style={{ fontFamily: "inherit", fontSize: 11, padding: "6px 10px", borderRadius: 8, cursor: "pointer",
                        border: "1px solid rgba(255,64,64,.25)", background: "transparent", color: "#b7a8ad" }}>Search</button>
                    <div style={{ display: "flex", gap: 4 }}>
                      {CHART_SYMBOLS.map((s) => (
                        <button key={s} onClick={() => setSymbol(s)}
                          style={{ fontFamily: "inherit", fontSize: 11, padding: "4px 8px", borderRadius: 100, cursor: "pointer",
                            border: "1px solid rgba(255,64,64,.2)", background: s === symbol ? "#ff2a2a" : "transparent",
                            color: s === symbol ? "#08060a" : "#8f8288", fontWeight: s === symbol ? 700 : 400 }}>{s}</button>
                      ))}
                    </div>
                    <div style={{ flexGrow: 1 }} />
                    <div style={{ display: "flex", gap: 4 }}>
                      {["1M", "3M", "6M", "1Y"].map((tf) => (
                        <button key={tf} onClick={() => setTfRange(tf)}
                          style={{ fontFamily: "inherit", fontSize: 11, padding: "4px 9px", borderRadius: 6, cursor: "pointer",
                            border: "1px solid rgba(255,64,64,.2)", background: tf === tfRange ? "#140e15" : "transparent",
                            color: tf === tfRange ? "#ff5757" : "#8f8288", fontWeight: tf === tfRange ? 700 : 400 }}>{tf}</button>
                      ))}
                    </div>
                  </div>
                  {chartLoading && <div style={{ display: "flex", justifyContent: "center", padding: 40 }}><Spinner size={18} /></div>}
                  {!chartLoading && !tech.available && (
                    <EmptyState title="Chart unavailable" description={`No historical series for ${symbol} (${chart?.status || chart?.error || "unavailable"}).`} />
                  )}
                  {!chartLoading && tech.available && (
                    <>
                      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 8 }}>
                        <div style={{ fontSize: 22, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{tech.last?.toFixed(2)}</div>
                        <div style={{ color: tech.day >= 0 ? "#2ee27a" : "#ff4d4d", fontSize: 13, fontWeight: 600 }}>{pct(tech.day)}</div>
                        <div style={{ flexGrow: 1 }} />
                        <Badge variant="soft" label={`${chart?.source_badge || "tracker"}`} />
                      </div>
                      <Candles tech={tech} trade={(journal?.trades || []).find((t) => t.symbol === symbol && t.status === "OPEN") || deckDeskTrade} smc={smcOn ? smcData?.smc : null} zones={deckDeskZones} />
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
                        <Badge variant="soft" label={`Trend ${tech.trend}`} color={tech.trend === "UPTREND" ? "#2ee27a" : tech.trend === "DOWNTREND" ? "#ff4d4d" : "var(--status-neutral)"} />
                        {tech.rsi != null && <Badge variant="soft" label={`RSI ${tech.rsi.toFixed(0)}`} color={tech.rsi > 70 ? "#ff4d4d" : tech.rsi < 30 ? "#2ee27a" : "#ffab3d"} />}
                        {tech.l20 != null && <Badge variant="soft" label={`MA20 ${tech.l20.toFixed(1)}`} />}
                        {tech.l50 != null && <Badge variant="soft" label={`MA50 ${tech.l50.toFixed(1)}`} />}
                      </div>
                      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 8, fontSize: 10, color: "#8f8288" }}>
                        <span><span style={{ color: "#ffab3d" }}>—</span> MA20</span>
                        <span><span style={{ color: "#4fb0c6" }}>—</span> MA50</span>
                        <span><span style={{ color: "#2ee27a" }}>--</span> Support</span>
                        <span><span style={{ color: "#ff6a6a" }}>--</span> Resistance</span>
                        <span><span style={{ color: "#2ee27a" }}>▲</span>/<span style={{ color: "#ff4d4d" }}>▼</span> volume buy/sell</span>
                        <span><span style={{ color: "#f2e8ea" }}>··</span> Entry / Target / Stop</span>
                      </div>
                      {/* Volume desk */}
                      <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8, background: "#0b0709", border: "1px solid rgba(255,64,64,.12)", borderRadius: 8, padding: "8px 11px" }}>
                        <span style={{ fontSize: 10, letterSpacing: ".08em", color: "#8f8288", fontWeight: 700 }}>VOLUME DESK</span>
                        <Badge variant="soft"
                          color={tech.lastSig === "BUY" ? "#2ee27a" : tech.lastSig === "SELL" ? "#ff4d4d" : "var(--status-neutral)"}
                          label={tech.lastSig ? `latest signal: ${tech.lastSig}` : "no volume signal"} />
                        <Text tone="disabled" size="xs">A signal fires on a volume spike (&gt;1.5× the {tfRange} average) — BUY on an up candle, SELL on a down candle. Drawn as arrows on the chart.</Text>
                      </div>
                      <div style={{ marginTop: 8, background: "#0b0709", border: "1px solid rgba(255,64,64,.12)", borderRadius: 8, padding: "9px 11px" }}>
                        <Text size="xs" tone="muted" style={{ display: "block" }}>
                          <strong style={{ color: "#f2e8ea" }}>Plain read:</strong> {symbol} is in a{" "}
                          <strong style={{ color: tech.trend === "UPTREND" ? "#2ee27a" : tech.trend === "DOWNTREND" ? "#ff4d4d" : "#ffab3d" }}>{tech.trend.toLowerCase()}</strong>.{" "}
                          Momentum (RSI {tech.rsi != null ? tech.rsi.toFixed(0) : "—"}) is{" "}
                          {tech.rsi > 70 ? "hot — often near a pullback" : tech.rsi < 30 ? "cold — often near a bounce" : "neutral"}.{" "}
                          The desk drew support ~{tech.support?.toFixed(0)} and resistance ~{tech.resistance?.toFixed(0)} — price often reacts at these lines.
                        </Text>
                      </div>
                      {smcOn && (
                        <div style={{ marginTop: 8, background: "#0b0709", border: "1px solid rgba(79,176,198,.25)", borderRadius: 8, padding: "10px 12px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                            <span style={{ color: "#4fb0c6", fontSize: 11, fontWeight: 700, letterSpacing: ".08em" }}>ICT / SMC STRUCTURE</span>
                            {smcData?.smc?.trend && <Badge variant="soft" color={smcData.smc.trend === "UP" ? "#2ee27a" : smcData.smc.trend === "DOWN" ? "#ff4d4d" : "var(--status-neutral)"} label={`structure ${smcData.smc.trend}`} />}
                            {smcData?.smc?.structure_break && <Badge variant="soft" color="#c99bff" label={`${smcData.smc.structure_break.type} ${smcData.smc.structure_break.dir}`} />}
                          </div>
                          {!smcData?.smc && <Text tone="muted" size="xs">Loading structure… (or unavailable for {symbol}).</Text>}
                          {smcData?.smc && (
                            <Text tone="muted" size="xs" style={{ display: "block", lineHeight: 1.6 }}>
                              <b style={{ color: "#f2e8ea" }}>FVG</b> (shaded) = a price gap the market often revisits ·{" "}
                              <b style={{ color: "#f2e8ea" }}>OB</b> (dashed box) = the last opposing candle before a big move ·{" "}
                              <b style={{ color: "#f2e8ea" }}>BOS/CHoCH</b> = trend continues / trend may be flipping ·{" "}
                              <b style={{ color: "#f2e8ea" }}>BSL/SSL</b> = resting liquidity (equal highs/lows) ·{" "}
                              <b style={{ color: "#f2e8ea" }}>EQ</b> = 50% of the range ({smcData.smc.premium_discount?.current_zone} now).
                            </Text>
                          )}
                        </div>
                      )}
                      <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>
                        Descriptive analytics from third-party historical series — research only, not a signal or advice.
                      </Text>
                    </>
                  )}
                </div>
              </Panel>

              {/* AI operating loop */}
              <Panel style={{ padding: 0 }}>
                <PanelHead title="AI Company · Operating Loop" right={<Text tone="disabled" size="xs">provenance-backed · owner-gated</Text>} />
                <div style={{ padding: "14px 16px", display: "flex", alignItems: "center", flexWrap: "wrap", gap: 4 }}>
                  {["Research", "Technical", "Risk", "Plan", "Recommend"].map((step, i, arr) => (
                    <div key={step} style={{ display: "flex", alignItems: "center" }}>
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                          <span className="retro-live ok" aria-hidden="true" style={{ display: "inline-block" }} />
                          <span style={{ fontSize: 12, fontWeight: 600 }}>{step}</span>
                        </div>
                      </div>
                      {i < arr.length - 1 && <span style={{ color: "#ff2a2a", padding: "0 14px" }}>▸</span>}
                    </div>
                  ))}
                </div>
              </Panel>
            </div>

            {/* RIGHT */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* Trading Guardian */}
              <Panel style={{ padding: 0 }}>
                <PanelHead title="Trading Guardian" right={<StatusBadge status="danger" label="OBSERVATION-ONLY" />} expandHref="/command-deck/guardian" />
                <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, background: "rgba(255,42,42,.06)", border: "1px solid rgba(255,42,42,.28)", borderRadius: 9, padding: "11px 13px" }}>
                    <div style={{ fontSize: 22 }}>🛡️</div>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#ff8a8a" }}>NO TRADE AUTHORITY</div>
                      <Text tone="disabled" size="xs">agent cannot buy · sell · transfer · withdraw</Text>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {["BUY", "SELL", "TRANSFER", "WITHDRAW"].map((a) => (
                      <Badge key={a} variant="soft" color="#ff5757" label={`${a} · BLOCKED`} />
                    ))}
                  </div>
                  {pf.conc != null && (
                    <Meter label={`Concentration · ${pf.largest?.symbol || ""}`} value={pf.conc} max={100}
                      color={pf.conc > 35 ? "#ff4d4d" : pf.conc > 25 ? "#ffab3d" : "#2ee27a"}
                      caption={pf.conc > 35 ? "Above 35% single-name cap — consider rebalancing." : "Within single-name limits."} />
                  )}
                  <Text tone="disabled" size="xs">
                    Capabilities from the live provider policy matrix{guardian.allBlocked ? " — all agent actions prohibited." : "."}
                  </Text>
                </div>
              </Panel>

              {/* AI Company advisory */}
              <Panel style={{ padding: 0 }}>
                <PanelHead title="AI Company · Research & Plan" right={<Text tone="disabled" size="xs">research only · you decide</Text>} />
                <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
                  {!pf.view ? (
                    <EmptyState
                      title="No portfolio observed yet"
                      description="Open your provider in the Financial Browser and enable Saathi Read — then this reads your holdings and drafts research."
                      action={<Link href="/finance/browser"><Button size="sm" variant="secondary">Financial Browser</Button></Link>}
                    />
                  ) : (
                    <>
                      {pf.conc != null && pf.conc > 30 && pf.largest && (
                        <PlanCard symbol={pf.largest.symbol} tag="REVIEW · concentration"
                          text={`${pf.largest.symbol} is ${pf.conc.toFixed(0)}% of the portfolio — above a prudent single-name weight. A rebalance to reduce it is worth reviewing.`}
                          evidence="observed holdings" />
                      )}
                      {tech.available && (
                        <PlanCard symbol={symbol} tag={`OBSERVATION · ${tech.trend}`}
                          text={`${symbol}: ${tech.trend.toLowerCase()} on the 3-month series` +
                            (tech.rsi != null ? `, RSI ${tech.rsi.toFixed(0)}${tech.rsi > 70 ? " (stretched)" : tech.rsi < 30 ? " (weak)" : ""}` : "") +
                            ". Descriptive only — not a buy/sell signal."}
                          evidence="tracker chart" />
                      )}
                      <PlanCard symbol="Portfolio" tag="PLAN · draft"
                        text="Any position change is yours to make in your broker. SaathiOS never executes — it researches, checks risk with the Guardian, and drafts options for you to approve."
                        evidence="governance" muted />
                    </>
                  )}
                </div>
              </Panel>
            </div>
          </section>

          {/* Trade Desk (setup + volume strength + S/R zones) */}
          <Panel style={{ padding: 0, marginTop: 16 }}>
            <PanelHead title="Trade Desk" right={<Text tone="disabled" size="xs">setup · volume strength · S/R zones</Text>} />
            <TradeDesk />
          </Panel>

          {/* Technical Analysis Team (agent) */}
          <Panel style={{ padding: 0, marginTop: 16 }}>
            <PanelHead title="Technical Analysis Team · agent" right={<Text tone="disabled" size="xs">NEPSE + Crypto · research only, not advice</Text>} />
            <div style={{ padding: 14 }}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <div style={{ display: "flex", gap: 4 }}>
                  {["NEPSE", "CRYPTO"].map((m) => (
                    <button key={m} onClick={() => { setTaMarket(m); setTaSymbol(m === "NEPSE" ? "NABIL" : "BTC"); }}
                      style={{ fontFamily: "inherit", fontSize: 12, padding: "6px 12px", borderRadius: 8, cursor: "pointer",
                        border: "1px solid rgba(255,64,64,.25)",
                        background: m === taMarket ? "#ff2a2a" : "transparent",
                        color: m === taMarket ? "#08060a" : "#b7a8ad", fontWeight: m === taMarket ? 700 : 400 }}>
                      {m}
                    </button>
                  ))}
                </div>
                <input
                  value={taSymbol}
                  onChange={(e) => setTaSymbol(e.target.value.toUpperCase())}
                  onKeyDown={(e) => { if (e.key === "Enter") runTA(taMarket, taSymbol); }}
                  placeholder={taMarket === "NEPSE" ? "NABIL, HDL, UPPER…" : "BTC, ETH, SOL…"}
                  style={{ fontFamily: "inherit", fontSize: 13, padding: "7px 10px", borderRadius: 8, width: 180,
                    background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" }}
                />
                <Button size="sm" onClick={() => runTA(taMarket, taSymbol)} disabled={taLoading}>
                  {taLoading ? "Analyzing…" : "Run analysis"}
                </Button>
                <Button size="sm" variant="secondary" onClick={() => runStrategy(taMarket, taSymbol)} disabled={stratLoading}
                  title="ICT playbook: 15m structure mapping (crypto) + potential IDM">
                  {stratLoading ? "Building…" : "Strategy (ICT + IDM)"}
                </Button>
                <div style={{ flexGrow: 1 }} />
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {["Trend", "Momentum", "Levels", "Risk"].map((a) => <Badge key={a} variant="soft" label={a} />)}
                </div>
              </div>

              {taLoading && <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 14 }}><Spinner size={16} /><Text tone="muted" size="sm">The desk is reading {taSymbol}…</Text></div>}

              {!taLoading && taResult && !taResult.available && (
                <div style={{ marginTop: 12 }}>
                  <EmptyState title="Analysis unavailable" description={`${taSymbol}: ${taResult.error || "no data"}. Try another symbol or market.`} />
                </div>
              )}

              {!taLoading && taResult && taResult.available && (
                <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "minmax(0,1fr) 300px", gap: 16, alignItems: "start" }}>
                  <div style={{ background: "#0b0709", border: "1px solid rgba(255,64,64,.14)", borderRadius: 10, padding: "14px 16px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                      <span style={{ fontWeight: 700, fontSize: 14 }}>{taResult.market} · {taResult.symbol}</span>
                      <Badge variant="soft" color={taResult.evidence?.trend === "UPTREND" ? "#2ee27a" : taResult.evidence?.trend === "DOWNTREND" ? "#ff4d4d" : "var(--status-neutral)"} label={taResult.evidence?.trend} />
                      <div style={{ flexGrow: 1 }} />
                      <Text tone="disabled" size="xs" mono>agent: {taResult.provider}</Text>
                    </div>
                    <div style={{ whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.6, color: "#dccfd3" }}>
                      {String(taResult.analysis || "").replace(/^#+\s*/gm, "").replace(/\*\*/g, "")}
                    </div>
                    <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 10 }}>{taResult.disclaimer}</Text>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288" }}>DETERMINISTIC EVIDENCE</div>
                    <EvRow k="Last" v={taResult.evidence?.last} />
                    <EvRow k="Change %" v={taResult.evidence?.change_pct} tone={(taResult.evidence?.change_pct ?? 0) >= 0 ? "up" : "down"} />
                    <EvRow k="RSI(14)" v={taResult.evidence?.rsi14} />
                    <EvRow k="SMA20" v={taResult.evidence?.sma20} />
                    <EvRow k="SMA50" v={taResult.evidence?.sma50} />
                    <EvRow k="Support" v={taResult.evidence?.support} />
                    <EvRow k="Resistance" v={taResult.evidence?.resistance} />
                    <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 4 }}>source: {taResult.source}</Text>
                  </div>
                </div>
              )}

              {stratLoading && <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 12 }}><Spinner size={16} /><Text tone="muted" size="sm">Building the ICT playbook ({taMarket === "CRYPTO" ? "15m structure" : "daily structure"} + IDM)…</Text></div>}
              {!stratLoading && taStrategy && (
                <div style={{ marginTop: 12, background: "#0b0709", border: "1px solid rgba(201,155,255,.3)", borderRadius: 10, padding: "12px 14px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
                    <span style={{ color: "#c99bff", fontSize: 11, fontWeight: 700, letterSpacing: ".08em" }}>ICT STRATEGY PLAYBOOK</span>
                    {taStrategy.timeframe && <Badge variant="soft" label={taStrategy.timeframe} />}
                    {taStrategy.smc?.inducement && <Badge variant="soft" color="#8fb3ff" label={`IDM ${taStrategy.smc.inducement.side} ${taStrategy.smc.inducement.price}`} />}
                    <div style={{ flexGrow: 1 }} />
                    {taStrategy.provider && <Text tone="disabled" size="xs" mono>agent: {taStrategy.provider}</Text>}
                  </div>
                  {taStrategy.available === false
                    ? <Text tone="muted" size="xs">Unavailable: {taStrategy.error}</Text>
                    : <div style={{ whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.6, color: "#dccfd3" }}>{String(taStrategy.strategy || "").replace(/^#+\s*/gm, "").replace(/\*\*/g, "")}</div>}
                  <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>Education/research only — not financial advice, never an execution. Same engine as Ask Saathi chat.</Text>
                </div>
              )}

              {!taResult && !taLoading && !taStrategy && !stratLoading && (
                <Text tone="muted" size="sm" style={{ display: "block", marginTop: 12 }}>
                  Pick a market and symbol, then Run analysis or build a Strategy (ICT structure map + potential IDM; 15-minute for crypto). Research only, never a buy/sell call.
                </Text>
              )}
            </div>
          </Panel>

          {/* News + Signals */}
          <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: 16, marginTop: 16 }}>
            <Panel style={{ padding: 0 }}>
              <PanelHead title="Market News" right={<Text tone="disabled" size="xs">research surface</Text>} />
              <MarketNews />
            </Panel>
            <Panel style={{ padding: 0 }}>
              <PanelHead title="Signals" right={<Text tone="disabled" size="xs">watchlist scan</Text>} />
              <TradingSignals />
            </Panel>
          </section>

          {/* Paper Trading Agent (simulation) */}
          <Panel style={{ padding: 0, marginTop: 16 }}>
            <PanelHead title="Paper Trading Agent · simulation" right={<Badge variant="soft" color="#ffab3d" label="SIMULATION ONLY · NO REAL ORDERS" />} />
            <div style={{ padding: 14 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))", gap: 10 }}>
                <StatTile label="Success rate" value={journal?.stats?.win_rate != null ? `${journal.stats.win_rate}%` : "—"} big
                  tone={journal?.stats?.win_rate == null ? "muted" : journal.stats.win_rate >= 50 ? "up" : "down"} />
                <StatTile label="Wins / Losses" value={`${journal?.stats?.won ?? 0} / ${journal?.stats?.lost ?? 0}`} />
                <StatTile label="Open" value={String(journal?.stats?.open ?? 0)} />
                <StatTile label="Total R" value={journal?.stats?.total_r != null ? `${journal.stats.total_r > 0 ? "+" : ""}${journal.stats.total_r}R` : "—"}
                  tone={(journal?.stats?.total_r ?? 0) >= 0 ? "up" : "down"} />
                <StatTile label="Expectancy" value={journal?.stats?.expectancy_r != null ? `${journal.stats.expectancy_r}R` : "—"} />
              </div>

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 12 }}>
                <Button size="sm" onClick={() => runAgent(taMarket, taSymbol)} disabled={paBusy === "run"}>
                  {paBusy === "run" ? "Running…" : `Run agent on ${taMarket} ${taSymbol}`}
                </Button>
                <Button size="sm" variant="secondary" onClick={evaluateTrades} disabled={paBusy === "eval"}>
                  {paBusy === "eval" ? "Evaluating…" : "Evaluate open trades"}
                </Button>
                {paMsg && <Text tone="muted" size="xs">{paMsg}</Text>}
              </div>

              <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>
                The agent opens a dummy trade only when there is a clean ATR trend setup (else it honestly skips),
                then marks it to the live price — win when target hits, loss when stop hits. No broker, no real money.
              </Text>

              {(journal?.trades || []).length > 0 && (
                <div style={{ overflowX: "auto", marginTop: 12 }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr>
                        {["Symbol", "Side", "Entry", "Stop", "Target", "Now/Exit", "R", "Status"].map((h, i) => (
                          <th key={h} style={{ textAlign: i === 0 || i === 1 ? "left" : "right", fontSize: 10, letterSpacing: ".06em", textTransform: "uppercase", color: "#8f8288", fontWeight: 500, padding: "8px 12px", borderBottom: "1px solid rgba(255,64,64,.14)" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {journal.trades.map((t) => {
                        const sc = t.status === "WON" ? "#2ee27a" : t.status === "LOST" ? "#ff4d4d" : "#ffab3d";
                        return (
                          <tr key={t.id}>
                            <td style={{ padding: "8px 12px", fontWeight: 600, borderBottom: "1px solid rgba(255,64,64,.07)" }}>{t.symbol}<span style={{ color: "#8f8288", fontWeight: 400 }}> · {t.market}</span></td>
                            <td style={{ padding: "8px 12px", borderBottom: "1px solid rgba(255,64,64,.07)", color: t.side === "LONG" ? "#2ee27a" : "#ff4d4d" }}>{t.side}</td>
                            <Td>{t.entry}</Td><Td>{t.stop}</Td><Td>{t.target}</Td>
                            <Td>{t.exit_price ?? t.last_price ?? "—"}</Td>
                            <Td>{t.r_multiple != null ? `${t.r_multiple > 0 ? "+" : ""}${t.r_multiple}` : "—"}</Td>
                            <td style={{ padding: "8px 12px", textAlign: "right", borderBottom: "1px solid rgba(255,64,64,.07)" }}>
                              <span style={{ color: sc, fontWeight: 600, fontSize: 12 }}>{t.status}</span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </Panel>

          {/* Holdings */}
          <Panel style={{ padding: 0, marginTop: 16 }}>
            <PanelHead title="My Portfolio · observed" right={<Text tone="disabled" size="xs">{pf.view ? "owner-authenticated browser · read-only" : "not connected"}</Text>} />
            {pf.positions.length === 0 ? (
              <div style={{ padding: 16 }}>
                <EmptyState title="No holdings observed" description={pf.state ? `State: ${pf.state}` : "Enable Saathi Read on an open provider to observe your holdings."} />
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr>
                      {["Symbol", "Qty", "Avg", "LTP", "Value", "Weight"].map((h, i) => (
                        <th key={h} style={{ textAlign: i === 0 ? "left" : "right", fontSize: 11, letterSpacing: ".06em", textTransform: "uppercase", color: "#8f8288", fontWeight: 500, padding: "10px 14px", borderBottom: "1px solid rgba(255,64,64,.14)" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {pf.positions.map((p, i) => {
                      const w = p.mv != null && pf.total ? (p.mv / pf.total) * 100 : null;
                      return (
                        <tr key={i}>
                          <td style={{ padding: "9px 14px", fontWeight: 600, borderBottom: "1px solid rgba(255,64,64,.07)" }}>{p.symbol}</td>
                          <Td>{p.qty ?? "—"}</Td>
                          <Td>{p.avg != null ? p.avg.toFixed(2) : "—"}</Td>
                          <Td>{p.ltp != null ? p.ltp.toFixed(2) : "—"}</Td>
                          <Td>{p.mv != null ? Math.round(p.mv).toLocaleString("en-IN") : "—"}</Td>
                          <Td>{w != null ? `${w.toFixed(0)}%` : "—"}</Td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </>
      )}

      {/* Full chart modal */}
      {fullChart && (
        <div onClick={() => setFullChart(false)}
          style={{ position: "fixed", inset: 0, background: "rgba(4,3,7,0.88)", zIndex: 50, display: "flex",
            alignItems: "center", justifyContent: "center", padding: 24 }}>
          <div onClick={(e) => e.stopPropagation()}
            style={{ width: "min(1200px,96vw)", background: "#0f0b10", border: "1px solid rgba(255,64,64,.25)", borderRadius: 12, padding: 18, boxShadow: "0 30px 80px rgba(0,0,0,.7)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <span style={{ fontWeight: 700, fontSize: 16 }}>{symbol}</span>
              <Badge variant="soft" label={tfRange} />
              {tech.available && <Badge variant="soft" color={tech.trend === "UPTREND" ? "#2ee27a" : tech.trend === "DOWNTREND" ? "#ff4d4d" : "var(--status-neutral)"} label={tech.trend} />}
              {smcOn && <Badge variant="soft" color="#4fb0c6" label="SMC/ICT" />}
              <div style={{ flexGrow: 1 }} />
              <div style={{ display: "flex", gap: 4 }}>
                {["1M", "3M", "6M", "1Y"].map((tf) => (
                  <button key={tf} onClick={() => setTfRange(tf)}
                    style={{ fontFamily: "inherit", fontSize: 12, padding: "5px 11px", borderRadius: 6, cursor: "pointer",
                      border: "1px solid rgba(255,64,64,.2)", background: tf === tfRange ? "#140e15" : "transparent",
                      color: tf === tfRange ? "#ff5757" : "#8f8288", fontWeight: tf === tfRange ? 700 : 400 }}>{tf}</button>
                ))}
                <button onClick={() => setFullChart(false)}
                  style={{ fontFamily: "inherit", fontSize: 12, padding: "5px 12px", borderRadius: 6, cursor: "pointer",
                    border: "1px solid rgba(255,42,42,.4)", background: "transparent", color: "#ff5757" }}>Close ✕</button>
              </div>
            </div>
            {tech.available
              ? <Candles tech={tech} trade={(journal?.trades || []).find((t) => t.symbol === symbol && t.status === "OPEN") || deckDeskTrade} smc={smcOn ? smcData?.smc : null} zones={deckDeskZones} height={520} />
              : <div style={{ padding: 60, textAlign: "center", color: "#8f8288" }}>Chart unavailable for {symbol}.</div>}
          </div>
        </div>
      )}
    </div>
  );
}

// ── small presentational pieces ──────────────────────────────────────────────
function PanelHead({ title, right, expandHref }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderBottom: "1px solid rgba(255,64,64,.12)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className="retro-live ok" aria-hidden="true" style={{ display: "inline-block" }} />
        <span style={{ fontSize: 11, letterSpacing: ".16em", textTransform: "uppercase", color: "#b7a8ad", fontWeight: 600 }}>{title}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {right}
        {expandHref && <Link href={expandHref} title="Open full screen" style={{ color: "#8f8288", fontSize: 13, textDecoration: "none" }}>⤢</Link>}
      </div>
    </div>
  );
}

function Kpi({ label, value, sub, subTone, tone, small }) {
  return (
    <Card style={{ padding: "12px 14px" }}>
      <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: small ? 12 : 18, fontWeight: 700, marginTop: 4, fontVariantNumeric: "tabular-nums", color: tone === "muted" ? "#8f8288" : tone === "warn" ? "#ffab3d" : "#f2e8ea" }}>
        {value}{sub ? <span style={{ fontSize: 12, marginLeft: 6, color: subTone === "up" ? "#2ee27a" : subTone === "down" ? "#ff4d4d" : "#8f8288" }}>{sub}</span> : null}
      </div>
    </Card>
  );
}

function StatTile({ label, value, big, tone }) {
  const col = tone === "up" ? "#2ee27a" : tone === "down" ? "#ff4d4d" : tone === "muted" ? "#8f8288" : "#f2e8ea";
  return (
    <div style={{ background: "#0b0709", border: "1px solid rgba(255,64,64,.12)", borderRadius: 8, padding: "10px 12px" }}>
      <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: big ? 24 : 17, fontWeight: 700, marginTop: 3, color: col, fontVariantNumeric: "tabular-nums" }}>{value}</div>
    </div>
  );
}

function Breadth({ adv, unch, dec }) {
  const a = adv || 0, u = unch || 0, d = dec || 0, t = a + u + d || 1;
  return (
    <div>
      <div style={{ display: "flex", height: 8, borderRadius: 100, overflow: "hidden", border: "1px solid rgba(255,64,64,.14)" }}>
        <div style={{ width: `${(a / t) * 100}%`, background: "#2ee27a" }} />
        <div style={{ width: `${(u / t) * 100}%`, background: "#8f8288" }} />
        <div style={{ width: `${(d / t) * 100}%`, background: "#ff4d4d" }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginTop: 5, color: "#8f8288", fontVariantNumeric: "tabular-nums" }}>
        <span style={{ color: "#2ee27a" }}>{a} adv</span><span>{u} unch</span><span style={{ color: "#ff4d4d" }}>{d} dec</span>
      </div>
    </div>
  );
}

function MoversList({ gainers, losers }) {
  const rows = [
    ...(gainers || []).map((g) => ({ s: g.symbol, v: g.pct, up: true })),
    ...(losers || []).map((g) => ({ s: g.symbol, v: g.pct, up: false })),
  ].filter((r) => r.s);
  if (rows.length === 0) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: 10, letterSpacing: ".1em", color: "#8f8288", marginBottom: 4 }}>TOP MOVERS</div>
      {rows.map((r, i) => (
        <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "4px 0", borderBottom: i < rows.length - 1 ? "1px solid rgba(255,64,64,.07)" : "none", fontVariantNumeric: "tabular-nums" }}>
          <span>{r.s}</span>
          <span style={{ color: r.up ? "#2ee27a" : "#ff4d4d" }}>{r.v != null ? pct(r.v, 1) : "—"}</span>
        </div>
      ))}
    </div>
  );
}

function Meter({ label, value, max, color, caption }) {
  const w = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#b7a8ad", fontVariantNumeric: "tabular-nums" }}>
        <span>{label}</span><span style={{ color }}>{value.toFixed(0)}%</span>
      </div>
      <div style={{ height: 6, borderRadius: 100, background: "#140e15", marginTop: 4, overflow: "hidden" }}>
        <div style={{ width: `${w}%`, height: "100%", background: color }} />
      </div>
      {caption && <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 4 }}>{caption}</Text>}
    </div>
  );
}

function PlanCard({ symbol, tag, text, evidence, muted }) {
  return (
    <div style={{ background: "#0b0709", border: "1px solid rgba(255,64,64,.14)", borderRadius: 9, padding: "11px 12px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>{symbol}</span>
        <Badge variant="soft" color={muted ? "var(--status-neutral)" : "#ffab3d"} label={tag} />
      </div>
      <Text tone="muted" size="xs" style={{ display: "block", marginTop: 5, lineHeight: 1.5 }}>{text}</Text>
      <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 6 }}>evidence: {evidence} · not financial advice</Text>
    </div>
  );
}

function EvRow({ k, v, tone }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "5px 0", borderBottom: "1px solid rgba(255,64,64,.08)", fontVariantNumeric: "tabular-nums" }}>
      <span style={{ color: "#8f8288" }}>{k}</span>
      <span style={{ color: tone === "up" ? "#2ee27a" : tone === "down" ? "#ff4d4d" : "#dccfd3" }}>{v == null ? "—" : String(v)}</span>
    </div>
  );
}

function Td({ children }) {
  return <td style={{ padding: "9px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#dccfd3", borderBottom: "1px solid rgba(255,64,64,.07)" }}>{children}</td>;
}
