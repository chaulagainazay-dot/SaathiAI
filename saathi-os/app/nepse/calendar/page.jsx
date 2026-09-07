"use client";
// US6 — Calendar. Announced dividends and the IPO pipeline.
//
// Both come from scraped pages rather than a licensed feed, so the page says so
// plainly and never renders them in the same visual register as the archive-backed
// market numbers. When a layout drifts the extractor refuses, and that refusal is
// shown as itself — an empty table would read as "no dividends announced", which
// is a different and false claim.

import { useEffect, useMemo, useState } from "react";
import { fmtNum, fmtRs } from "@/lib/nepse/format";
import {
  DAY_KIND, calendarFromCounts, closuresByMonth, statusFor, weekdayProfile,
} from "@/lib/nepse/holidays";
import { fiscalYearsIn, filterByFiscalYear } from "@/lib/nepse/bs";

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

const KIND_LABEL = {
  [DAY_KIND.TRADED]: "Open — the archive records sessions",
  [DAY_KIND.WEEKEND]: "Weekend — NEPSE trades Sunday to Thursday",
  [DAY_KIND.CLOSED]: "Closed — no session, with trading either side",
  [DAY_KIND.UNCONFIRMED]: "Unknown — the archive is too sparse here to say",
};

const KIND_TONE = {
  [DAY_KIND.TRADED]: "up",
  [DAY_KIND.WEEKEND]: "neutral",
  [DAY_KIND.CLOSED]: "down",
  [DAY_KIND.UNCONFIRMED]: "neutral",
};

/**
 * The trading calendar is DERIVED, never a hardcoded holiday list.
 *
 * A day is CLOSED only when the archive recorded sessions on both sides of it —
 * that is what separates "the exchange was shut" from "our data stops here". A
 * hardcoded list of festivals would confidently mark a day the exchange actually
 * opened, and would quietly go stale the year the dates move.
 */
