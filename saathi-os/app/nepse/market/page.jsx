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
import { useMarketAggregates, useIndices } from "@/lib/nepse/use-market";

/** Real index history — the close series NEPSE published, not a generated curve. */
function IndexChart({ series }) {
  const w = 640; const h = 160; const pad = 8;
  if (!series || series.length < 2) return null;
  const vs = series.map((d) => d.close);
  const min = Math.min(...vs); const max = Math.max(...vs);
  const span = max - min || 1;
  const pts = series.map((d, i) => [
    pad + (i / (series.length - 1)) * (w - pad * 2),
    pad + (1 - (d.close - min) / span) * (h - pad * 2),
  ]);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = `${line} L${pts[pts.length - 1][0].toFixed(1)},${h} L${pts[0][0].toFixed(1)},${h} Z`;
  return (
    <>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img"
           aria-label={`NEPSE index, ${series.length} sessions to ${series[series.length - 1].date}`}>
        <path d={area} fill="var(--accent-soft)" />
        <path d={line} fill="none" stroke="var(--accent)" strokeWidth="2" />
      </svg>
      <div className="nepse-row" style={{ justifyContent: "space-between", fontSize: "0.75rem", color: "var(--text-faint)" }}>
        <span>{series[0].date} · {fmtNum(min)}</span>
        <span>{series.length} sessions</span>
        <span>{series[series.length - 1].date} · {fmtNum(max)} high</span>
      </div>
    </>
  );
}

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
  const ix = useIndices();

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

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">Market</div>
        <h1 className="nepse-title">Exchange-wide state</h1>
        <p className="nepse-dek">
          Last completed session {data.asOf} versus {data.priorDate}, across{" "}
          {b.measured} of {data.coverage.listedTotal}{" "}
          {data.universeKind === "LISTED" ? "listed companies"
            : data.universeKind === "TRADED" ? "companies that traded"
            : "companies in this build's own list"}. Not live — this is the settled
          session, computed from the daily archive.
        </p>
      </header>

      <div className="nepse-grid-4" style={{ marginTop: "1rem" }}>
        <div className="nepse-card">
          <span className="tag">NEPSE index</span>
          {ix.data?.index ? (
            <>
              <div className="nepse-stat num">{fmtNum(ix.data.index.close)}</div>
              <div className={ix.data.index.changePct >= 0 ? "nepse-up" : "nepse-down"}>
                {fmtPct(ix.data.index.changePct)} vs {ix.data.priorDate}
              </div>
            </>
          ) : (
            <>
              <div className="nepse-stat num" style={{ color: "var(--text-faint)" }}>—</div>
              <div style={{ color: "var(--text-faint)", fontSize: "0.78rem" }}>
                Index source unavailable. Never derived from company prices.
              </div>
            </>
          )}
        </div>
        <div className="nepse-card"><span className="tag">Turnover</span>
          <div className="nepse-stat num">
            {ix.data?.turnover ? fmtCompactRs(ix.data.turnover) : "—"}
          </div>
          <div style={{ color: "var(--text-faint)", fontSize: "0.78rem" }}>
            {ix.data?.turnover ? "as published with the index" : "no published figure"}
          </div>
        </div>
        <div className="nepse-card"><span className="tag">Volume</span>
          <div className="nepse-stat num">{fmtNum(data.activity.totalVolume, 0)}</div>
          <div style={{ color: "var(--text-faint)", fontSize: "0.78rem" }}>
            shares, summed over {data.activity.volumeReportedBy} companies
          </div>
        </div>
        <div className="nepse-card"><span className="tag">Coverage</span>
          <div className="nepse-stat num">{b.measured}</div>
          <div style={{ color: "var(--text-faint)", fontSize: "0.78rem" }}>
            of {data.coverage.listedTotal}{" "}
            {data.universeKind === "LISTED" ? "listed" : data.universeKind === "TRADED" ? "traded" : "curated"}
            {data.coverage.excluded ? ` · ${data.coverage.excluded} unmeasurable` : ""}
          </div>
        </div>
      </div>

      {ix.data?.markets?.length > 1 && (
        <div className="nepse-grid-4" style={{ marginTop: "0.75rem" }}>
          {ix.data.markets.filter((m) => m.index !== "NEPSE").map((m) => (
            <div key={m.index} className="nepse-card">
              <div style={{ color: "var(--text-faint)", fontSize: "0.8rem" }}>{m.label}</div>
              <div className="nepse-row" style={{ justifyContent: "space-between", marginTop: 4 }}>
                <span className="num strong">{fmtNum(m.close)}</span>
                <span className={`nepse-badge ${(m.changePct ?? 0) >= 0 ? "up" : "down"}`}>
                  {m.changePct === null ? "—" : fmtPct(m.changePct)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {ix.data?.series?.length > 1 && (
        <div className="nepse-card" style={{ marginTop: "1rem" }}>
          <span className="tag">NEPSE index · published history</span>
          <IndexChart series={ix.data.series} />
        </div>
      )}

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
      {ix.data?.sectors?.length ? (
        <>
          <p style={{ color: "var(--text-faint)", fontSize: "0.82rem", margin: "0 0 0.75rem" }}>
            NEPSE&apos;s own published sub-indices for {ix.data.asOf} against {ix.data.priorDate}.
            These replaced an average over the handful of companies whose sector this
            build knew — with two or three members a sector average was mostly noise.
          </p>
          <div className="nepse-grid-3">
            {ix.data.sectors.map((sec) => {
              // The published index says how the sector moved; the constituents we
              // could classify say how broadly. They answer different questions, so
              // both are shown and neither is derived from the other.
              const breadth = data.sectors.find(
                (b) => b.status === "OK" && b.sector.toLowerCase().replace(/[^a-z]/g, "")
                  === sec.label.toLowerCase().replace(/[^a-z]/g, ""),
              );
              return (
                <div key={sec.index} className="nepse-card">
                  <div className="strong">{sec.label}</div>
                  <div className="nepse-row" style={{ justifyContent: "space-between", marginTop: 4 }}>
                    <span className="num" style={{ color: "var(--text-faint)", fontSize: "0.85rem" }}>
                      {fmtNum(sec.close)}
                    </span>
                    <span className={`nepse-badge ${(sec.changePct ?? 0) >= 0 ? "up" : "down"}`}>
                      {sec.changePct === null ? "—" : fmtPct(sec.changePct)}
                    </span>
                  </div>
                  {breadth && (
                    <div style={{ color: "var(--text-faint)", fontSize: "0.75rem", marginTop: 4 }}>
                      {breadth.advancing}↑ {breadth.declining}↓ of {breadth.members} classified
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          {ix.data.missingSectors?.length > 0 && (
            <p style={{ color: "var(--text-faint)", fontSize: "0.78rem", marginTop: "0.75rem" }}>
              Not carried by this source: {ix.data.missingSectors.join(", ")}. NEPSE publishes
              it; its absence here is a gap in the feed, not a sector that did not move.
            </p>
          )}
          {ix.data.conflicts?.length > 0 && (
            <div className="nepse-callout" style={{ marginTop: "0.75rem" }}>
              <strong>The index source contradicted itself</strong> on{" "}
              {ix.data.conflicts.map((c) => `${c.index} (${c.values.join(" vs ")})`).join(", ")}.
              The later row is shown.
            </div>
          )}
        </>
      ) : (
        <p style={{ color: "var(--text-faint)", fontSize: "0.82rem" }}>
          Sub-indices unavailable{ix.error ? ` (${ix.error})` : ""}. Nothing is averaged
          in their place.
        </p>
      )}

      <p style={{ color: "var(--text-faint)", fontSize: "0.78rem", marginTop: "1.25rem" }}>
        Breadth, movers and volume: {data.source} · {data.classification} ·{" "}
        {data.adjustment} prices. Index, sub-indices and turnover:{" "}
        {ix.data ? `${ix.data.source} · ${ix.data.license} · ${ix.data.adjustment} prices` : "unavailable"}.
        Two independent archives; neither is used to fill a gap in the other.
        Computed {new Date(data.computedAt).toLocaleString()}.
      </p>
    </>
  );
}
