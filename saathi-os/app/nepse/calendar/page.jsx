"use client";
// US6 — Calendar. Announced dividends and the IPO pipeline.
//
// Both come from scraped pages rather than a licensed feed, so the page says so
// plainly and never renders them in the same visual register as the archive-backed
// market numbers. When a layout drifts the extractor refuses, and that refusal is
// shown as itself — an empty table would read as "no dividends announced", which
// is a different and false claim.

import { useEffect, useState } from "react";
import { fmtNum, fmtRs } from "@/lib/nepse/format";

function useDataset(name) {
  const [s, setS] = useState({ loading: true, data: null, error: "", detail: "" });
  useEffect(() => {
    const ac = new AbortController();
    fetch(`/api/nepse/sharesansar?dataset=${name}`, { signal: ac.signal, cache: "no-store" })
      .then((r) => r.json())
      .then((d) => setS(d?.available
        ? { loading: false, data: d, error: "", detail: "" }
        : { loading: false, data: null, error: d?.reason || "UNAVAILABLE", detail: d?.detail || "" }))
      .catch(() => setS({ loading: false, data: null, error: "UNREACHABLE", detail: "" }));
    return () => ac.abort();
  }, [name]);
  return s;
}

function Panel({ title, state, note, children }) {
  return (
    <section style={{ marginTop: "1.5rem" }}>
      <h3 style={{ margin: "0 0 0.4rem" }}>{title}</h3>
      {note && <p style={{ color: "var(--text-faint)", fontSize: "0.82rem", margin: "0 0 0.75rem" }}>{note}</p>}
      {state.loading && <div className="nepse-empty">Reading the page…</div>}
      {!state.loading && !state.data && (
        <div className="nepse-callout">
          <strong>Not available ({state.error}).</strong>{" "}
          {state.detail
            ? `${state.detail}. Parsing was refused rather than guessed — an empty table would read as "nothing announced", which is a different claim.`
            : "Nothing is shown rather than something approximate."}
        </div>
      )}
      {!state.loading && state.data && children(state.data)}
    </section>
  );
}

export default function CalendarPage() {
  const dividends = useDataset("dividends");
  const ipos = useDataset("ipos");

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">Calendar</div>
        <h1 className="nepse-title">Dividends and issues</h1>
        <p className="nepse-dek">
          Announced dividends and the IPO pipeline, read from ShareSansar&apos;s public
          pages. Scraped, not licensed — treat these as a prompt to check the
          company&apos;s own notice, not as a record.
        </p>
      </header>

      <Panel
        title="Announced dividends"
        state={dividends}
        note="Bonus and cash are percentages of paid-up value. Fiscal year is Bikram Sambat, kept as published rather than converted."
      >
        {(d) => (
          <>
            <div className="nepse-table-wrap">
              <table className="nepse-table">
                <thead>
                  <tr><th>Symbol</th><th>Company</th><th>Bonus</th><th>Cash</th><th>Total</th>
                    <th>Book closure</th><th>Fiscal year</th><th>LTP</th></tr>
                </thead>
                <tbody>
                  {d.rows.map((r) => (
                    <tr key={`${r.symbol}-${r.bookClosureOn || r.announcedOn}`}>
                      <td className="strong">{r.symbol}</td>
                      <td>{r.company || "—"}</td>
                      <td className="num">{r.bonusPct === null ? "—" : `${fmtNum(r.bonusPct)}%`}</td>
                      <td className="num">{r.cashPct === null ? "—" : `${fmtNum(r.cashPct)}%`}</td>
                      <td className="num strong">{r.totalPct === null ? "—" : `${fmtNum(r.totalPct)}%`}</td>
                      <td className="num">{r.bookClosureOn || "—"}</td>
                      <td className="num">{r.fiscalYearBs || "—"}</td>
                      <td className="num">{r.ltp === null ? "—" : fmtNum(r.ltp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p style={{ color: "var(--text-faint)", fontSize: "0.78rem", marginTop: "0.5rem" }}>
              {d.count} announced{d.rejected ? ` · ${d.rejected} rows unreadable` : ""} · {d.source.id}
            </p>
          </>
        )}
      </Panel>

      <Panel
        title="IPO / FPO pipeline"
        state={ipos}
        note="A blank listing date means it has not listed yet — not that it listed on an unknown day."
      >
        {(d) => (
          <>
            <div className="nepse-table-wrap">
              <table className="nepse-table">
                <thead>
                  <tr><th>Symbol</th><th>Company</th><th>Units</th><th>Price</th>
                    <th>Opens</th><th>Closes</th><th>Listed</th><th>Issue manager</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {d.rows.map((r) => (
                    <tr key={`${r.symbol}-${r.opensOn}`}>
                      <td className="strong">{r.symbol}</td>
                      <td>{r.company || "—"}</td>
                      <td className="num">{r.units === null ? "—" : fmtNum(r.units, 0)}</td>
                      <td className="num">{r.pricePerUnit === null ? "—" : fmtRs(r.pricePerUnit)}</td>
                      <td className="num">{r.opensOn || "—"}</td>
                      <td className="num">{r.closesOn || "—"}</td>
                      <td className="num">{r.listedOn || "—"}</td>
                      <td>{r.issueManager || "—"}</td>
                      <td>
                        <span className={`nepse-badge ${/open|coming/i.test(r.status || "") ? "up" : ""}`}>
                          {r.status || "—"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p style={{ color: "var(--text-faint)", fontSize: "0.78rem", marginTop: "0.5rem" }}>
              {d.count} issues{d.rejected ? ` · ${d.rejected} rows unreadable` : ""} · {d.source.id}
            </p>
          </>
        )}
      </Panel>
    </>
  );
}
