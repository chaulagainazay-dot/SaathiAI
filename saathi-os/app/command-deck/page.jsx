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
import FinancialViewport from "@/components/finance/FinancialViewport";

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
  const [providers, setProviders] = useState(null);
  const [runtimes, setRuntimes] = useState([]);
  const [portfolio, setPortfolio] = useState(null);
  const [booting, setBooting] = useState(true);

  const loadNepse = useCallback(async () => {
    const r = await api("/api/v1/market/nepse/live/full");
    if (r.ok) { setNepse(r.body); setNepseErr(""); }
    else setNepseErr(r.body?.error || `HTTP ${r.status}`);
  }, []);

  const loadChart = useCallback(async (sym) => {
    setChartLoading(true);
    const r = await api(`/api/v1/market/tracker/chart?symbol=${encodeURIComponent(sym)}&range=3M`);
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
      await Promise.all([loadNepse(), loadChart(symbol), loadFinance()]);
      setBooting(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const id = setInterval(loadNepse, NEPSE_POLL_MS);
    return () => clearInterval(id);
  }, [loadNepse]);

  useEffect(() => { loadChart(symbol); }, [symbol, loadChart]);

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
    return { pts: win, s20: s20.slice(-48), s50: s50.slice(-48), closes, last, day, rsi, trend, l20, l50, available: true };
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
  const guardian = useMemo(() => {
    const caps = providers || {};
    // capability_matrix keys per provider carry agent_actions etc.
    const anyActions = Object.entries(caps)
      .filter(([k]) => !["policies"].includes(k))
      .map(([, v]) => (v && typeof v === "object" ? String(v.agent_actions || "") : ""))
      .filter(Boolean);
    const allBlocked = anyActions.length > 0 && anyActions.every((a) => /PROHIBIT|UNSUPPORT|NONE/i.test(a));
    return { allBlocked, sample: anyActions[0] || "PROHIBITED" };
  }, [providers]);

  const openRuntime = runtimes.find((r) => r.runtime_state === "OPEN_OWNER_CONTROL");
  const readableRuntime = runtimes.find((r) => r.agent_read && r.runtime_state !== "CLOSED");

  const idx = numOr(nepse?.index ?? nepse?.nepse_index ?? nepse?.value);
  const idxChg = numOr(nepse?.change ?? nepse?.point_change);
  const idxPct = numOr(nepse?.percent_change ?? nepse?.change_percent);
  const adv = numOr(nepse?.advances ?? nepse?.advancers);
  const dec = numOr(nepse?.declines ?? nepse?.decliners);
  const unch = numOr(nepse?.unchanged);
  const movers = nepse?.top_gainers || nepse?.gainers || [];
  const losers = nepse?.top_losers || nepse?.losers || [];
  const marketState = nepse?.market_state || nepse?.state || nepse?.status;

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
                <PanelHead title="Financial Browser" right={<StatusBadge status="success" label="EMBEDDED" />} />
                <div style={{ padding: 14 }}>
                  {openRuntime ? (
                    <FinancialViewport provider={openRuntime.provider} runtimeId={openRuntime.runtime_id} />
                  ) : (
                    <EmptyState
                      title="No embedded browser open"
                      description="Open a provider to load its site inside SaathiOS — no external Chrome. You log in yourself."
                      action={<Link href="/finance/browser"><Button size="sm">Open Financial Browser</Button></Link>}
                    />
                  )}
                  {readableRuntime && (
                    <div style={{ marginTop: 10 }}>
                      <StatusBadge status="success" label="SAATHI READ · ON" />
                      <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 4 }}>
                        Owner-visual only — pixels never sent to any model.
                      </Text>
                    </div>
                  )}
                </div>
              </Panel>

              {/* NEPSE Tracker */}
              <Panel style={{ padding: 0 }}>
                <PanelHead title="NEPSE Tracker" right={<Text tone="disabled" size="xs" mono>{nepse?.source_badge ? "observed" : "live"}</Text>} />
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
                  right={
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {CHART_SYMBOLS.map((s) => (
                        <button key={s} onClick={() => setSymbol(s)}
                          style={{ fontFamily: "inherit", fontSize: 11, padding: "3px 8px", borderRadius: 100, cursor: "pointer",
                            border: "1px solid rgba(255,64,64,.25)",
                            background: s === symbol ? "#ff2a2a" : "transparent",
                            color: s === symbol ? "#08060a" : "#b7a8ad", fontWeight: s === symbol ? 700 : 400 }}>
                          {s}
                        </button>
                      ))}
                    </div>
                  }
                />
                <div style={{ padding: 14 }}>
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
                      <Candles tech={tech} />
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
                        <Badge variant="soft" label={`Trend ${tech.trend}`} color={tech.trend === "UPTREND" ? "#2ee27a" : tech.trend === "DOWNTREND" ? "#ff4d4d" : "var(--status-neutral)"} />
                        {tech.rsi != null && <Badge variant="soft" label={`RSI ${tech.rsi.toFixed(0)}`} color={tech.rsi > 70 ? "#ff4d4d" : tech.rsi < 30 ? "#2ee27a" : "#ffab3d"} />}
                        {tech.l20 != null && <Badge variant="soft" label={`MA20 ${tech.l20.toFixed(1)}`} />}
                        {tech.l50 != null && <Badge variant="soft" label={`MA50 ${tech.l50.toFixed(1)}`} />}
                      </div>
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
                <PanelHead title="Trading Guardian" right={<StatusBadge status="danger" label="OBSERVATION-ONLY" />} />
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
    </div>
  );
}

