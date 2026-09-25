"use client";
// Compare — several instruments on one rebased axis, plus a fundamentals matrix.
//
// The chart plots PERCENTAGE CHANGE FROM THE PERIOD START, never price. Two
// stocks at Rs 4,000 and Rs 200 on a shared price axis tell you which is more
// expensive, which nobody asked. Rebasing turns the picture into the question
// actually being asked: which one performed better.

import { useEffect, useMemo, useState } from "react";
import { STOCKS } from "@/lib/nepse/data";
import {
  COMPARE_FIELDS, MAX_COMPARE, canAdd, compareMatrix, compareSeries,
} from "@/lib/nepse/compare";
import { fmtCompactRs, fmtNum, fmtPct } from "@/lib/nepse/format";

// The history route ships the most recent 400 sessions, so anything longer than a
// year would be drawn from a window it does not carry. Offering "5Y" over 400 bars
// would label ~18 months as five years.
const PERIOD_OPTIONS = ["1W", "1M", "3M", "6M", "1Y"];
const MAX_SESSIONS_AVAILABLE = 400;

const LINE = ["#1f8a53", "#b83f34", "#9a6d1f", "#2f6fb8", "#7b4fa8", "#0f8f8f", "#c2557a", "#5a6b3a"];
const START = ["NABIL", "NICA"];
/** Fields large enough that the Nepali Arba/Kharba scale is the readable form. */
const MONEY_SCALE = new Set(["marketCap", "paidUpCapital"]);

function useSeries(symbols) {
  const [bars, setBars] = useState({});
  const [failed, setFailed] = useState({});
  useEffect(() => {
    const ac = new AbortController();
    const missing = symbols.filter((s) => !(s in bars) && !(s in failed));
    if (!missing.length) return () => ac.abort();
    Promise.all(missing.map((sym) =>
      fetch(`/api/nepse/history?symbol=${encodeURIComponent(sym)}`, { signal: ac.signal, cache: "no-store" })
        .then((r) => r.json())
        .then((d) => [sym, Array.isArray(d?.bars) && d.bars.length ? d.bars : null, d?.reason || "NO_BARS"])
        .catch(() => [sym, null, "UNREACHABLE"]),
    )).then((rows) => {
      const okRows = {};
      const badRows = {};
      for (const [sym, b, reason] of rows) {
        if (b) okRows[sym] = b; else badRows[sym] = reason;
      }
      if (Object.keys(okRows).length) setBars((p) => ({ ...p, ...okRows }));
      if (Object.keys(badRows).length) setFailed((p) => ({ ...p, ...badRows }));
    }).catch(() => {});
    return () => ac.abort();
  }, [symbols, bars, failed]);
  return { bars, failed };
}

function Chart({ series, colours }) {
  const W = 900; const H = 300; const PAD = 34;
  if (!series.length) return null;
  const all = series.flatMap((s) => s.points.map((p) => p.pct));
  const min = Math.min(0, ...all);
  const max = Math.max(0, ...all);
  const span = max - min || 1;
  const len = Math.max(...series.map((s) => s.points.length));
  const x = (i, n) => PAD + (n <= 1 ? 0 : (i / (n - 1)) * (W - PAD * 2));
  const y = (v) => PAD / 2 + (1 - (v - min) / span) * (H - PAD);
  const zeroY = y(0);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
         aria-label={`Rebased return, ${series.map((s) => s.symbol).join(" versus ")}`}>
      <line x1={PAD} y1={zeroY} x2={W - PAD} y2={zeroY} stroke="var(--border)" strokeDasharray="3 3" />
      <text x={4} y={zeroY - 3} fontSize="10" fill="var(--text-faint)"
            fontFamily="'IBM Plex Mono', monospace">0%</text>
      <text x={4} y={y(max) + 9} fontSize="10" fill="var(--text-faint)"
            fontFamily="'IBM Plex Mono', monospace">{fmtPct(max)}</text>
      <text x={4} y={y(min) - 2} fontSize="10" fill="var(--text-faint)"
            fontFamily="'IBM Plex Mono', monospace">{fmtPct(min)}</text>
      {series.map((s) => {
        // Each series is drawn across its OWN length. A shorter history is a
        // shorter line, not a stretched one pretending to span the same window.
        const n = s.points.length;
        const d = s.points.map((p, i) =>
          `${i ? "L" : "M"}${x(i, n).toFixed(1)},${y(p.pct).toFixed(1)}`).join(" ");
        return <path key={s.symbol} d={d} fill="none" stroke={colours[s.symbol]} strokeWidth="1.8" />;
      })}
      {len < MAX_SESSIONS_AVAILABLE ? null : null}
    </svg>
  );
}

