"use client";
// US3 — Market. Exchange-wide state computed from the daily archive.
//
// What changed and why: this page used to render a HARDCODED index (2557.31), a
// hardcoded turnover figure, and an index "history" that was a sine wave. Every
// number here is now derived from the archive's last completed session across the
// whole listed universe — and the index is GONE rather than guessed, because the
// archive is per-company and an index built from company prices would be ours, not
// NEPSE's, while looking exactly like the published one.

import { fmtNum, fmtPct, fmtCompactRs } from "@/lib/nepse/format";
import { useMarketAggregates } from "@/lib/nepse/use-market";

function MoverTable({ title, rows, tone }) {
  if (!rows.length) return null;
  return (
    <div className="nepse-card">
      <span className="tag">{title}</span>
      <div className="nepse-table-wrap" style={{ marginTop: "0.6rem" }}>
        <table className="nepse-table">
          <thead><tr><th>Symbol</th><th>Close</th><th>Change</th><th>Turnover</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.symbol}>
                <td className="strong">{r.symbol}</td>
                <td className="num">{fmtNum(r.close)}</td>
                <td className={`num ${tone}`}>{fmtPct(r.changePct)}</td>
                <td className="num">{r.turnover === null ? "—" : fmtCompactRs(r.turnover)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function MarketPage() {
  const { loading, data, error } = useMarketAggregates();

  if (loading) {
    return (
      <>
        <header className="nepse-head">
          <div className="nepse-eyebrow">Market</div>
          <h1 className="nepse-title">Exchange-wide state</h1>
        </header>
        <div className="nepse-empty" style={{ marginTop: "1rem" }}>
          Reading the last completed session across the listed universe…
        </div>
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <header className="nepse-head">
          <div className="nepse-eyebrow">Market</div>
          <h1 className="nepse-title">Exchange-wide state</h1>
        </header>
        {/* No fallback numbers. A market page with invented figures is worse than none. */}
        <div className="nepse-callout" style={{ marginTop: "1rem" }}>
          <strong>No market data.</strong> The daily archive could not be read
          ({error}). Nothing is shown rather than something approximate.
        </div>
      </>
    );
  }

  const b = data.breadth;
  const measured = b.measured || 1;
  const needle = Math.round((b.advancing / (b.advancing + b.declining || 1)) * 100);
  const sectors = data.sectors.filter((s) => s.status === "OK");
  const otherBuckets = data.sectors.filter((s) => s.status !== "OK");

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">Market</div>
        <h1 className="nepse-title">Exchange-wide state</h1>
        <p className="nepse-dek">
          Last completed session {data.asOf} versus {data.priorDate}, across{" "}
          {b.measured} of {data.coverage.listedTotal} listed companies. Not live —
          this is the settled session, computed from the daily archive.
        </p>
      </header>

      <div className="nepse-grid-4" style={{ marginTop: "1rem" }}>
        <div className="nepse-card">
          <span className="tag">Index</span>
          <div className="nepse-stat num" style={{ color: "var(--text-faint)" }}>—</div>
          <div style={{ color: "var(--text-faint)", fontSize: "0.78rem" }}>
            No index source. Not computed from company prices.
          </div>
        </div>
        <div className="nepse-card"><span className="tag">Turnover</span>
          <div className="nepse-stat num">{fmtCompactRs(data.activity.totalTurnover)}</div>
          <div style={{ color: "var(--text-faint)", fontSize: "0.78rem" }}>
            summed over {data.activity.turnoverReportedBy} reporting
          </div>
        </div>
        <div className="nepse-card"><span className="tag">Volume</span>
          <div className="nepse-stat num">{fmtNum(data.activity.totalVolume, 0)}</div>
          <div style={{ color: "var(--text-faint)", fontSize: "0.78rem" }}>shares</div>
        </div>
        <div className="nepse-card"><span className="tag">Coverage</span>
          <div className="nepse-stat num">{b.measured}</div>
          <div style={{ color: "var(--text-faint)", fontSize: "0.78rem" }}>
            of {data.coverage.listedTotal} listed
            {data.coverage.excluded ? ` · ${data.coverage.excluded} unmeasurable` : ""}
          </div>
        </div>
      </div>

      <div className="nepse-grid-2" style={{ marginTop: "1rem" }}>
        <div className="nepse-card">
          <span className="tag">Breadth</span>
          <h3>{b.mood[0] + b.mood.slice(1).toLowerCase()} · A/D {b.advanceDeclineRatio ?? "—"}</h3>
          <div className="nepse-gauge" style={{ marginTop: "1rem" }}>
            <div className="needle" style={{ left: `${needle}%` }} />
          </div>
          <div className="nepse-row" style={{ marginTop: "0.9rem", gap: "1.5rem", fontSize: "0.9rem" }}>
            <span className="nepse-up">Advancing {b.advancing}</span>
            <span className="nepse-down">Declining {b.declining}</span>
            <span style={{ color: "var(--text-faint)" }}>Unchanged {b.unchanged}</span>
          </div>
          <p style={{ color: "var(--text-faint)", fontSize: "0.78rem", marginTop: "0.8rem" }}>
            Percentages are of the {b.measured} companies actually measured
            ({Math.round((b.advancing / measured) * 100)}% advancing). Companies without a
            prior close are excluded, never counted as unchanged.
          </p>
        </div>
        <div className="nepse-card">
          <span className="tag">Most traded · by turnover</span>
          <div className="nepse-table-wrap" style={{ marginTop: "0.6rem" }}>
            <table className="nepse-table">
              <thead><tr><th>Symbol</th><th>Turnover</th><th>Change</th></tr></thead>
              <tbody>
                {data.mostTraded.map((r) => (
                  <tr key={r.symbol}>
                    <td className="strong">{r.symbol}</td>
                    <td className="num">{fmtCompactRs(r.turnover)}</td>
                    <td className={`num ${r.changePct >= 0 ? "nepse-up" : "nepse-down"}`}>
                      {fmtPct(r.changePct)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="nepse-grid-2" style={{ marginTop: "1rem" }}>
        <MoverTable title="Top gainers" rows={data.gainers} tone="nepse-up" />
        <MoverTable title="Top losers" rows={data.losers} tone="nepse-down" />
      </div>

      {data.repriced.length > 0 && (
        <div className="nepse-callout" style={{ marginTop: "1rem" }}>
          <strong>Held out of the movers tables:</strong>{" "}
          {data.repriced.map((r) => `${r.symbol} ${fmtPct(r.changePct)}`).join(", ")}.
          {" "}A move beyond NEPSE&apos;s ±{data.circuitLimitPct}% circuit cannot be a trade
          move. The archive is unadjusted, so this is almost certainly a book closure,
          bonus or rights issue repricing the stock — holders did not lose that.
        </div>
      )}

      <h3 style={{ margin: "1.5rem 0 0.5rem" }}>Sector performance</h3>
      <p style={{ color: "var(--text-faint)", fontSize: "0.82rem", margin: "0 0 0.75rem" }}>
        Sector is only known for {data.sectorsKnownFor} of the {b.measured} measured
        companies. Simple average first; turnover-weighted in parentheses, which follows
        the money rather than the member count.
      </p>
      <div className="nepse-grid-3">
        {sectors.map((sec) => (
          <div key={sec.sector} className="nepse-card">
            <div className="strong">{sec.sector}</div>
            <div className="nepse-row" style={{ justifyContent: "space-between", marginTop: 4 }}>
              <span style={{ color: "var(--text-faint)", fontSize: "0.8rem" }}>
                {sec.members} measured · {sec.advancing}↑ {sec.declining}↓
              </span>
              <span className={`nepse-badge ${sec.changePct >= 0 ? "up" : "down"}`}>
                {fmtPct(sec.changePct)}
                {sec.weightedChangePct === null ? "" : ` (${fmtPct(sec.weightedChangePct)})`}
              </span>
            </div>
          </div>
        ))}
      </div>

      {otherBuckets.length > 0 && (
        <div className="nepse-callout" style={{ marginTop: "1rem" }}>
          {otherBuckets.map((s) => (
            <div key={s.sector}>
              <strong>{s.sector}</strong>{" "}
              {s.status === "UNCLASSIFIED"
                ? `— ${s.members} companies whose sector this build does not know. Their
                   average (${fmtPct(s.changePct)}) is real, but it is the rest of the
                   market, not a sector.`
                : `— ${s.note}`}
            </div>
          ))}
        </div>
      )}

      <p style={{ color: "var(--text-faint)", fontSize: "0.78rem", marginTop: "1.25rem" }}>
        Source: {data.source} · {data.classification} · {data.adjustment} prices.
        Computed {new Date(data.computedAt).toLocaleString()}.
      </p>
    </>
  );
}
