"use client";
// Investor calculators — WACC, capital gains tax, right shares, SIP.
//
// Every figure on this page comes from lib/nepse/calculators.js and carries the
// fee schedule that produced it. That schedule is PROVISIONAL: the arithmetic is
// exact, the rates are policy, and a tax figure shown without the schedule behind
// it is the kind of number someone files a return against. The banner is not
// decoration — it is the difference between a calculator and a claim.

import { useMemo, useState } from "react";
import {
  INVESTOR, capitalGains, daysBetween, rightShareAdjustment, sip, wacc,
} from "@/lib/nepse/calculators";
import { EQUITY_SCHEDULE_2080, SCHEDULE_STATUS, transactionCosts } from "@/lib/nepse/fees";
import { fmtNum, fmtPct, fmtRs } from "@/lib/nepse/format";

const TABS = [
  { id: "wacc", label: "WACC" },
  { id: "cgt", label: "Capital gains" },
  { id: "right", label: "Right shares" },
  { id: "sip", label: "SIP" },
];

const money = (v) => (v === null || v === undefined ? "—" : fmtRs(v));
const pct = (v) => (v === null || v === undefined ? "—" : fmtPct(v));

function Row({ label, value, hint, strong }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem",
                  padding: "0.35rem 0", borderBottom: "1px solid var(--border)" }}>
      <span style={{ color: strong ? "var(--text)" : "var(--text-dim)",
                     fontWeight: strong ? 600 : 400, fontSize: "0.88rem" }}>
        {label}
        {hint ? <span style={{ display: "block", fontSize: "0.72rem", color: "var(--text-faint)" }}>{hint}</span> : null}
      </span>
      <span className="num" style={{ fontWeight: strong ? 700 : 500 }}>{value}</span>
    </div>
  );
}

function ScheduleNote({ id, status }) {
  return (
    <p style={{ fontSize: "0.75rem", color: "var(--text-faint)", marginTop: "0.6rem" }}>
      Schedule <span className="mono">{id}</span>
      {status === SCHEDULE_STATUS.PROVISIONAL ? (
        <> · <strong style={{ color: "var(--gold)" }}>provisional</strong> — the rates
        below have not been verified against a broker note or a SEBON circular in
        this repository. Check them before treating any figure as tax.</>
      ) : null}
    </p>
  );
}

// ── WACC ─────────────────────────────────────────────────────────────────────────

function WaccPanel() {
  const [lots, setLots] = useState([{ qty: "100", price: "500" }, { qty: "50", price: "450" }]);
  const [includeCosts, setIncludeCosts] = useState(true);
  const result = useMemo(() => wacc(lots, { includeCosts }), [lots, includeCosts]);

  const set = (i, k, v) => setLots(lots.map((l, j) => (j === i ? { ...l, [k]: v } : l)));

  return (
    <div className="nepse-grid-2">
      <div className="nepse-card">
        <h3>Purchase lots</h3>
        {lots.map((l, i) => (
          <div key={i} className="nepse-row" style={{ marginTop: "0.5rem" }}>
            <input className="nepse-input" style={{ width: "7rem" }} inputMode="decimal"
                   aria-label={`Lot ${i + 1} quantity`} placeholder="Qty"
                   value={l.qty} onChange={(e) => set(i, "qty", e.target.value)} />
            <input className="nepse-input" style={{ width: "8rem" }} inputMode="decimal"
                   aria-label={`Lot ${i + 1} price`} placeholder="Price"
                   value={l.price} onChange={(e) => set(i, "price", e.target.value)} />
            <button className="nepse-btn ghost" type="button"
                    onClick={() => setLots(lots.filter((_, j) => j !== i))}
                    disabled={lots.length === 1}>Remove</button>
          </div>
        ))}
        <div className="nepse-row" style={{ marginTop: "0.75rem" }}>
          <button className="nepse-btn" type="button"
                  onClick={() => setLots([...lots, { qty: "", price: "" }])}>Add lot</button>
          <label style={{ display: "flex", gap: "0.4rem", alignItems: "center", fontSize: "0.82rem" }}>
            <input type="checkbox" checked={includeCosts}
                   onChange={(e) => setIncludeCosts(e.target.checked)} />
            Include purchase costs in the basis
          </label>
        </div>
        <p style={{ fontSize: "0.75rem", color: "var(--text-faint)", marginTop: "0.6rem" }}>
          Commission, SEBON fee and DP charge on the way IN are part of what the
          shares cost you. Excluding them overstates the eventual gain — and the
          tax on it — so they are included by default.
        </p>
      </div>

      <div className="nepse-card">
        <h3>Weighted average cost</h3>
        <Row label="Total quantity" value={result.qty ? fmtNum(result.qty, 0) : "—"} />
        <Row label="Total cost" value={money(result.totalCost)} />
        <Row label="WACC per share" value={money(result.wacc)} strong
             hint={result.includesCosts ? "including purchase costs" : "excluding purchase costs"} />
        {result.rejected.length > 0 && (
          <p style={{ fontSize: "0.78rem", color: "var(--down)", marginTop: "0.6rem" }}>
            {result.rejected.length} lot{result.rejected.length === 1 ? "" : "s"} ignored —
            a quantity or price was missing or not a number. They are not counted as
            zero-cost shares.
          </p>
        )}
        {result.wacc === null && (
          <p style={{ fontSize: "0.78rem", color: "var(--text-faint)", marginTop: "0.6rem" }}>
            No usable lot, so there is no cost basis. This is not a WACC of zero —
            that would make every future sale look like pure profit.
          </p>
        )}
        <ScheduleNote id={result.schedule} status={result.status} />
      </div>
    </div>
  );
}

