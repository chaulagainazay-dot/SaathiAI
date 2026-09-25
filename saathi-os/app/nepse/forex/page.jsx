"use client";
// Foreign exchange — Nepal Rastra Bank's published rates.
//
// BUY AND SELL ARE DIFFERENT NUMBERS and the difference is real money, so this
// page never collapses them into one "rate". The converter asks which side of the
// trade you are on, because using the wrong one is a silent ~0.4% error.
//
// NRB quotes some currencies per 100 or per 10 units. Every figure here is
// normalised to one unit as well, since "INR 160" against "INR 1.60" is the
// difference between a sensible number and a hundredfold mistake.

import { useEffect, useMemo, useState } from "react";
import { FOREX_STATE, convert, findRate } from "@/lib/nepse/forex";
import { fmtNum, fmtPct, fmtRs } from "@/lib/nepse/format";

const FAIL_TEXT = {
  [FOREX_STATE.UNREACHABLE]: "NRB did not answer. Nothing is shown rather than a cached guess.",
  [FOREX_STATE.MALFORMED]: "NRB answered in a shape this build does not recognise. Parsing was refused rather than half-read — a partially-read rate table is worse than none.",
  [FOREX_STATE.EMPTY]: "NRB published no rates for that date. Banks are shut on some of the days a calendar will happily let you pick.",
  [FOREX_STATE.HOST_NOT_ALLOWED]: "The rates URL was not on NRB's own host, so the request was not made.",
  [FOREX_STATE.NOT_CONFIGURED]: "No forex source is configured in this build.",
};

export default function ForexPage() {
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate] = useState(today);
  const [s, setS] = useState({ loading: true, data: null, state: null, detail: "" });
  const [amount, setAmount] = useState("100");
  const [code, setCode] = useState("USD");
  const [side, setSide] = useState("buy");

  useEffect(() => {
    const ac = new AbortController();
    setS((p) => ({ ...p, loading: true }));
    fetch(`/api/nepse/forex?date=${date}`, { signal: ac.signal, cache: "no-store" })
      .then((r) => r.json())
      .then((d) => setS(d?.available
        ? { loading: false, data: d, state: FOREX_STATE.OK, detail: "" }
        : { loading: false, data: null, state: d?.state || FOREX_STATE.UNREACHABLE, detail: d?.detail || "" }))
      .catch(() => setS({ loading: false, data: null, state: FOREX_STATE.UNREACHABLE, detail: "" }));
    return () => ac.abort();
  }, [date]);

  const rates = s.data?.rates || [];
  const rate = useMemo(() => findRate(rates, code), [rates, code]);
  const converted = useMemo(() => convert(amount, rate, { side }), [amount, rate, side]);

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">Forex</div>
        <h1 className="nepse-title">Nepal Rastra Bank rates</h1>
        <p className="nepse-dek">
          The published reference rate, read from NRB directly. Your bank&apos;s
          counter rate will differ — this is the benchmark, not a quote.
        </p>
      </header>

      <div className="nepse-row" style={{ margin: "1rem 0", flexWrap: "wrap" }}>
        <input className="nepse-input" type="date" aria-label="Rate date" value={date} max={today}
               onChange={(e) => setDate(e.target.value)} />
        {s.data?.date && s.data.date.slice(0, 10) !== date && (
          <span className="nepse-chip warn">
            showing {s.data.date.slice(0, 10)}, not {date}
          </span>
        )}
      </div>

      {s.loading && <div className="nepse-empty">Reading NRB…</div>}

      {!s.loading && !s.data && (
        <div className="nepse-callout">
          <strong>No rates for {date} ({s.state}).</strong>{" "}
          {FAIL_TEXT[s.state] || "Nothing is shown rather than something approximate."}
          {s.detail ? <> <span className="mono" style={{ fontSize: "0.76rem" }}>{s.detail}</span></> : null}
        </div>
      )}

      {!s.loading && s.data && (
        <>
          <div className="nepse-card" style={{ marginBottom: "1.25rem" }}>
            <h3>Convert</h3>
            <div className="nepse-row" style={{ marginTop: "0.6rem", flexWrap: "wrap" }}>
              <input className="nepse-input" style={{ width: "8rem" }} inputMode="decimal"
                     aria-label="Amount" value={amount} onChange={(e) => setAmount(e.target.value)} />
              <select className="nepse-select" aria-label="Currency" value={code}
                      onChange={(e) => setCode(e.target.value)}>
                {rates.map((r) => <option key={r.code} value={r.code}>{r.code} — {r.name}</option>)}
              </select>
              <select className="nepse-select" aria-label="Side" value={side}
                      onChange={(e) => setSide(e.target.value)}>
                <option value="buy">Buying (the bank buys your foreign currency)</option>
                <option value="sell">Selling (the bank sells you foreign currency)</option>
              </select>
            </div>
            <p style={{ marginTop: "0.75rem", fontSize: "1.15rem" }}>
              <span className="num">{fmtNum(Number(amount) || 0)} {code}</span>{" "}
              ={" "}
              <strong className="num">{converted === null ? "—" : fmtRs(converted)}</strong>
            </p>
            {rate && (
              <p style={{ fontSize: "0.78rem", color: "var(--text-faint)" }}>
                At the <strong>{side}</strong> rate of{" "}
                {fmtNum(side === "sell" ? rate.sellPerUnit : rate.buyPerUnit, 4)} per {code}.
                NRB quotes this currency per {rate.unit} unit{rate.unit === 1 ? "" : "s"};
                the per-unit figure is derived, never the quoted one reused.
                The two sides differ by {fmtPct(rate.spreadPct)} — using the wrong
                one is a silent error of exactly that size.
              </p>
            )}
          </div>

          <div className="nepse-table-wrap">
            <table className="nepse-table">
              <thead>
                <tr>
                  <th>Code</th><th>Currency</th><th className="rt">Unit</th>
                  <th className="rt">Buy</th><th className="rt">Sell</th>
                  <th className="rt">Buy / unit</th><th className="rt">Spread</th>
                </tr>
              </thead>
              <tbody>
                {rates.map((r) => (
                  <tr key={r.code}>
                    <td className="strong mono">{r.code}</td>
                    <td>{r.name ?? "—"}</td>
                    <td className="rt num">{r.unit}</td>
                    <td className="rt num">{fmtNum(r.buy, 2)}</td>
                    <td className="rt num">{fmtNum(r.sell, 2)}</td>
                    <td className="rt num">{fmtNum(r.buyPerUnit, 4)}</td>
                    <td className="rt num">{fmtPct(r.spreadPct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p style={{ fontSize: "0.76rem", color: "var(--text-faint)", marginTop: "0.6rem" }}>
            {rates.length} currencies published for {s.data.date?.slice(0, 10) ?? date}
            {s.data.published ? ` (published ${s.data.published})` : ""}.
            {s.data.rejected?.length
              ? ` ${s.data.rejected.length} row(s) were incomplete and are not shown — a one-sided rate invites being read as both sides.`
              : " No row was incomplete."}
            {" "}Source: {s.data.source}.
          </p>

          {s.data.bullion && (
            <div className="nepse-callout" style={{ marginTop: "1.25rem" }}>
              <strong>Gold and silver: no source ({s.data.bullion.state}).</strong>{" "}
              {s.data.bullion.detail}. A spot price plus an assumed local premium
              would be a number this build invented, so none is shown.
            </div>
          )}
        </>
      )}
    </>
  );
}
