"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { formatPaisa, hcgActions, HCG_NOTICE, safeToken } from "@/lib/hcg";

const NAV = [
  "Overview",
  "POS",
  "Orders",
  "Kitchen",
  "Menu",
  "Inventory",
  "Purchases",
  "Expenses",
  "Credit",
  "Suppliers",
  "Shifts",
  "Reports",
  "Notifications",
  "Settings",
];

const card = {
  background: "rgba(18, 28, 48, 0.92)",
  border: "1px solid rgba(120, 150, 200, 0.18)",
  borderRadius: 12,
  padding: 14,
};

const btn = {
  background: "#2B6CFF",
  color: "#fff",
  border: "none",
  borderRadius: 8,
  padding: "10px 14px",
  cursor: "pointer",
  fontWeight: 600,
  minHeight: 40,
};

const btnGhost = {
  ...btn,
  background: "transparent",
  border: "1px solid rgba(120,150,200,0.35)",
  color: "#D7E2F5",
};

export default function HcgWorkspace() {
  const [token, setToken] = useState("");
  const [view, setView] = useState("Overview");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dashboard, setDashboard] = useState(null);
  const [menu, setMenu] = useState({ items: [], categories: [] });
  const [basket, setBasket] = useState([]);
  const [orders, setOrders] = useState([]);
  const [kitchen, setKitchen] = useState([]);
  const [shifts, setShifts] = useState([]);
  const [inventory, setInventory] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [expenses, setExpenses] = useState([]);
  const [report, setReport] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [searchQ, setSearchQ] = useState("");
  const [searchHits, setSearchHits] = useState([]);
  const [yetiQ, setYetiQ] = useState("What were today’s sales?");
  const [yetiA, setYetiA] = useState(null);
  const [activeShift, setActiveShift] = useState(null);
  const [payMethod, setPayMethod] = useState("CASH");
  const [qrRef, setQrRef] = useState("");
  const [creditCustomer, setCreditCustomer] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [statement, setStatement] = useState(null);
  const [backupPayload, setBackupPayload] = useState(null);
  const [statusMsg, setStatusMsg] = useState("");

  useEffect(() => {
    setToken(safeToken());
  }, []);

  const refreshCore = useCallback(async () => {
    const t = safeToken() || token;
    if (!t) return;
    setError("");
    try {
      const [d, m, o, k, s, inv, c, sup, exp, n] = await Promise.all([
        hcgActions.dashboard(t),
        hcgActions.menu(t),
        hcgActions.orders(t),
        hcgActions.kitchen(t),
        hcgActions.shifts(t),
        hcgActions.inventory(t),
        hcgActions.customers(t),
        hcgActions.suppliers(t),
        hcgActions.expenses(t),
        hcgActions.notifications(t),
      ]);
      setDashboard(d.dashboard || null);
      setMenu({ items: m.items || [], categories: m.categories || [] });
      setOrders(o.orders || []);
      setKitchen(k.tickets || []);
      setShifts(s.shifts || []);
      setInventory(inv.items || []);
      setCustomers(c.customers || []);
      setSuppliers(sup.suppliers || []);
      setExpenses(exp.expenses || []);
      setNotifications(n.notifications || []);
      const open = (s.shifts || []).find((x) => x.status === "OPEN");
      setActiveShift(open || null);
      if (!creditCustomer && (c.customers || []).length) {
        setCreditCustomer(c.customers[0].record_id);
      }
    } catch (e) {
      setError(e.message || "Load failed");
    }
  }, [token, creditCustomer]);

  useEffect(() => {
    if (token) refreshCore();
  }, [token, refreshCore]);

  const basketTotal = useMemo(
    () =>
      basket.reduce(
        (sum, line) => sum + line.qty * line.unit_price_minor - (line.discount_minor || 0),
        0
      ),
    [basket]
  );

  const filteredMenu = useMemo(() => {
    let items = menu.items || [];
    if (categoryFilter) {
      items = items.filter((i) => (i.body || {}).category_id === categoryFilter);
    }
    return items;
  }, [menu, categoryFilter]);

  async function run(fn) {
    setBusy(true);
    setError("");
    setStatusMsg("");
    try {
      await fn();
      await refreshCore();
    } catch (e) {
      setError(e.message || "Action failed");
    } finally {
      setBusy(false);
    }
  }

  function addToBasket(item) {
    const body = item.body || {};
    setBasket((prev) => {
      const idx = prev.findIndex((x) => x.menu_item_id === item.record_id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = { ...next[idx], qty: next[idx].qty + 1 };
        return next;
      }
      return [
        ...prev,
        {
          menu_item_id: item.record_id,
          name: body.name,
          qty: 1,
          unit_price_minor: body.price_minor || 0,
          discount_minor: 0,
        },
      ];
    });
  }

  async function checkout() {
    if (!basket.length) return;
    await run(async () => {
      const t = safeToken() || token;
      const orderRes = await hcgActions.createOrder(t, {
        lines: basket,
        channel: "dine_in",
        customer_id: payMethod === "CREDIT" ? creditCustomer : "",
        shift_id: activeShift?.record_id || "",
        idempotency_key: `pos-${Date.now()}`,
      });
      const order = orderRes.order;
      await hcgActions.submitKitchen(t, order.record_id);
      const payBody = {
        order_id: order.record_id,
        amount_minor: order.body.total_minor,
        method: payMethod,
        shift_id: activeShift?.record_id || "",
        customer_id: payMethod === "CREDIT" ? creditCustomer : "",
        qr_reference: payMethod === "QR" ? qrRef || `QR-DEMO-${Date.now()}` : "",
        idempotency_key: `pay-${order.record_id}`,
      };
      await hcgActions.payment(t, payBody);
      setBasket([]);
      setQrRef("");
      setStatusMsg(`Order ${order.body.token} paid via ${payMethod}`);
      setView("Orders");
    });
  }

  if (!token) {
    return (
      <main style={{ padding: 24, color: "#D7E2F5" }} aria-label="HCG Operations workspace">
        <h1>HCG Operations</h1>
        <p>Sign in required. Open Security to authenticate, then return here.</p>
        <Link href="/security">Go to Security</Link>
      </main>
    );
  }

  const m = dashboard?.metrics || {};

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "linear-gradient(160deg,#0B1220,#121C30)",
        color: "#E8EEF9",
        padding: "16px 16px 48px",
      }}
      aria-label="HCG Operations workspace"
    >
      <header style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", marginBottom: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22 }}>HCG Cafeteria Operations</h1>
          <p style={{ margin: "4px 0 0", color: "#8B98B4", fontSize: 13 }}>{HCG_NOTICE.data}</p>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link href="/apps" style={{ color: "#9EC1FF" }}>
            Application launcher
          </Link>
          <button type="button" style={btnGhost} onClick={() => refreshCore()} disabled={busy}>
            Refresh
          </button>
        </div>
      </header>

      <nav
        aria-label="HCG sections"
        style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}
      >
        {NAV.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setView(name)}
            style={{
              ...btnGhost,
              background: view === name ? "rgba(43,108,255,0.25)" : "transparent",
              borderColor: view === name ? "#2B6CFF" : "rgba(120,150,200,0.35)",
              minWidth: 72,
            }}
            aria-current={view === name ? "page" : undefined}
          >
            {name}
          </button>
        ))}
      </nav>

      <div aria-live="polite" style={{ minHeight: 22, color: error ? "#FF8A8A" : "#10C98A", marginBottom: 8 }}>
        {error || statusMsg}
      </div>

      {view === "Overview" && (
        <section style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))" }}>
          {[
            ["Sales today", formatPaisa(m.sales_today_minor)],
            ["Orders", m.order_count ?? "—"],
            ["Cash", formatPaisa(m.cash_received_minor)],
            ["QR", formatPaisa(m.qr_received_minor)],
            ["Credit sales", formatPaisa(m.credit_sales_minor)],
            ["Expenses", formatPaisa(m.expenses_minor)],
            ["Customer credit", formatPaisa(m.customer_credit_outstanding_minor)],
            ["Supplier dues", formatPaisa(m.supplier_dues_minor)],
            ["Low stock", m.low_stock_count ?? "—"],
            ["Kitchen tickets", m.active_kitchen_tickets ?? "—"],
            ["Open shifts", m.open_shift_count ?? "—"],
          ].map(([label, val]) => (
            <div key={label} style={card}>
              <div style={{ color: "#8B98B4", fontSize: 12 }}>{label}</div>
              <div style={{ fontSize: 20, fontWeight: 700, marginTop: 6 }}>{val}</div>
            </div>
          ))}
          <div style={{ ...card, gridColumn: "1 / -1" }}>
            <strong>Shift status:</strong>{" "}
            {activeShift
              ? `OPEN ${activeShift.record_id} — opening ${formatPaisa(activeShift.body?.opening_cash_minor)}`
              : "No open shift"}
            <div style={{ marginTop: 8, color: "#8B98B4", fontSize: 13 }}>
              Metrics derived from authoritative domain records. {HCG_NOTICE.money}.
            </div>
          </div>
        </section>
      )}

      {view === "POS" && (
        <section style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 320px" }}>
          <div style={card}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
              <button type="button" style={btnGhost} onClick={() => setCategoryFilter("")}>
                All
              </button>
              {(menu.categories || []).map((c) => (
                <button
                  key={c.record_id}
                  type="button"
                  style={btnGhost}
                  onClick={() => setCategoryFilter((c.body || {}).category_id || c.record_id)}
                >
                  {(c.body || {}).name}
                </button>
              ))}
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill,minmax(120px,1fr))",
                gap: 8,
              }}
            >
              {filteredMenu.map((item) => (
                <button
                  key={item.record_id}
                  type="button"
                  onClick={() => addToBasket(item)}
                  style={{
                    ...btnGhost,
                    minHeight: 72,
                    textAlign: "left",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                  }}
                  aria-label={`Add ${(item.body || {}).name}`}
                >
                  <span>{(item.body || {}).name}</span>
                  <span style={{ color: "#9EC1FF" }}>{formatPaisa((item.body || {}).price_minor)}</span>
                </button>
              ))}
            </div>
          </div>
          <div style={card}>
            <h2 style={{ marginTop: 0, fontSize: 16 }}>Order basket</h2>
            {basket.length === 0 && <p style={{ color: "#8B98B4" }}>Empty — tap menu items</p>}
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {basket.map((line) => (
                <li key={line.menu_item_id} style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                  <span>
                    {line.qty}× {line.name}
                  </span>
                  <span>{formatPaisa(line.qty * line.unit_price_minor)}</span>
                </li>
              ))}
            </ul>
            <div style={{ fontWeight: 700, margin: "12px 0" }}>Total {formatPaisa(basketTotal)}</div>
            <label style={{ display: "block", marginBottom: 8 }}>
              Payment
              <select
                value={payMethod}
                onChange={(e) => setPayMethod(e.target.value)}
                style={{ width: "100%", marginTop: 4, padding: 8, borderRadius: 8 }}
                aria-label="Payment method"
              >
                <option value="CASH">Cash</option>
                <option value="QR">QR (manual ref)</option>
                <option value="CREDIT">Customer credit</option>
              </select>
            </label>
            {payMethod === "QR" && (
              <label style={{ display: "block", marginBottom: 8 }}>
                QR reference
                <input
                  value={qrRef}
                  onChange={(e) => setQrRef(e.target.value)}
                  placeholder="Manual verified ref"
                  style={{ width: "100%", marginTop: 4, padding: 8, borderRadius: 8 }}
                  aria-label="QR payment reference"
                />
              </label>
            )}
            {payMethod === "CREDIT" && (
              <label style={{ display: "block", marginBottom: 8 }}>
                Customer
                <select
                  value={creditCustomer}
                  onChange={(e) => setCreditCustomer(e.target.value)}
                  style={{ width: "100%", marginTop: 4, padding: 8, borderRadius: 8 }}
                  aria-label="Credit customer"
                >
                  {customers.map((c) => (
                    <option key={c.record_id} value={c.record_id}>
                      {(c.body || {}).name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <p style={{ fontSize: 12, color: "#8B98B4" }}>{HCG_NOTICE.qr}</p>
            <button type="button" style={{ ...btn, width: "100%" }} disabled={busy || !basket.length} onClick={checkout}>
              Submit & pay
            </button>
          </div>
        </section>
      )}

      {view === "Orders" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Orders</h2>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "#8B98B4" }}>
                <th>Token</th>
                <th>Status</th>
                <th>Total</th>
                <th>Paid</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.record_id} style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                  <td>{(o.body || {}).token}</td>
                  <td>{o.status}</td>
                  <td>{formatPaisa((o.body || {}).total_minor)}</td>
                  <td>{formatPaisa((o.body || {}).paid_minor)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!orders.length && <p style={{ color: "#8B98B4" }}>No orders yet</p>}
        </section>
      )}

      {view === "Kitchen" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Kitchen queue</h2>
          <div style={{ display: "grid", gap: 8 }}>
            {kitchen.map((t) => (
              <div
                key={t.record_id}
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 8,
                  alignItems: "center",
                  borderTop: "1px solid rgba(255,255,255,0.06)",
                  paddingTop: 8,
                }}
              >
                <strong>{(t.body || {}).token}</strong>
                <span>
                  {(t.body || {}).qty}× {(t.body || {}).item_name}
                </span>
                <span style={{ color: "#9EC1FF" }}>{t.status}</span>
                {t.status === "QUEUED" && (
                  <button
                    type="button"
                    style={btn}
                    onClick={() =>
                      run(() => hcgActions.kitchenTransition(token, t.record_id, "PREPARING"))
                    }
                  >
                    Preparing
                  </button>
                )}
                {t.status === "PREPARING" && (
                  <button
                    type="button"
                    style={btn}
                    onClick={() =>
                      run(() => hcgActions.kitchenTransition(token, t.record_id, "READY"))
                    }
                  >
                    Ready
                  </button>
                )}
                {t.status === "READY" && (
                  <button
                    type="button"
                    style={btn}
                    onClick={() =>
                      run(() => hcgActions.kitchenTransition(token, t.record_id, "SERVED"))
                    }
                  >
                    Served
                  </button>
                )}
              </div>
            ))}
            {!kitchen.length && <p style={{ color: "#8B98B4" }}>No kitchen tickets</p>}
          </div>
        </section>
      )}

      {view === "Menu" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Menu</h2>
          <ul>
            {(menu.items || []).map((i) => (
              <li key={i.record_id}>
                {(i.body || {}).name} — {formatPaisa((i.body || {}).price_minor)}
                {(i.body || {}).favorite ? " ★" : ""}
                {(i.body || {}).available === false ? " (unavailable)" : ""}
              </li>
            ))}
          </ul>
        </section>
      )}

      {view === "Inventory" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Inventory</h2>
          <ul>
            {inventory.map((i) => {
              const b = i.body || {};
              const low = (b.qty_on_hand || 0) <= (b.min_qty || 0);
              return (
                <li key={i.record_id} style={{ color: low ? "#E8B84B" : undefined }}>
                  {b.name}: {b.qty_on_hand} {b.unit}
                  {low ? " — low stock" : ""}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {view === "Purchases" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Purchases</h2>
          <button
            type="button"
            style={btn}
            disabled={busy || !suppliers.length || !inventory.length}
            onClick={() =>
              run(async () => {
                const inv = inventory[0];
                await hcgActions.purchase(token, {
                  supplier_id: suppliers[0].record_id,
                  lines: [
                    {
                      inventory_item_id: inv.record_id,
                      name: inv.body?.name,
                      qty: 5,
                      unit_price_minor: 1000,
                      unit: inv.body?.unit || "unit",
                    },
                  ],
                  paid_minor: 2000,
                  credit_minor: 3000,
                  payment_method: "MIXED",
                });
                setStatusMsg("Purchase recorded (demo)");
              })
            }
          >
            Record demo purchase (part credit)
          </button>
        </section>
      )}

      {view === "Expenses" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Expenses</h2>
          <button
            type="button"
            style={btn}
            disabled={busy}
            onClick={() =>
              run(async () => {
                await hcgActions.expense(token, {
                  category: "supplies",
                  amount_minor: 5000,
                  description: "Demo operational expense",
                  payment_source: "CASH",
                  shift_id: activeShift?.record_id || "",
                });
                setStatusMsg("Expense recorded");
              })
            }
          >
            Record expense (50.00 NPR)
          </button>
          <ul style={{ marginTop: 12 }}>
            {expenses.map((e) => (
              <li key={e.record_id}>
                {(e.body || {}).category}: {formatPaisa((e.body || {}).amount_minor)} — {(e.body || {}).description}
              </li>
            ))}
          </ul>
        </section>
      )}

      {view === "Credit" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Customer credit</h2>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            <select
              value={creditCustomer}
              onChange={(e) => setCreditCustomer(e.target.value)}
              aria-label="Select customer"
              style={{ padding: 8, borderRadius: 8 }}
            >
              {customers.map((c) => (
                <option key={c.record_id} value={c.record_id}>
                  {(c.body || {}).name}
                </option>
              ))}
            </select>
            <button
              type="button"
              style={btn}
              onClick={() =>
                run(async () => {
                  const st = await hcgActions.customerStatement(token, creditCustomer);
                  setStatement(st);
                })
              }
            >
              Statement
            </button>
            <button
              type="button"
              style={btnGhost}
              onClick={() =>
                run(async () => {
                  await hcgActions.repay(token, {
                    customer_id: creditCustomer,
                    amount_minor: 10000,
                    method: "CASH",
                    shift_id: activeShift?.record_id || "",
                  });
                  setStatusMsg("Repayment recorded");
                  const st = await hcgActions.customerStatement(token, creditCustomer);
                  setStatement(st);
                })
              }
            >
              Repay 100 NPR
            </button>
          </div>
          {statement && (
            <div>
              <p>
                Balance: {formatPaisa(statement.balance_minor)} (ledger-backed:{" "}
                {String(statement.ledger_backed)})
              </p>
              <ul>
                {(statement.entries || []).map((e) => (
                  <li key={e.record_id}>
                    {(e.body || {}).entry_type}: {formatPaisa((e.body || {}).delta_minor)} — {(e.body || {}).note}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {view === "Suppliers" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Suppliers</h2>
          <ul>
            {suppliers.map((s) => (
              <li key={s.record_id}>
                {(s.body || {}).name}{" "}
                <button
                  type="button"
                  style={btnGhost}
                  onClick={() =>
                    run(async () => {
                      const st = await hcgActions.supplierStatement(token, s.record_id);
                      setStatement(st);
                      setStatusMsg(`Supplier balance ${formatPaisa(st.balance_minor)}`);
                    })
                  }
                >
                  Statement
                </button>
              </li>
            ))}
          </ul>
          {statement?.supplier && (
            <p>
              Outstanding: {formatPaisa(statement.balance_minor)} (ledger-backed)
            </p>
          )}
        </section>
      )}

      {view === "Shifts" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Shifts & cash reconciliation</h2>
          {!activeShift && (
            <button
              type="button"
              style={btn}
              onClick={() =>
                run(async () => {
                  await hcgActions.openShift(token, {
                    opening_cash_minor: 500000,
                    register_id: "reg-1",
                    idempotency_key: `shift-open-${Date.now()}`,
                  });
                  setStatusMsg("Shift opened with 5000.00 NPR");
                })
              }
            >
              Open shift (5000 NPR)
            </button>
          )}
          {activeShift && (
            <button
              type="button"
              style={btn}
              onClick={() =>
                run(async () => {
                  const opening = activeShift.body?.opening_cash_minor || 0;
                  const cashSales = m.cash_received_minor || 0;
                  const actual = opening + cashSales;
                  const res = await hcgActions.closeShift(token, activeShift.record_id, {
                    actual_cash_minor: actual,
                    explanation: actual === opening + cashSales ? "" : "variance note",
                  });
                  setStatusMsg(
                    `Shift closed — recon ${res.reconciliation?.status} diff ${res.reconciliation?.body?.difference_minor}`
                  );
                })
              }
            >
              Close shift (actual = expected)
            </button>
          )}
          <ul style={{ marginTop: 12 }}>
            {shifts.map((s) => (
              <li key={s.record_id}>
                {s.record_id} — {s.status} — open {formatPaisa(s.body?.opening_cash_minor)}
                {s.body?.difference_minor != null
                  ? ` — diff ${formatPaisa(s.body.difference_minor)}`
                  : ""}
              </li>
            ))}
          </ul>
        </section>
      )}

      {view === "Reports" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Reports & search</h2>
          <button
            type="button"
            style={btn}
            onClick={() =>
              run(async () => {
                const r = await hcgActions.reports(token);
                setReport(r.data || r.report?.body);
              })
            }
          >
            Daily sales report
          </button>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <input
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
              placeholder="Search orders, customers…"
              aria-label="Search HCG records"
              style={{ flex: 1, padding: 8, borderRadius: 8 }}
            />
            <button
              type="button"
              style={btnGhost}
              onClick={() =>
                run(async () => {
                  const r = await hcgActions.search(token, searchQ);
                  setSearchHits(r.results || []);
                })
              }
            >
              Search
            </button>
          </div>
          {report && (
            <pre style={{ overflow: "auto", fontSize: 12, background: "#0B1220", padding: 12, borderRadius: 8 }}>
              {JSON.stringify(report, null, 2)}
            </pre>
          )}
          {!!searchHits.length && (
            <ul>
              {searchHits.map((h) => (
                <li key={h.record_id}>
                  {h.record_type} {h.record_id} {h.status}
                </li>
              ))}
            </ul>
          )}
          <div style={{ marginTop: 16 }}>
            <h3 style={{ fontSize: 14 }}>Ask Yeti (grounded, read-only)</h3>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                value={yetiQ}
                onChange={(e) => setYetiQ(e.target.value)}
                aria-label="Yeti operational question"
                style={{ flex: 1, padding: 8, borderRadius: 8 }}
              />
              <button
                type="button"
                style={btn}
                onClick={() =>
                  run(async () => {
                    const a = await hcgActions.yeti(token, yetiQ);
                    setYetiA(a);
                  })
                }
              >
                Ask
              </button>
            </div>
            {yetiA && (
              <div style={{ marginTop: 8 }}>
                <p>{yetiA.answer}</p>
                <p style={{ fontSize: 12, color: "#8B98B4" }}>
                  mutable={String(yetiA.can_mutate)} · estimates={String(yetiA.estimates)}
                </p>
              </div>
            )}
          </div>
        </section>
      )}

      {view === "Notifications" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Notifications</h2>
          <ul>
            {notifications.map((n) => (
              <li key={n.notification_id || n.id || JSON.stringify(n).slice(0, 20)}>
                {n.title || n.type}: {n.summary}
              </li>
            ))}
          </ul>
          {!notifications.length && <p style={{ color: "#8B98B4" }}>No notifications</p>}
        </section>
      )}

      {view === "Settings" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Settings · backup · health</h2>
          <p style={{ color: "#8B98B4" }}>{HCG_NOTICE.production}</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              style={btn}
              onClick={() =>
                run(async () => {
                  const b = await hcgActions.backup(token);
                  setBackupPayload(b.backup);
                  setStatusMsg(`Backup hash ${b.backup?.content_hash?.slice(0, 12)}…`);
                })
              }
            >
              Create backup
            </button>
            <button
              type="button"
              style={btnGhost}
              disabled={!backupPayload}
              onClick={() =>
                run(async () => {
                  // Restore requires approval — expect APPROVAL_REQUIRED without one
                  try {
                    await hcgActions.restore(token, {
                      payload: backupPayload,
                      approval_reference: "",
                    });
                  } catch (e) {
                    setStatusMsg(`Restore gated: ${e.message || e.code || "approval required"}`);
                    throw e;
                  }
                })
              }
            >
              Restore (requires approval)
            </button>
            <button type="button" style={btnGhost} onClick={() => run(() => hcgActions.seed(token))}>
              Ensure seed data
            </button>
          </div>
          {dashboard && (
            <p style={{ marginTop: 12, fontSize: 13 }}>
              Schema {dashboard.schema_version} · instance {dashboard.app_instance_id}
            </p>
          )}
        </section>
      )}
    </main>
  );
}