// ── Capital gains ────────────────────────────────────────────────────────────────

function CgtPanel() {
  const [f, setF] = useState({
    qty: "100", buyPrice: "500", sellPrice: "600",
    buyDate: "2024-01-10", sellDate: "2025-06-20", investor: INVESTOR.INDIVIDUAL,
  });
  const on = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const r = useMemo(() => capitalGains({
    qty: f.qty, buyPrice: f.buyPrice, sellPrice: f.sellPrice,
    investor: f.investor, buyDate: f.buyDate || null, sellDate: f.sellDate || null,
  }), [f]);
  const held = daysBetween(f.buyDate || null, f.sellDate || null);

  return (
    <div className="nepse-grid-2">
      <div className="nepse-card">
        <h3>Sale</h3>
        <div className="nepse-row" style={{ marginTop: "0.5rem", flexWrap: "wrap" }}>
          <input className="nepse-input" style={{ width: "7rem" }} aria-label="Quantity"
                 placeholder="Qty" inputMode="decimal" value={f.qty} onChange={on("qty")} />
          <input className="nepse-input" style={{ width: "8rem" }} aria-label="Buy price"
                 placeholder="Buy price" inputMode="decimal" value={f.buyPrice} onChange={on("buyPrice")} />
          <input className="nepse-input" style={{ width: "8rem" }} aria-label="Sell price"
                 placeholder="Sell price" inputMode="decimal" value={f.sellPrice} onChange={on("sellPrice")} />
        </div>
        <div className="nepse-row" style={{ marginTop: "0.5rem", flexWrap: "wrap" }}>
          <input className="nepse-input" type="date" aria-label="Buy date" value={f.buyDate} onChange={on("buyDate")} />
          <input className="nepse-input" type="date" aria-label="Sell date" value={f.sellDate} onChange={on("sellDate")} />
          <select className="nepse-select" aria-label="Investor type" value={f.investor} onChange={on("investor")}>
            <option value={INVESTOR.INDIVIDUAL}>Individual</option>
            <option value={INVESTOR.INSTITUTIONAL}>Institutional</option>
          </select>
        </div>
        <p style={{ fontSize: "0.75rem", color: "var(--text-faint)", marginTop: "0.6rem" }}>
          The holding period sets the rate, so leaving a date blank leaves the rate
          UNDETERMINED rather than defaulting to the cheaper one.
          {held === null ? "" : ` Held ${fmtNum(held, 0)} days.`}
        </p>
      </div>

      <div className="nepse-card">
        <h3>Result</h3>
        {!r.ok ? (
          <p style={{ color: "var(--text-faint)", fontSize: "0.85rem" }}>
            Enter a quantity and both prices.
          </p>
        ) : (
          <>
            <Row label="Cost basis" hint="purchase + buy-side costs" value={money(r.costBasis)} />
            <Row label="Net proceeds" hint="sale − sell-side costs" value={money(r.netProceeds)} />
            <Row label="Gain" value={money(r.gain)} strong />
            <Row label="Term" value={r.term ?? "—"} />
            {/* Not fmtPct: that signs the number for a CHANGE, and "+5.00%" reads
                as a rate that went up rather than a rate of five percent. */}
            <Row label="CGT rate" value={r.cgtRate === null ? "—" : `${fmtNum(r.cgtRate * 100)}%`} />
            <Row label="Tax" value={money(r.tax)} />
            <Row label="Net profit" value={money(r.netProfit)} strong />
            <Row label="Return on cost" value={pct(r.roiPct)} />
            {r.gain <= 0 && (
              <p style={{ fontSize: "0.78rem", color: "var(--text-faint)", marginTop: "0.5rem" }}>
                A loss attracts no tax. Nothing is shown as a refund or credit.
              </p>
            )}
            {r.note && (
              <p style={{ fontSize: "0.78rem", color: "var(--gold)", marginTop: "0.5rem" }}>{r.note}</p>
            )}
            <ScheduleNote id={r.schedule} status={r.status} />
          </>
        )}
      </div>
    </div>
  );
}