function TradingCalendar() {
  const [s, setS] = useState({ loading: true, counts: null, error: "" });
  const [pick, setPick] = useState(new Date().toISOString().slice(0, 10));

  useEffect(() => {
    const ac = new AbortController();
    fetch("/api/nepse/indicators", { signal: ac.signal, cache: "no-store" })
      .then((r) => r.json())
      .then((d) => setS(d?.sessions && Object.keys(d.sessions).length
        ? { loading: false, counts: d.sessions, error: "" }
        : { loading: false, counts: null, error: d?.reason || "NO_SESSIONS" }))
      .catch(() => setS({ loading: false, counts: null, error: "UNREACHABLE" }));
    return () => ac.abort();
  }, []);

  const cal = useMemo(
    () => (s.counts ? calendarFromCounts(s.counts, { minTradedFor: 3 }) : null),
    [s.counts],
  );
  const months = useMemo(() => (cal ? closuresByMonth(cal).slice(-12).reverse() : []), [cal]);
  const day = useMemo(() => (cal ? statusFor(cal, pick) : null), [cal, pick]);
  const profile = useMemo(() => (s.counts ? weekdayProfile(s.counts) : null), [s.counts]);
  const disputed = cal?.disputedMonths || [];

  return (
    <section style={{ marginTop: "1.5rem" }}>
      <h3 style={{ margin: "0 0 0.4rem" }}>Trading calendar</h3>
      <p style={{ color: "var(--text-faint)", fontSize: "0.82rem", margin: "0 0 0.75rem" }}>
        Derived from which days the archive actually recorded sessions, not from a
        list of festivals typed in by hand. A weekday with no sessions is only
        called CLOSED when trading is recorded on both sides of it.
      </p>

      {s.loading && <div className="nepse-empty">Reading the archive…</div>}
      {!s.loading && !cal && (
        <div className="nepse-callout">
          <strong>No calendar ({s.error}).</strong> Without session evidence the
          only honest answer about any given day is &ldquo;unknown&rdquo;.
        </div>
      )}

      {cal && (
        <>
          <div className="nepse-row" style={{ marginBottom: "0.75rem", flexWrap: "wrap" }}>
            <input className="nepse-input" type="date" aria-label="Check a date"
                   value={pick} onChange={(e) => setPick(e.target.value)} />
            {day && (
              <span className={`nepse-badge ${KIND_TONE[day.kind]}`}>
                {/* "Too sparse to say" is the wrong reason for a date the archive
                    simply does not reach yet. Both are unknown; they are unknown
                    for different reasons and the reader can act on only one. */}
                {day.outsideArchive && day.kind === DAY_KIND.UNCONFIRMED
                  ? "Unknown — past the last day the archive carries"
                  : KIND_LABEL[day.kind]}
              </span>
            )}
            {day?.outsideArchive && (
              <span className="nepse-chip warn">
                archive ends {cal.span?.to}
              </span>
            )}
            {day?.kind === DAY_KIND.TRADED && (
              <span style={{ fontSize: "0.8rem", color: "var(--text-faint)" }}>
                {fmtNum(day.instruments, 0)} instruments reported
              </span>
            )}
          </div>

          <div className="nepse-table-wrap">
            <table className="nepse-table">
              <thead><tr><th>Month</th><th>Weekday closures</th></tr></thead>
              <tbody>
                {months.length === 0 ? (
                  <tr><td colSpan={2} style={{ color: "var(--text-faint)" }}>
                    No confirmed weekday closure in the archive&apos;s span.
                  </td></tr>
                ) : months.map((m) => (
                  <tr key={m.month}>
                    <td className="strong mono">{m.month}</td>
                    <td className="num" style={{ fontSize: "0.82rem" }}>
                      {m.days.map((d) => d.date.slice(8)).join(", ")}
                      <span style={{ color: "var(--text-faint)" }}> ({m.days.length})</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p style={{ color: "var(--text-faint)", fontSize: "0.78rem", marginTop: "0.5rem" }}>
            {cal.closures.length} confirmed closures across {cal.coverage} recorded
            session days, {cal.span?.from} to {cal.span?.to}. The last 12 months with a
            closure are listed. Days the archive cannot speak for are reported as
            unknown rather than assumed open.
          </p>

          {disputed.length > 0 && (
            <div className="nepse-callout gold" style={{ marginTop: "0.75rem" }}>
              <strong>
                {disputed.length} month{disputed.length === 1 ? "" : "s"} cannot be
                classified at all, including {disputed.slice(-3).join(", ")}.
              </strong>{" "}
              NEPSE trades Sunday to Thursday, and in these months the archive
              records busy Fridays. That is not an exchange that opened on a Friday —
              it is a month whose dates are shifted, and a shift moves every date in
              it. Marking only the Fridays would leave the neighbouring
              &ldquo;closures&rdquo; standing, and those are the fabricated ones, so
              the whole month is reported as unknown.
              {profile && (
                <div className="mono" style={{ fontSize: "0.72rem", marginTop: "0.4rem" }}>
                  session days by weekday — Sun {profile[0]} · Mon {profile[1]} ·
                  Tue {profile[2]} · Wed {profile[3]} · Thu {profile[4]} ·
                  Fri {profile[5]} · Sat {profile[6]}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}

export default function CalendarPage() {
  const dividends = useDataset("dividends");
  const ipos = useDataset("ipos");
  const [fy, setFy] = useState("");

  // Fiscal years are Bikram Sambat and stay as published. They are SORTED by the
  // year they start, not alphabetically — "2080/81" and "2079/80" sort correctly
  // as strings only by luck, and stop doing so the moment a label is formatted
  // differently.
  const fyOptions = useMemo(
    () => fiscalYearsIn(dividends.data?.rows || [], "fiscalYearBs"),
    [dividends.data],
  );
  const dividendRows = useMemo(
    () => (fy ? filterByFiscalYear(dividends.data?.rows || [], fy, "fiscalYearBs")
              : dividends.data?.rows || []),
    [dividends.data, fy],
  );

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
            {fyOptions.length > 1 && (
              <div className="nepse-row" style={{ marginBottom: "0.6rem", flexWrap: "wrap" }}>
                <select className="nepse-select" aria-label="Fiscal year" value={fy}
                        onChange={(e) => setFy(e.target.value)}>
                  <option value="">All fiscal years</option>
                  {fyOptions.map((y) => <option key={y} value={y}>{y}</option>)}
                </select>
                <span style={{ fontSize: "0.76rem", color: "var(--text-faint)" }}>
                  Bikram Sambat, as published. Nothing is converted to A.D. — Nepali
                  month lengths come from an almanac, not a formula.
                </span>
              </div>
            )}
            <div className="nepse-table-wrap">
              <table className="nepse-table">
                <thead>
                  <tr><th>Symbol</th><th>Company</th><th>Bonus</th><th>Cash</th><th>Total</th>
                    <th>Book closure</th><th>Fiscal year</th><th>LTP</th></tr>
                </thead>
                <tbody>
                  {dividendRows.map((r) => (
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
              {fy ? `${dividendRows.length} of ${d.count}` : d.count} announced
              {fy ? ` in ${fy}` : ""}{d.rejected ? ` · ${d.rejected} rows unreadable` : ""} · {d.source.id}
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

      <TradingCalendar />
    </>
  );
}