export default function ComparePage() {
  const [symbols, setSymbols] = useState(START);
  const [period, setPeriod] = useState("1Y");
  const [pick, setPick] = useState("SCB");
  const [msg, setMsg] = useState("");
  const { bars, failed } = useSeries(symbols);

  const entries = useMemo(
    () => symbols.filter((s) => bars[s]).map((s) => ({ symbol: s, bars: bars[s] })),
    [symbols, bars],
  );
  const built = useMemo(() => compareSeries(entries, { period }), [entries, period]);
  const colours = useMemo(
    () => Object.fromEntries(symbols.map((s, i) => [s, LINE[i % LINE.length]])),
    [symbols],
  );
  const stocks = useMemo(
    () => symbols.map((s) => STOCKS.find((x) => x.symbol === s) || { symbol: s }),
    [symbols],
  );
  const matrix = useMemo(
    () => compareMatrix(stocks, { series: built.series }), [stocks, built.series],
  );

  const add = () => {
    const check = canAdd(symbols, pick);
    if (!check.ok) {
      setMsg(check.reason === "LIMIT_REACHED"
        ? `A comparison stops being readable past ${MAX_COMPARE} lines.`
        : check.reason === "ALREADY_ADDED" ? `${pick} is already in the comparison.` : "Pick a symbol.");
      return;
    }
    setMsg("");
    setSymbols([...symbols, check.symbol]);
  };

  const pending = symbols.filter((s) => !bars[s] && !failed[s]);

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">Compare</div>
        <h1 className="nepse-title">Side by side, rebased</h1>
        <p className="nepse-dek">
          Each line starts at 0% on the first session of the period, so what you
          are reading is performance rather than price.
        </p>
      </header>

      <div className="nepse-row" style={{ margin: "1rem 0", flexWrap: "wrap" }}>
        <select className="nepse-select" aria-label="Add a symbol" value={pick}
                onChange={(e) => setPick(e.target.value)}>
          {STOCKS.map((s) => <option key={s.symbol} value={s.symbol}>{s.symbol} — {s.name}</option>)}
        </select>
        <button className="nepse-btn" type="button" onClick={add}>Add</button>
        <select className="nepse-select" aria-label="Period" value={period}
                onChange={(e) => setPeriod(e.target.value)}>
          {PERIOD_OPTIONS.map((p) => <option key={p}>{p}</option>)}
        </select>
        {symbols.map((s) => (
          <button key={s} type="button" className="nepse-btn ghost"
                  onClick={() => setSymbols(symbols.filter((x) => x !== s))}
                  style={{ borderColor: colours[s], color: colours[s] }}>
            {s} ×
          </button>
        ))}
      </div>
      {msg && <p style={{ color: "var(--gold)", fontSize: "0.82rem" }}>{msg}</p>}

      <div className="nepse-card">
        {pending.length > 0 && <div className="nepse-empty">Reading {pending.join(", ")}…</div>}
        {built.series.length > 0
          ? <Chart series={built.series} colours={colours} />
          : pending.length === 0 && <div className="nepse-empty">Nothing to plot yet.</div>}

        <div className="nepse-row" style={{ gap: "1rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
          {built.series.map((s) => (
            <span key={s.symbol} style={{ fontSize: "0.82rem" }}>
              <i style={{ display: "inline-block", width: 18, height: 3, background: colours[s.symbol],
                          verticalAlign: "middle", marginRight: 6 }} />
              <span className="mono">{s.symbol}</span>{" "}
              <span className={s.returnPct >= 0 ? "nepse-up" : "nepse-down"}>{fmtPct(s.returnPct)}</span>
            </span>
          ))}
        </div>

        <p style={{ fontSize: "0.75rem", color: "var(--text-faint)", marginTop: "0.6rem" }}>
          {built.plotted} of {built.requested} plotted over {period}. The browser
          receives the most recent {MAX_SESSIONS_AVAILABLE} sessions, which is why
          nothing longer than a year is offered — a longer label over a shorter
          window would be a lie about the axis.
        </p>

        {built.excluded.length > 0 && (
          <p style={{ fontSize: "0.78rem", color: "var(--gold)", marginTop: "0.4rem" }}>
            Not plotted: {built.excluded.map((e) => `${e.symbol} (${e.reason})`).join(", ")}.
            A series with no usable base cannot be rebased, and a divide-by-zero
            spike drawn as a line is worse than an absent one.
          </p>
        )}
        {Object.keys(failed).length > 0 && (
          <p style={{ fontSize: "0.78rem", color: "var(--down)", marginTop: "0.4rem" }}>
            No history for {Object.entries(failed).map(([s, r]) => `${s} (${r})`).join(", ")}.
          </p>
        )}
      </div>

      <h2 style={{ margin: "1.5rem 0 0.5rem", fontSize: "1.1rem" }}>Fundamentals</h2>
      <div className="nepse-table-wrap">
        <table className="nepse-table">
          <thead>
            <tr>
              <th>Field</th>
              {matrix.symbols.map((s) => <th key={s} className="rt">{s}</th>)}
            </tr>
          </thead>
          <tbody>
            {matrix.rows.map((row) => (
              <tr key={row.key}>
                <td className="strong">{row.label}</td>
                {row.values.map((v, i) => (
                  <td key={i} className="rt num">
                    {/* A missing fundamental is an em dash. Substituting zero would
                        sort a company with no published P/E to the top of "cheapest". */}
                    {v === null ? "—"
                      : typeof v !== "number" ? String(v)
                      : row.key.endsWith("Pct") ? fmtPct(v)
                      // A market cap printed in full is fourteen digits of
                      // Rs 2,23,18,08,00,000, which nobody reads as a number.
                      : MONEY_SCALE.has(row.key) ? fmtCompactRs(v)
                      : fmtNum(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ fontSize: "0.75rem", color: "var(--text-faint)", marginTop: "0.6rem" }}>
        Fundamentals come from this build&apos;s curated list ({COMPARE_FIELDS.length} fields);
        a symbol outside it shows dashes rather than borrowed numbers.
      </p>
    </>
  );
}