// ── Right shares ─────────────────────────────────────────────────────────────────

function RightPanel() {
  const [f, setF] = useState({ marketPrice: "600", ratio: "0.5", rightPrice: "100", bonusPct: "0" });
  const on = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const r = useMemo(() => rightShareAdjustment({
    marketPrice: f.marketPrice, ratio: f.ratio, rightPrice: f.rightPrice, bonusPct: f.bonusPct,
  }), [f]);

  return (
    <div className="nepse-grid-2">
      <div className="nepse-card">
        <h3>Issue</h3>
        <div className="nepse-row" style={{ marginTop: "0.5rem", flexWrap: "wrap" }}>
          <input className="nepse-input" style={{ width: "9rem" }} aria-label="Market price"
                 placeholder="Market price" inputMode="decimal" value={f.marketPrice} onChange={on("marketPrice")} />
          <select className="nepse-select" aria-label="Right ratio" value={f.ratio} onChange={on("ratio")}>
            <option value="1">1:1 — one new for each held</option>
            <option value="0.5">1:2 — one new for every two held</option>
            <option value="0.3333333333">1:3</option>
            <option value="0.25">1:4</option>
            <option value="0.2">1:5</option>
          </select>
        </div>
        <div className="nepse-row" style={{ marginTop: "0.5rem", flexWrap: "wrap" }}>
          <input className="nepse-input" style={{ width: "9rem" }} aria-label="Right price"
                 placeholder="Right price" inputMode="decimal" value={f.rightPrice} onChange={on("rightPrice")} />
          <input className="nepse-input" style={{ width: "9rem" }} aria-label="Bonus percent"
                 placeholder="Bonus %" inputMode="decimal" value={f.bonusPct} onChange={on("bonusPct")} />
        </div>
      </div>

      <div className="nepse-card">
        <h3>Theoretical ex-right price</h3>
        {!r.ok ? (
          <p style={{ color: "var(--text-faint)", fontSize: "0.85rem" }}>Enter a market price and ratio.</p>
        ) : (
          <>
            <Row label="Adjusted price" value={money(r.adjustedPrice)} strong />
            <Row label="Apparent drop per share" value={money(r.dropPerShare)} />
            <Row label="Value of the right" value={money(r.valueOfRight)} />
            <Row label="Shares held per old share" value={fmtNum(r.sharesPerOld, 4)} />
            <div className="nepse-callout" style={{ marginTop: "0.75rem" }}>
              <strong>This drop is arithmetic, not a loss.</strong> You hold more
              shares at a lower blended price for the same money. A portfolio screen
              that shows the fall as negative P&amp;L is misreading it — this is the
              single most common misreading on a Nepali holdings page.
            </div>
            <p style={{ fontSize: "0.75rem", color: "var(--text-faint)", marginTop: "0.6rem" }}>{r.note}</p>
          </>
        )}
      </div>
    </div>
  );
}

// ── SIP ──────────────────────────────────────────────────────────────────────────

