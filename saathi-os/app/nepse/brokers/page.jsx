"use client";
// US5 — Brokers. Exchange-wide broker ranking: top-3 cards + a sortable, searchable
// table (rank, name/code, buy/sell/total turnover, trade count).
import { useMemo, useState } from "react";
import { BROKERS } from "@/lib/nepse/data";
import { fmtNum, fmtCompactRs } from "@/lib/nepse/format";

export default function BrokersPage() {
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const query = q.trim().toLowerCase();
    if (!query) return BROKERS;
    return BROKERS.filter((b) => b.name.toLowerCase().includes(query) || String(b.code).includes(query));
  }, [q]);
  const top3 = BROKERS.slice(0, 3);

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">Brokers</div>
        <h1 className="nepse-title">Broker ranking</h1>
        <p className="nepse-dek">Every licensed NEPSE broker, ranked by total turnover.</p>
      </header>

      <div className="nepse-grid-3" style={{ marginTop: "1rem" }}>
        {top3.map((b) => (
          <div key={b.code} className="nepse-card">
            <span className="tag">Rank #{b.rank}</span>
            <h3>#{b.code} {b.name}</h3>
            <div className="nepse-stat num" style={{ fontSize: "1.2rem" }}>{fmtCompactRs(b.total)}</div>
          </div>
        ))}
      </div>

      <div className="nepse-row" style={{ margin: "1.25rem 0 1rem" }}>
        <input className="nepse-input" placeholder="Search by name or code (e.g. 58, Naasa)" value={q}
          onChange={(e) => setQ(e.target.value)} style={{ minWidth: 300 }} />
      </div>

      <div className="nepse-table-wrap">
        <table className="nepse-table">
          <thead><tr>
            <th className="rt">Rank</th><th>Broker</th><th className="rt">Buy turnover</th>
            <th className="rt">Sell turnover</th><th className="rt">Total</th><th className="rt">Trades</th>
          </tr></thead>
          <tbody>
            {rows.map((b) => (
              <tr key={b.code}>
                <td className="rt num">{b.rank}</td>
                <td className="strong">#{b.code} {b.name}</td>
                <td className="rt num">{fmtCompactRs(b.buy)}</td>
                <td className="rt num">{fmtCompactRs(b.sell)}</td>
                <td className="rt num">{fmtCompactRs(b.total)}</td>
                <td className="rt num">{fmtNum(b.trades, 0)}</td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={6} className="nepse-empty">No broker matches “{q}”.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}
