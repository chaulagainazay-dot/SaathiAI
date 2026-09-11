"use client";
// US5 — Watchlist. Portfolio-independent tracking list with the same live-style columns
// as the screener (score / signal / RSI), add-by-symbol, and a simple remove.
import { useEffect, useMemo, useState } from "react";
import { STOCKS } from "@/lib/nepse/data";
import { useNepseQuotes } from "@/lib/nepse/live";
import { useNepseIndicators, liveDayChange } from "@/lib/nepse/use-indicators";
import { withAnalytics } from "@/lib/nepse/analytics";
import { fmtRs, fmtNum, fmtPct, dayChangePct } from "@/lib/nepse/format";
import * as store from "@/lib/nepse/store";

const SYMBOLS = STOCKS.map((s) => s.symbol);

export default function WatchlistPage() {
  const [state, setState] = useState(null);
  const [pick, setPick] = useState("NABIL");
  const { stocks, isLive } = useNepseQuotes();
  const { indicators } = useNepseIndicators();
  useEffect(() => { setState(store.loadState()); }, []);

  // Resolve watched symbols against the live-merged set, so the watchlist and the
  // screener can never disagree about a price.
  const rows = useMemo(() => {
    if (!state) return [];
    const bySymbol = new Map(stocks.map((s) => [s.symbol, s]));
    return state.watchlist
      .map((sym) => bySymbol.get(String(sym).toUpperCase()))
      .filter(Boolean)
      .map(withAnalytics);
  }, [state, stocks]);

  if (!state) return <div className="nepse-empty">Loading…</div>;

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">Watchlist</div>
        <h1 className="nepse-title">Stocks you’re watching{isLive ? " · live" : ""}</h1>
        <p className="nepse-dek">Independent of any portfolio — for what you track, not necessarily hold.</p>
      </header>

      <div className="nepse-row" style={{ margin: "1rem 0" }}>
        <select className="nepse-select" value={pick} onChange={(e) => setPick(e.target.value)}>
          {SYMBOLS.map((s) => <option key={s}>{s}</option>)}
        </select>
        <button className="nepse-btn" onClick={() => setState(store.toggleWatch(pick))}>
          {state.watchlist.includes(pick) ? "Remove" : "Add symbol"}
        </button>
      </div>

      <div className="nepse-table-wrap">
        <table className="nepse-table">
          <thead><tr>
            <th>Symbol</th><th className="rt">LTP</th><th className="rt">% Chg</th>
            <th className="rt">Score</th><th>Signal</th><th className="rt">RSI</th><th></th>
          </tr></thead>
          <tbody>
            {rows.map((r) => {
              // Same derivation as the screener — the two must never disagree.
              const dc = liveDayChange(r.ltp, indicators[r.symbol], isLive);
              const noChange = !dc.available;
              const chg = dc.changePct;
              return (
                <tr key={r.symbol}>
                  <td className="strong"><a href={`/nepse/stocks/${r.symbol}`}>{r.symbol}</a></td>
                  <td className="rt num">{fmtRs(r.ltp)}</td>
                  <td className={`rt num ${noChange ? "" : chg >= 0 ? "nepse-up" : "nepse-down"}`}
                      title={noChange ? "No trustworthy previous close available" : `vs close of ${dc.against}`}>
                    {noChange ? "—" : fmtPct(chg)}
                  </td>
                  <td className="rt num">{r.score}</td>
                  <td><span className={`nepse-badge ${r.signal === "Buy" ? "up" : r.signal === "Sell" ? "down" : "neutral"}`}>{r.signal}</span></td>
                  <td className="rt num">{fmtNum(r.rsi, 0)}</td>
                  <td className="rt"><button className="nepse-btn ghost" onClick={() => setState(store.toggleWatch(r.symbol))}>Remove</button></td>
                </tr>
              );
            })}
            {!rows.length && <tr><td colSpan={7} className="nepse-empty">Nothing on your watchlist yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}
