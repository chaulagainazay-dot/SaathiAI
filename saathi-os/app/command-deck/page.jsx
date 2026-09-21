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
import CommandOverview from "@/components/finance/CommandOverview";
import StockScreener from "@/components/finance/StockScreener";
import BrokerDesk from "@/components/finance/BrokerDesk";
import CompanyCard from "@/components/finance/CompanyCard";
import PriceAlerts from "@/components/finance/PriceAlerts";

const CHART_SYMBOLS = ["NABIL", "HDL", "UPPER", "GBIME", "NRIC"];
const NEPSE_POLL_MS = 30000;

const DECK_TILES = [
  { icon: "▤", label: "Portfolio", desc: "Add · track · analyse · recommend · research", href: "/command-deck/portfolio" },
  { icon: "◈", label: "Chart Analysis", desc: "Candles · ICT/SMC · volume · full workspace", href: "/command-deck/chart" },
  { icon: "◧", label: "Financial Browser", desc: "Embedded provider browser · read-only", href: "/command-deck/browser" },
  { icon: "🛡", label: "Trading Guardian", desc: "No trade authority · paper agent", href: "/command-deck/guardian" },
  { icon: "▦", label: "Stock Screener", desc: "Full market · fundamental + technical", href: "/command-deck/screener" },
  { icon: "◨", label: "Broker Analysis", desc: "Accumulation vs distribution · floorsheet", href: "/command-deck/brokers" },
  { icon: "◮", label: "Trade Desk", desc: "Setup · volume strength · S/R zones", href: "/command-deck/trade-desk" },
  { icon: "◪", label: "NEPSE Tracker", desc: "Index · breadth · movers (live)", href: "/command-deck/nepse" },
  { icon: "✦", label: "AI Analysis", desc: "TA desk + ICT/IDM strategy", href: "/command-deck/ai" },
  { icon: "▣", label: "Company Financials", desc: "EPS · P/E · P/B · 52W · any symbol", href: "/command-deck/company" },
  { icon: "◔", label: "Price Alerts", desc: "Target crosses · on this device", href: "/command-deck/alerts" },
  { icon: "▤", label: "News", desc: "Market research surface", href: "/command-deck/news" },
  { icon: "◎", label: "Signals", desc: "Watchlist setup scan", href: "/command-deck/signals" },
  { icon: "👁", label: "Screen Analysis", desc: "Saathi looks at your screen (vision)", href: "/command-deck/vision" },
];

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
  // Free-source movers (no API key); fall back to deriving from the licensed snapshot.
  const [freeMovers, setFreeMovers] = useState(null);
  useEffect(() => {
    let alive = true;
    const run = async () => { const r = await api("/api/v1/market/free/movers?top=4"); if (alive && r.ok && r.body?.available) setFreeMovers(r.body); };
    run(); const id = setInterval(run, 60000); return () => { alive = false; clearInterval(id); };
  }, []);
  const { movers, losers } = useMemo(() => {
    if (freeMovers?.available) {
      const map = (arr) => (arr || []).map((s) => ({ symbol: s.symbol, pct: numOr(s.percent_change) })).filter((s) => s.symbol && s.pct != null);
      return { movers: map(freeMovers.gainers).slice(0, 3), losers: map(freeMovers.losers).slice(0, 2) };
    }
    const secs = (nepse?.securities || [])
      .map((s) => ({ symbol: s.symbol, pct: numOr(s.percent_change) }))
      .filter((s) => s.symbol && s.pct != null);
    const byPct = [...secs].sort((a, b) => b.pct - a.pct);
    return { movers: byPct.slice(0, 3), losers: byPct.slice(-2).reverse() };
  }, [nepse, freeMovers]);

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
          {/* Function launcher — clean boxes, one per tool */}
          <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12, marginTop: 20 }}>
            {DECK_TILES.map((t) => <DeckTile key={t.label} {...t} />)}
          </section>

          {/* KPI row */}
          <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", gap: 12, marginTop: 16 }}>
            <Kpi label="Portfolio value" value={pf.total != null ? fmtNpr(pf.total) : "Awaiting read"} tone={pf.total != null ? "" : "muted"} />
            <Kpi label="Positions" value={pf.positions.length ? String(pf.positions.length) : "—"} />
            <Kpi label="Top concentration" value={pf.conc != null ? `${pf.conc.toFixed(0)}%` : "—"} tone={pf.conc > 35 ? "warn" : ""} />
            <Kpi label="NEPSE index" value={idx != null ? idx.toLocaleString("en-IN") : "—"} sub={idxPct != null ? pct(idxPct) : ""} subTone={idxPct >= 0 ? "up" : "down"} />
            <Kpi label={`${symbol} last`} value={tech.last != null ? tech.last.toFixed(2) : "—"} sub={tech.day != null ? pct(tech.day) : ""} subTone={tech.day >= 0 ? "up" : "down"} />
            <Kpi label="AI agents" value="Research · TA · Risk · Plan" small />
          </section>

          {/* Unified overview — all modules at a glance */}
          <CommandOverview />

        </>
      )}

    </div>
  );
}

// ── small presentational pieces ──────────────────────────────────────────────
function DeckTile({ icon, label, desc, href }) {
  const inner = (
    <div className="deck-tile" style={{ position: "relative", background: "#0f0b10", border: "1px solid rgba(255,64,64,.18)", borderRadius: 12, padding: "16px 14px", overflow: "hidden", height: "100%", boxShadow: "inset 0 0 40px rgba(255,42,42,.03)" }}>
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 2, background: "linear-gradient(90deg,transparent,rgba(255,42,42,.6),transparent)" }} />
      <div style={{ fontSize: 22, marginBottom: 8 }}>{icon}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: "#f2e8ea" }}>{label}</div>
      <div style={{ fontSize: 11, color: "#8f8288", marginTop: 4, lineHeight: 1.4 }}>{desc}</div>
      <div style={{ fontSize: 11, color: "#ff5757", marginTop: 8, fontWeight: 600 }}>open →</div>
    </div>
  );
  const style = { textDecoration: "none", display: "block", height: "100%" };
  return href.startsWith("/")
    ? <Link href={href} style={style}>{inner}</Link>
    : <a href={href} style={style}>{inner}</a>;
}

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
