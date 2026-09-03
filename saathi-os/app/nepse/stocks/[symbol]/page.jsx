"use client";
// US4 — Stock detail. Three tabs: Overview (fundamentals + dividend history),
// Technical (Pro-gated, per the teardown paywall — no real charting engine here),
// and Brokers (per-stock buy/sell breakdown). Header carries a watchlist star.
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { getStock, brokersForStock } from "@/lib/nepse/data";
import { withAnalytics } from "@/lib/nepse/analytics";
import { fmtRs, fmtNum, fmtPct, dayChangePct, fmtCompactRs } from "@/lib/nepse/format";
import * as store from "@/lib/nepse/store";

function dividends(stock) {
  const seed = stock.symbol.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  return [0, 1, 2].map((i) => {
    const fy = 2081 - i; // Nepali fiscal year (BS)
    const bonus = +(((seed * (i + 2)) % 18)).toFixed(2);
    const cash = +(((seed * (i + 1)) % 12) + 0.5).toFixed(2);
    return { fy: `${fy}/${String(fy + 1).slice(2)}`, bonus, cash };
  });
}

export default function StockDetail() {
  const params = useParams();
  const symbol = String(params?.symbol || "").toUpperCase();
  const base = getStock(symbol);
  const stock = base ? withAnalytics(base) : null;
  const [tab, setTab] = useState("overview");
  const [watched, setWatched] = useState(false);

  useEffect(() => {
    try { setWatched(store.loadState().watchlist.includes(symbol)); } catch { /* noop */ }
  }, [symbol]);

  const brokers = useMemo(() => (stock ? brokersForStock(symbol) : []), [symbol, stock]);
  const divs = useMemo(() => (stock ? dividends(stock) : []), [stock]);

  if (!stock) return <div className="nepse-empty">Unknown symbol “{symbol}”. <a href="/nepse/stocks">Back to screener</a></div>;

  const chg = dayChangePct(stock.ltp, stock.prevClose);
  const toggleStar = () => {
    const st = store.toggleWatch(symbol);
    setWatched(st.watchlist.includes(symbol));
  };

  const OV = [
    ["LTP", fmtRs(stock.ltp)], ["Prev close", fmtRs(stock.prevClose)],
    ["52w high", fmtRs(stock.high52)], ["52w low", fmtRs(stock.low52)],
    ["Market cap", fmtCompactRs(stock.marketCap)], ["Paid-up capital", fmtCompactRs(stock.paidUp * 1e6)],
    ["EPS", fmtRs(stock.eps)], ["P/E", stock.pe ?? "—"],
    ["Book value", fmtRs(stock.bookValue)], ["P/B", stock.pb ?? "—"],
    ["RSI", fmtNum(stock.rsi, 0)], ["Listed shares", `${fmtNum(stock.listedShares, 2)} mn`],
  ];

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">{stock.sector}</div>
        <div className="nepse-row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h1 className="nepse-title">{stock.symbol} · <span style={{ fontSize: "0.6em", color: "var(--text-dim)" }}>{stock.name}</span></h1>
            <div className="nepse-row" style={{ marginTop: 6, gap: "1rem" }}>
              <span className="nepse-stat num">{fmtRs(stock.ltp)}</span>
              <span className={`nepse-badge ${chg >= 0 ? "up" : "down"}`}>{fmtPct(chg)}</span>
              <span className={`nepse-badge ${stock.signal === "Buy" ? "up" : stock.signal === "Sell" ? "down" : "neutral"}`}>Score {stock.score} · {stock.signal}</span>
            </div>
          </div>
          <button className="nepse-btn ghost" onClick={toggleStar} aria-pressed={watched}>
            {watched ? "★ Watching" : "☆ Watch"}
          </button>
        </div>
      </header>

      <div className="nepse-tabs" style={{ marginTop: "1rem" }}>
        {[["overview", "Overview"], ["technical", "Technical"], ["brokers", "Brokers"]].map(([k, l]) => (
          <button key={k} className={`nepse-tab ${tab === k ? "active" : ""}`} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          <div className="nepse-grid-4">
            {OV.map(([l, v]) => (
              <div key={l} className="nepse-card"><span className="tag">{l}</span><div className="nepse-stat num" style={{ fontSize: "1.15rem" }}>{v}</div></div>
            ))}
          </div>
          <h3 style={{ margin: "1.5rem 0 0.75rem" }}>Dividend history</h3>
          <div className="nepse-table-wrap">
            <table className="nepse-table">
              <thead><tr><th>Fiscal year (BS)</th><th className="rt">Bonus %</th><th className="rt">Cash %</th><th className="rt">Total %</th></tr></thead>
              <tbody>{divs.map((d) => (
                <tr key={d.fy}><td className="strong">{d.fy}</td><td className="rt num">{d.bonus}</td><td className="rt num">{d.cash}</td><td className="rt num">{(d.bonus + d.cash).toFixed(2)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}

      {tab === "technical" && (
        <div className="nepse-callout gold">
          <b>Technical Analysis is a Pro feature.</b> The candlestick chart with drawing tools
          (trendlines, Fibonacci, measure), multi-timeframe scale, and automated pattern
          detection sits behind the paid Analysis tier and is out of scope for this snapshot build.
        </div>
      )}

      {tab === "brokers" && (
        <div className="nepse-table-wrap">
          <table className="nepse-table">
            <thead><tr>
              <th>Broker</th><th className="rt">Buy qty</th><th className="rt">Buy amt</th>
              <th className="rt">Sell qty</th><th className="rt">Sell amt</th><th className="rt">Net</th><th className="rt">Trades</th>
            </tr></thead>
            <tbody>{brokers.map((b) => (
              <tr key={b.code}>
                <td className="strong">#{b.code} {b.name}</td>
                <td className="rt num">{fmtNum(b.buyQty, 0)}</td>
                <td className="rt num">{fmtCompactRs(b.buyAmount)}</td>
                <td className="rt num">{fmtNum(b.sellQty, 0)}</td>
                <td className="rt num">{fmtCompactRs(b.sellAmount)}</td>
                <td className={`rt num ${b.net >= 0 ? "nepse-up" : "nepse-down"}`}>{fmtCompactRs(b.net)}</td>
                <td className="rt num">{b.trades}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </>
  );
}
