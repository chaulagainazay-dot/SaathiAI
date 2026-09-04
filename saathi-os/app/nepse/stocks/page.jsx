"use client";
// US2 — All Stocks screener. Search, sector filter, sortable numeric columns,
// pagination (50/page). AI Score / Signal / Evaluation are the ILLUSTRATIVE
// deterministic composite from lib/nepse/analytics — not advice, not a live model.
import { useMemo, useState } from "react";
import { SECTORS } from "@/lib/nepse/data";
import { useNepseQuotes } from "@/lib/nepse/live";
import { screen } from "@/lib/nepse/screener";
import { fmtNum, fmtRs, fmtPct, dayChangePct } from "@/lib/nepse/format";

const COLS = [
  { key: "symbol", label: "Stock", align: "" },
  { key: "ltp", label: "LTP", align: "rt" },
  { key: "change", label: "% Chg", align: "rt" },
  { key: "score", label: "Score", align: "rt" },
  { key: "signal", label: "Signal", align: "", nosort: true },
  { key: "evaluation", label: "Evaluation", align: "", nosort: true },
  { key: "rsi", label: "RSI", align: "rt" },
  { key: "pe", label: "P/E", align: "rt" },
  { key: "pb", label: "P/B", align: "rt" },
];

export default function ScreenerPage() {
  const [query, setQuery] = useState("");
  const [sector, setSector] = useState("");
  const [sort, setSort] = useState({ key: "score", dir: "desc" });
  const [page, setPage] = useState(1);
  const { stocks, isLive } = useNepseQuotes();

  const result = useMemo(
    () => screen(stocks, { query, sector, sort, page, pageSize: 50 }),
    [stocks, query, sector, sort, page],
  );

  const onSort = (key) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" }));

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">All Stocks</div>
        <h1 className="nepse-title">Screener · {stocks.length} instruments{isLive ? " · live" : ""}</h1>
        <p className="nepse-dek">The data backbone. Score / Signal / Evaluation are an illustrative composite — not investment advice.</p>
      </header>

      <div className="nepse-row" style={{ margin: "1rem 0" }}>
        <input className="nepse-input" placeholder="Search symbol or company" value={query}
          onChange={(e) => { setQuery(e.target.value); setPage(1); }} style={{ minWidth: 260 }} />
        <select className="nepse-select" value={sector} onChange={(e) => { setSector(e.target.value); setPage(1); }}>
          <option value="">All sectors</option>
          {SECTORS.map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>

      <div className="nepse-table-wrap">
        <table className="nepse-table" data-testid="screener-table">
          <thead><tr>
            {COLS.map((c) => (
              <th key={c.key} className={c.align} onClick={() => !c.nosort && onSort(c.key)}
                style={{ cursor: c.nosort ? "default" : "pointer" }}>
                {c.label}{sort.key === c.key ? (sort.dir === "asc" ? " ▲" : " ▼") : ""}
              </th>
            ))}
          </tr></thead>
          <tbody>
            {result.rows.map((r) => {
              const noChange = r.changeUnavailable || r.prevClose == null;
              const chg = noChange ? null : dayChangePct(r.ltp, r.prevClose);
              return (
                <tr key={r.symbol}>
                  <td className="strong"><a href={`/nepse/stocks/${r.symbol}`}>{r.symbol}</a>
                    <div style={{ color: "var(--text-faint)", fontSize: "0.72rem", fontWeight: 400 }}>{r.sector}</div></td>
                  <td className="rt num">{fmtRs(r.ltp)}</td>
                  <td className={`rt num ${noChange ? "" : chg >= 0 ? "nepse-up" : "nepse-down"}`}
                      title={noChange ? "Feed does not report a previous close" : undefined}>
                    {noChange ? "—" : fmtPct(chg)}
                  </td>
                  <td className="rt num">{r.score}</td>
                  <td><span className={`nepse-badge ${r.signal === "Buy" ? "up" : r.signal === "Sell" ? "down" : "neutral"}`}>{r.signal}</span></td>
                  <td>{r.evaluation}</td>
                  <td className="rt num">{fmtNum(r.rsi, 0)}</td>
                  <td className="rt num">{r.pe ?? "—"}</td>
                  <td className="rt num">{r.pb ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="nepse-pagination">
        <button className="nepse-btn ghost" disabled={result.page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</button>
        <span>Page {result.page} / {result.pages} · {result.total} rows</span>
        <button className="nepse-btn ghost" disabled={result.page >= result.pages} onClick={() => setPage((p) => p + 1)}>Next</button>
      </div>
    </>
  );
}