function SipPanel() {
  const [f, setF] = useState({ monthly: "5000", years: "10", annualReturnPct: "12" });
  const on = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const r = useMemo(() => sip(f), [f]);

  return (
    <div className="nepse-grid-2">
      <div className="nepse-card">
        <h3>Standing instruction</h3>
        <div className="nepse-row" style={{ marginTop: "0.5rem", flexWrap: "wrap" }}>
          <input className="nepse-input" style={{ width: "9rem" }} aria-label="Monthly amount"
                 placeholder="Monthly Rs" inputMode="decimal" value={f.monthly} onChange={on("monthly")} />
          <input className="nepse-input" style={{ width: "6rem" }} aria-label="Years"
                 placeholder="Years" inputMode="decimal" value={f.years} onChange={on("years")} />
          <input className="nepse-input" style={{ width: "7rem" }} aria-label="Assumed annual return percent"
                 placeholder="Return %" inputMode="decimal" value={f.annualReturnPct}
                 onChange={on("annualReturnPct")} />
        </div>
        <p style={{ fontSize: "0.75rem", color: "var(--text-faint)", marginTop: "0.6rem" }}>
          Contributions are applied at the start of each period, which is what a
          standing instruction actually does. Treating it as an end-of-period
          annuity understates the result.
        </p>
      </div>

      <div className="nepse-card">
        <h3>Projection</h3>
        {!r.ok ? (
          <p style={{ color: "var(--text-faint)", fontSize: "0.85rem" }}>
            Enter an amount, a number of years and an assumed return.
          </p>
        ) : (
          <>
            <Row label="Invested" value={money(r.invested)} />
            <Row label="Projected value" value={money(r.futureValue)} strong />
            <Row label="Gain" value={money(r.gain)} />
            <Row label="Multiple" value={r.multiple === null ? "—" : `${fmtNum(r.multiple, 2)}×`} />
            <div className="nepse-table-wrap" style={{ marginTop: "0.75rem", maxHeight: 220, overflowY: "auto" }}>
              <table className="nepse-table">
                <thead><tr><th>Year</th><th className="rt">Invested</th><th className="rt">Value</th></tr></thead>
                <tbody>
                  {r.schedule.map((s) => (
                    <tr key={s.year}>
                      <td>{s.year}</td>
                      <td className="rt num">{fmtRs(s.invested)}</td>
                      <td className="rt num">{fmtRs(s.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p style={{ fontSize: "0.78rem", color: "var(--gold)", marginTop: "0.6rem" }}>{r.note}</p>
          </>
        )}
      </div>
    </div>
  );
}

// ── page ─────────────────────────────────────────────────────────────────────────

export default function CalculatorsPage() {
  const [tab, setTab] = useState("wacc");
  const sample = useMemo(() => transactionCosts(100_000), []);

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">Calculators</div>
        <h1 className="nepse-title">What a trade actually costs</h1>
        <p className="nepse-dek">
          Cost basis, capital gains tax, right-share adjustment and SIP projection —
          every one of them carrying the fee schedule that produced it.
        </p>
      </header>

      <div className="nepse-callout gold" style={{ marginTop: "1rem" }}>
        <strong>The rates are provisional.</strong> Broker commission, SEBON fee, DP
        charge and CGT are policy figures that change by circular. The arithmetic
        here is exact; the schedule behind it has not been verified in this
        repository. On Rs 100,000 it charges{" "}
        <span className="num">{fmtRs(sample.total)}</span> in total costs
        (commission {fmtRs(sample.commission)}, SEBON {fmtRs(sample.sebon)},
        DP {fmtRs(sample.dp)}). Check that against your own broker note before
        relying on any figure below.
      </div>

      <div className="nepse-tabs" style={{ marginTop: "1.25rem" }}>
        {TABS.map((t) => (
          <button key={t.id} type="button" onClick={() => setTab(t.id)}
                  className={`nepse-tab ${tab === t.id ? "active" : ""}`}
                  style={{ background: "none", border: 0, cursor: "pointer",
                           borderBottom: "2px solid", borderBottomColor: tab === t.id ? "var(--accent)" : "transparent" }}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "wacc" && <WaccPanel />}
      {tab === "cgt" && <CgtPanel />}
      {tab === "right" && <RightPanel />}
      {tab === "sip" && <SipPanel />}

      <p style={{ fontSize: "0.75rem", color: "var(--text-faint)", marginTop: "1.5rem" }}>
        Schedule <span className="mono">{EQUITY_SCHEDULE_2080.id}</span>, effective
        from {EQUITY_SCHEDULE_2080.effectiveFrom}. Not investment or tax advice.
      </p>
    </>
  );
}
