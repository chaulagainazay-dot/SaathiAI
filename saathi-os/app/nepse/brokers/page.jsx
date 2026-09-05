"use client";
// US5 — Brokers. Ranked by what they actually traded in the last completed session.
//
// This page used to rank a hardcoded list of eight brokers by hardcoded turnover
// figures, under a heading claiming "every licensed NEPSE broker". It now counts
// the exchange floorsheet: every trade of the session, both sides, per broker.
// Where a code has no name in this build it stays a code — a broker is not given
// a name that might belong to another firm.

import { useMemo, useState } from "react";
import { fmtNum, fmtCompactRs } from "@/lib/nepse/format";
import { useFloorsheet } from "@/lib/nepse/use-market";

export default function BrokersPage() {
  const [q, setQ] = useState("");
  const { loading, data, error } = useFloorsheet();

  const rows = useMemo(() => {
    const all = data?.brokers || [];
    const query = q.trim().toLowerCase();
    if (!query) return all;
    return all.filter((b) => (b.name || "").toLowerCase().includes(query) || String(b.code).includes(query));
  }, [data, q]);

  const head = (
    <header className="nepse-head">
      <div className="nepse-eyebrow">Brokers</div>
      <h1 className="nepse-title">Broker ranking</h1>
      <p className="nepse-dek">
        {data
          ? `Counted from the ${data.asOf} floorsheet — ${fmtNum(data.totals.trades, 0)} trades across ${data.totals.symbols} symbols.`
          : "Ranked by what each broker actually traded in the last completed session."}
      </p>
    </header>
  );

  if (loading) {
    return <>{head}<div className="nepse-empty" style={{ marginTop: "1rem" }}>Counting the session floorsheet…</div></>;
  }
  if (error || !data) {
    return (
      <>{head}
        <div className="nepse-callout" style={{ marginTop: "1rem" }}>
          <strong>No floorsheet.</strong> Broker activity could not be read ({error}).
          Nothing is shown rather than a generated ranking.
        </div>
      </>
    );
  }

  const top3 = data.brokers.slice(0, 3);

  return (
    <>
      {head}

      <div className="nepse-grid-3" style={{ marginTop: "1rem" }}>
        {top3.map((b) => (
          <div key={b.code} className="nepse-card">
            <span className="tag">Rank #{b.rank}</span>
            <h3>#{b.code} {b.name || <span style={{ color: "var(--text-faint)" }}>name unknown</span>}</h3>
            <div className="nepse-stat num" style={{ fontSize: "1.2rem" }}>{fmtCompactRs(b.total)}</div>
            <div style={{ color: "var(--text-faint)", fontSize: "0.78rem" }}>
              {fmtNum(b.trades, 0)} trades · net {fmtCompactRs(b.net)}
            </div>
          </div>
        ))}
      </div>

      <div className="nepse-row" style={{ margin: "1.25rem 0 1rem" }}>
        <input className="nepse-input" placeholder="Search by name or code (e.g. 58, Naasa)" value={q}
          onChange={(e) => setQ(e.target.value)} style={{ minWidth: 300 }} />
      </div>

      <div className="nepse-table-wrap">
        <table className="nepse-table">
          <thead>
            <tr><th>#</th><th>Broker</th><th>Bought</th><th>Sold</th><th>Total</th><th>Net</th><th>Trades</th></tr>
          </thead>
          <tbody>
            {rows.map((b) => (
              <tr key={b.code}>
                <td className="num">{b.rank}</td>
                <td className="strong">
                  #{b.code}{" "}
                  {b.name || <span style={{ color: "var(--text-faint)", fontWeight: 400 }}>name unknown</span>}
                </td>
                <td className="num">{fmtCompactRs(b.buyAmount)}</td>
                <td className="num">{fmtCompactRs(b.sellAmount)}</td>
                <td className="num">{fmtCompactRs(b.total)}</td>
                <td className={`num ${b.net >= 0 ? "nepse-up" : "nepse-down"}`}>{fmtCompactRs(b.net)}</td>
                <td className="num">{fmtNum(b.trades, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p style={{ color: "var(--text-faint)", fontSize: "0.78rem", marginTop: "1rem" }}>
        Top {data.brokers.length} brokers of the session. This build can name{" "}
        {data.namedBrokers} broker codes; the rest are shown by code rather than
        guessed. Session turnover counted here is {fmtCompactRs(data.totals.amount)} across{" "}
        {fmtNum(data.totals.quantity, 0)} shares. Source: {data.source} · {data.license} ·{" "}
        {data.classification}.
      </p>
    </>
  );
}