// ── small presentational pieces ──────────────────────────────────────────────
function PanelHead({ title, right }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderBottom: "1px solid rgba(255,64,64,.12)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className="retro-live ok" aria-hidden="true" style={{ display: "inline-block" }} />
        <span style={{ fontSize: 11, letterSpacing: ".16em", textTransform: "uppercase", color: "#b7a8ad", fontWeight: 600 }}>{title}</span>
      </div>
      {right}
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
    ...(gainers || []).slice(0, 3).map((g) => ({ s: g.symbol || g.ticker, v: numOr(g.percent_change ?? g.change_percent ?? g.pct), up: true })),
    ...(losers || []).slice(0, 2).map((g) => ({ s: g.symbol || g.ticker, v: numOr(g.percent_change ?? g.change_percent ?? g.pct), up: false })),
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

function Candles({ tech }) {
  const pts = tech.pts;
  const W = 560, H = 200, pad = 8;
  const highs = pts.map((p) => p.h ?? p.c), lows = pts.map((p) => p.l ?? p.c);
  const hi = Math.max(...highs), lo = Math.min(...lows);
  const span = hi - lo || 1;
  const y = (v) => pad + (hi - v) / span * (H - pad * 2);
  const n = pts.length;
  const slot = W / n;
  const bw = Math.max(2, slot * 0.6);
  const linePts = (arr) => arr.map((v, i) => v == null ? null : `${(i * slot + slot / 2).toFixed(1)},${y(v).toFixed(1)}`).filter(Boolean).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="200" preserveAspectRatio="none" style={{ display: "block", background: "#0b0709", borderRadius: 8, border: "1px solid rgba(255,64,64,.1)" }}>
      {[0.25, 0.5, 0.75].map((g) => (
        <line key={g} x1="0" y1={pad + g * (H - pad * 2)} x2={W} y2={pad + g * (H - pad * 2)} stroke="rgba(255,64,64,.07)" strokeWidth="1" />
      ))}
      {pts.map((p, i) => {
        const x = i * slot + slot / 2;
        const up = (p.c ?? 0) >= (p.o ?? p.c ?? 0);
        const col = up ? "#2ee27a" : "#ff4d4d";
        const yo = y(p.o ?? p.c), yc = y(p.c);
        const top = Math.min(yo, yc), h = Math.max(1.5, Math.abs(yc - yo));
        return (
          <g key={i}>
            <line x1={x} y1={y(p.h ?? p.c)} x2={x} y2={y(p.l ?? p.c)} stroke={col} strokeWidth="1" />
            <rect x={x - bw / 2} y={top} width={bw} height={h} fill={col} />
          </g>
        );
      })}
      {tech.s50 && <polyline fill="none" stroke="#4fb0c6" strokeWidth="1.2" opacity="0.7" points={linePts(tech.s50)} />}
      {tech.s20 && <polyline fill="none" stroke="#ffab3d" strokeWidth="1.2" opacity="0.85" points={linePts(tech.s20)} />}
    </svg>
  );
}

function Td({ children }) {
  return <td style={{ padding: "9px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "#dccfd3", borderBottom: "1px solid rgba(255,64,64,.07)" }}>{children}</td>;
}
