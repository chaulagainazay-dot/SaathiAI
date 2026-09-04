"use client";
// US1 — Portfolio (Home). Create a named, color-tagged portfolio; log buy/sell/
// receivable transactions; read total value / investment / receivable derived from
// the transaction log + snapshot prices. Import path is file-based (Meroshare / TMS /
// Nepal Share). All state is localStorage-only (see lib/nepse/store).
import { useEffect, useMemo, useState } from "react";
import { STOCKS } from "@/lib/nepse/data";
import { computePortfolio, PORTFOLIO_COLORS } from "@/lib/nepse/portfolio";
import { importTransactions } from "@/lib/nepse/importers";
import { fmtRs, fmtNum, fmtPct } from "@/lib/nepse/format";
import * as store from "@/lib/nepse/store";

const PRICE_MAP = Object.fromEntries(STOCKS.map((s) => [s.symbol, s.ltp]));
const SYMBOLS = STOCKS.map((s) => s.symbol);

export default function PortfolioHome() {
  const [state, setState] = useState(null); // null until mounted (SSR-safe)
  const [tab, setTab] = useState("value");
  const [newName, setNewName] = useState("");
  const [colorIdx, setColorIdx] = useState(0);
  const [form, setForm] = useState({ symbol: "NABIL", side: "BUY", qty: "", price: "", date: "" });
  const [importSrc, setImportSrc] = useState("meroshare");
  const [importMsg, setImportMsg] = useState("");

  useEffect(() => { setState(store.loadState()); }, []);

  const active = useMemo(
    () => state?.portfolios.find((p) => p.id === state.activeId) || null,
    [state],
  );
  const computed = useMemo(
    () => (active ? computePortfolio(active.transactions, PRICE_MAP) : null),
    [active],
  );

  if (!state) return <div className="nepse-empty">Loading…</div>;

  const createPortfolio = () => {
    if (!newName.trim()) return;
    setState(store.createPortfolio(newName, colorIdx));
    setNewName("");
  };
  const addTx = () => {
    if (!active) return;
    const qty = Number(form.qty);
    const price = Number(form.price);
    if (!(qty > 0)) return;
    setState(store.addTransaction(active.id, {
      symbol: form.symbol, side: form.side, qty, price,
      date: form.date || new Date().toISOString().slice(0, 10),
    }));
    setForm({ ...form, qty: "", price: "" });
  };
  const doImport = (text) => {
    if (!active) { setImportMsg("Create a portfolio first."); return; }
    try {
      const txs = importTransactions(importSrc, text);
      if (!txs.length) { setImportMsg("No rows parsed — check the file format."); return; }
      setState(store.addTransactions(active.id, txs));
      setImportMsg(`Imported ${txs.length} row(s) from ${importSrc}.`);
    } catch (e) { setImportMsg(String(e.message || e)); }
  };
  const onFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const r = new FileReader();
    r.onload = () => doImport(String(r.result || ""));
    r.readAsText(f);
  };

  const headline = computed
    ? { value: computed.totals.value, invest: computed.totals.invested, recv: computed.totals.receivable }
    : { value: 0, invest: 0, recv: 0 };
  const shown = tab === "value" ? headline.value : tab === "invest" ? headline.invest : headline.recv;

  return (
    <>
      <header className="nepse-head">
        <div className="nepse-eyebrow">Portfolio</div>
        <h1 className="nepse-title">Your NEPSE holdings</h1>
        <p className="nepse-dek">
          Everything here is scoped to a portfolio — a named, color-tagged container.
          No portfolio exists until you make one; every write blocks on that first.
        </p>
      </header>

      {/* portfolio selector + creator */}
      <div className="nepse-card" style={{ marginTop: "1rem" }}>
        <div className="nepse-row" style={{ justifyContent: "space-between" }}>
          <div className="nepse-row">
            {state.portfolios.map((p) => (
              <button
                key={p.id}
                onClick={() => setState(store.setActive(p.id))}
                className={`nepse-tab ${p.id === state.activeId ? "active" : ""}`}
                style={{ borderBottom: "none", display: "flex", gap: 6, alignItems: "center" }}
              >
                <span style={{ width: 10, height: 10, borderRadius: 3, background: p.color, display: "inline-block" }} />
                {p.name}
              </button>
            ))}
            {!state.portfolios.length && <span style={{ color: "var(--text-faint)" }}>No portfolios yet.</span>}
          </div>
        </div>
        <div className="nepse-row" style={{ marginTop: "0.9rem" }}>
          <input className="nepse-input" placeholder="New portfolio name" value={newName}
            onChange={(e) => setNewName(e.target.value)} />
          <div className="nepse-row" style={{ gap: 4 }}>
            {PORTFOLIO_COLORS.map((c, i) => (
              <span key={c} onClick={() => setColorIdx(i)}
                className={`nepse-swatch ${i === colorIdx ? "sel" : ""}`} style={{ background: c }} />
            ))}
          </div>
          <button className="nepse-btn" onClick={createPortfolio} disabled={!newName.trim()}>Create portfolio</button>
        </div>
      </div>

      {active && computed && (
        <>
          {/* headline totals */}
          <div className="nepse-card" style={{ marginTop: "1rem" }}>
            <div className="nepse-tabs" style={{ margin: 0, border: "none" }}>
              {[["value", "Total value"], ["invest", "Investment"], ["recv", "Receivable"]].map(([k, l]) => (
                <button key={k} className={`nepse-tab ${tab === k ? "active" : ""}`} onClick={() => setTab(k)}>{l}</button>
              ))}
            </div>
            <div className="nepse-stat big num" style={{ marginTop: "0.5rem" }}>{fmtRs(shown)}</div>
            <div className="nepse-row" style={{ marginTop: "0.5rem", gap: "1.5rem" }}>
              <span>Unrealized <b className={computed.totals.unrealizedPnl >= 0 ? "nepse-up" : "nepse-down"}>
                {fmtRs(computed.totals.unrealizedPnl)} ({fmtPct(computed.totals.returnPct)})</b></span>
              <span>Realized <b className={computed.totals.realizedPnl >= 0 ? "nepse-up" : "nepse-down"}>
                {fmtRs(computed.totals.realizedPnl)}</b></span>
            </div>
          </div>

          {/* add transaction */}
          <div className="nepse-card" style={{ marginTop: "1rem" }}>
            <h3>Add transaction</h3>
            <div className="nepse-row" style={{ marginTop: "0.6rem" }}>
              <select className="nepse-select" value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })}>
                {SYMBOLS.map((s) => <option key={s}>{s}</option>)}
              </select>
              <select className="nepse-select" value={form.side} onChange={(e) => setForm({ ...form, side: e.target.value })}>
                <option>BUY</option><option>SELL</option><option>RECEIVABLE</option>
              </select>
              <input className="nepse-input" type="number" min="0" placeholder="Qty" style={{ width: 100 }}
                value={form.qty} onChange={(e) => setForm({ ...form, qty: e.target.value })} />
              <input className="nepse-input" type="number" min="0" placeholder="Price (Rs)" style={{ width: 120 }}
                value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />
              <input className="nepse-input" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
              <button className="nepse-btn" onClick={addTx} disabled={!(Number(form.qty) > 0)}>Add</button>
            </div>
          </div>

          {/* holdings table */}
          <div className="nepse-table-wrap" style={{ marginTop: "1rem" }}>
            <table className="nepse-table">
              <thead><tr>
                <th>Symbol</th><th className="rt">Qty</th><th className="rt">Avg cost</th>
                <th className="rt">LTP</th><th className="rt">Invested</th><th className="rt">Value</th><th className="rt">Unreal. P&amp;L</th>
              </tr></thead>
              <tbody>
                {computed.holdings.map((h) => (
                  <tr key={h.symbol}>
                    <td className="strong"><a href={`/nepse/stocks/${h.symbol}`}>{h.symbol}</a></td>
                    <td className="rt num">{fmtNum(h.qty, 0)}</td>
                    <td className="rt num">{fmtRs(h.avgCost)}</td>
                    <td className="rt num">{fmtRs(h.ltp)}</td>
                    <td className="rt num">{fmtRs(h.invested)}</td>
                    <td className="rt num">{fmtRs(h.marketValue)}</td>
                    <td className={`rt num ${h.unrealizedPnl >= 0 ? "nepse-up" : "nepse-down"}`}>{fmtRs(h.unrealizedPnl)}</td>
                  </tr>
                ))}
                {!computed.holdings.length && (
                  <tr><td colSpan={7} className="nepse-empty">No holdings yet — add a transaction or import a file.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          {computed.rejected.length > 0 && (
            <p style={{ color: "var(--down)", marginTop: 8, fontSize: "0.85rem" }}>
              {computed.rejected.length} transaction(s) rejected (e.g. over-sell / invalid).
            </p>
          )}

          {/* import dashboard */}
          <div className="nepse-card" style={{ marginTop: "1.25rem" }}>
            <h3>Import dashboard — the real onboarding path</h3>
            <p style={{ color: "var(--text-dim)", fontSize: "0.9rem", margin: "0.4rem 0 0.9rem" }}>
              File-based, no live brokerage connection. Export from your platform, then upload here.
            </p>
            <div className="nepse-row">
              <select className="nepse-select" value={importSrc} onChange={(e) => setImportSrc(e.target.value)}>
                <option value="meroshare">Meroshare (CSV)</option>
                <option value="tms">TMS (Excel → CSV)</option>
                <option value="nepalshare">Nepal Share (CSV / TSV)</option>
              </select>
              <input className="nepse-input" type="file" accept=".csv,.tsv,.txt" onChange={onFile} />
            </div>
            {importMsg && <p className="nepse-callout" style={{ marginTop: "0.8rem" }}>{importMsg}</p>}
          </div>
        </>
      )}
    </>
  );
}
