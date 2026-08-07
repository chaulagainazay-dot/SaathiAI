"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

/** M295 — Institutional Paper Trading Simulation Control Center.
 *  VIRTUAL EXCHANGE ONLY. NO BROKER. NO API KEYS. NO LIVE TRADING.
 */
export default function PaperSimulationPage() {
  const d = useAuthMe();
  const [dash, setDash] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [bootstrap, setBootstrap] = useState(null);
  const [exchange, setExchange] = useState(null);
  const [book, setBook] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [orders, setOrders] = useState(null);
  const [fills, setFills] = useState(null);
  const [cash, setCash] = useState(null);
  const [ks, setKs] = useState(null);
  const [calendar, setCalendar] = useState(null);
  const [brokerBlock, setBrokerBlock] = useState(null);
  const [credBlock, setCredBlock] = useState(null);
  const [realOrderBlock, setRealOrderBlock] = useState(null);
  const [liveBlock, setLiveBlock] = useState(null);
  const [error, setError] = useState(null);

  const load = async (path, setter, method = "GET", body = undefined) => {
    if (!d.token) return;
    setError(null);
    try {
      const opts = { token: d.token, method };
      if (body !== undefined) opts.body = body;
      setter(await plat(path, opts));
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  const afterBootstrap = async () => {
    if (!d.token) return;
    setError(null);
    try {
      const boot = await plat("/tg/paper-simulation/bootstrap", { token: d.token, method: "POST" });
      setBootstrap(boot);
      const pid = boot?.portfolio_id;
      setExchange(await plat("/tg/paper-simulation/exchange", { token: d.token }));
      setBook(await plat("/tg/paper-simulation/order-book/SPY", { token: d.token }));
      if (pid) {
        setPortfolio(await plat(`/tg/paper-simulation/portfolios/${pid}`, { token: d.token }));
        setOrders(await plat(`/tg/paper-simulation/portfolios/${pid}/orders`, { token: d.token }));
        setFills(await plat(`/tg/paper-simulation/portfolios/${pid}/fills`, { token: d.token }));
        setCash(await plat(`/tg/paper-simulation/portfolios/${pid}/cash`, { token: d.token }));
      }
      setKs(await plat("/tg/paper-simulation/kill-switch", { token: d.token }));
      setCalendar(await plat("/tg/paper-simulation/calendar", { token: d.token }));
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  return (
    <div className="page shell-page">
      <TradingHeader
        title="Institutional Paper Trading Simulation"
        subtitle="Virtual exchange, matching engine, ledger, risk and kill switch — no broker, no real orders."
      />
      <TradingTabs />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        <span className="mono" data-testid="paper-sim-only" style={pill("#5B8CFF")}>PAPER SIMULATION ONLY</span>
        <span className="mono" data-testid="virtual-exchange" style={pill("#5B8CFF")}>VIRTUAL EXCHANGE ONLY</span>
        <span className="mono" data-testid="no-broker" style={pill("#FF5A5A")}>NO BROKER CONNECTIVITY</span>
        <span className="mono" data-testid="no-real-routing" style={pill("#FF5A5A")}>NO REAL ORDER ROUTING</span>
        <span className="mono" data-testid="no-live-trading" style={pill("#FF5A5A")}>NO LIVE TRADING</span>
        <span className="mono" data-testid="no-api-keys" style={pill("#FF5A5A")}>NO API KEYS</span>
        <span className="mono" data-testid="no-guaranteed-profit" style={pill("#F5A623")}>NO GUARANTEED PROFITABILITY</span>
      </div>
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        {error && <LoadError message={error} />}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <Button data-testid="load-dashboard" onClick={() => load("/tg/paper-simulation/dashboard", setDash)}>Dashboard</Button>
          <Button data-testid="load-verdict" onClick={() => load("/tg/paper-simulation/verdict", setVerdict)}>Verdict</Button>
          <Button data-testid="run-bootstrap" onClick={afterBootstrap}>Bootstrap Simulation</Button>
          <Button data-testid="load-exchange" onClick={() => load("/tg/paper-simulation/exchange", setExchange)}>Exchange</Button>
          <Button data-testid="load-book" onClick={() => load("/tg/paper-simulation/order-book/SPY", setBook)}>Order Book</Button>
          <Button data-testid="load-kill-switch" onClick={() => load("/tg/paper-simulation/kill-switch", setKs)}>Kill Switch</Button>
          <Button data-testid="load-calendar" onClick={() => load("/tg/paper-simulation/calendar", setCalendar)}>Calendar</Button>
          <Button data-testid="refuse-broker" onClick={() => load("/tg/paper-simulation/broker/connect", setBrokerBlock, "POST")}>Probe Broker</Button>
          <Button data-testid="refuse-credentials" onClick={() => load("/tg/paper-simulation/credentials", setCredBlock, "POST", { api_key: "x" })}>Probe Creds</Button>
          <Button data-testid="refuse-real-orders" onClick={() => load("/tg/paper-simulation/real-orders", setRealOrderBlock, "POST")}>Probe Real Orders</Button>
          <Button data-testid="refuse-live" onClick={() => load("/tg/paper-simulation/live/activate", setLiveBlock, "POST")}>Probe Live</Button>
          <Button data-testid="run-certify" onClick={() => load("/tg/paper-simulation/certify", setVerdict, "POST")}>Certify</Button>
        </div>

        {dash && (
          <Card data-testid="dashboard-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Paper Portfolio Dashboard</Heading>
            <Text data-testid="dashboard-title">{dash.title}</Text>
            <Text className="mono" data-testid="exchange-name">{dash.exchange?.exchange}</Text>
            <Text className="mono" data-testid="authority-live-false">LIVE_TRADING_AUTHORIZED={String(dash.LIVE_TRADING_AUTHORIZED)}</Text>
            <Text className="mono" data-testid="real-exchange-false">REAL_EXCHANGE_AUTHORIZED={String(dash.REAL_EXCHANGE_AUTHORIZED)}</Text>
          </Card>
        )}
        {verdict && (
          <Card data-testid="verdict-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Certification</Heading>
            <Text className="mono" data-testid="verdict-value">{verdict.verdict}</Text>
            <Text className="mono" data-testid="max-state">{verdict.max_state}</Text>
          </Card>
        )}
        {bootstrap && (
          <Card data-testid="bootstrap-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Bootstrap Pipeline</Heading>
            <Text className="mono" data-testid="portfolio-id">Portfolio: {bootstrap.portfolio_id}</Text>
            <Text className="mono" data-testid="fill-count">Fills: {bootstrap.fill_count}</Text>
            <Text className="mono" data-testid="market-fill">Market fill: {String(bootstrap.market_fill)}</Text>
          </Card>
        )}
        {exchange && (
          <Card data-testid="exchange-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Virtual Exchange</Heading>
            <Text className="mono" data-testid="exchange-label">{exchange.exchange}</Text>
            <Text className="mono">real_exchange={String(exchange.real_exchange)}</Text>
            <pre className="mono" style={{ fontSize: 11 }}>{JSON.stringify(exchange.symbols, null, 2)}</pre>
          </Card>
        )}
        {book && (
          <Card data-testid="book-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Order Book Simulator</Heading>
            <Text className="mono" data-testid="book-symbol">{book.symbol}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 160 }}>{JSON.stringify({ bids: book.bids, asks: book.asks }, null, 2)}</pre>
          </Card>
        )}
        {portfolio && (
          <Card data-testid="portfolio-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Portfolio Ledger</Heading>
            <Text className="mono" data-testid="equity">Equity: {portfolio.metrics?.equity}</Text>
            <Text className="mono" data-testid="cash">Cash: {portfolio.metrics?.cash}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 160 }}>{JSON.stringify(portfolio.positions, null, 2)}</pre>
          </Card>
        )}
        {orders && (
          <Card data-testid="orders-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Orders</Heading>
            <Text className="mono" data-testid="orders-count">Count: {orders.count}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 160 }}>{JSON.stringify(orders.orders, null, 2)}</pre>
          </Card>
        )}
        {fills && (
          <Card data-testid="fills-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Fill Audit</Heading>
            <Text className="mono" data-testid="fills-count">Count: {fills.count}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 160 }}>{JSON.stringify(fills.fills, null, 2)}</pre>
          </Card>
        )}
        {cash && (
          <Card data-testid="cash-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Cash Ledger</Heading>
            <Text className="mono" data-testid="cash-count">Entries: {cash.count}</Text>
          </Card>
        )}
        {ks && (
          <Card data-testid="kill-switch-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Kill Switch / Risk Monitor</Heading>
            <Text className="mono" data-testid="ks-state">State: {ks.state}</Text>
            <Text className="mono" data-testid="ks-active">Active: {String(ks.active)}</Text>
          </Card>
        )}
        {calendar && (
          <Card data-testid="calendar-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Trading Calendar</Heading>
            <Text className="mono" data-testid="calendar-note">{calendar.note}</Text>
          </Card>
        )}
        {(brokerBlock || credBlock || realOrderBlock || liveBlock) && (
          <Card data-testid="refusal-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Boundary Refusals</Heading>
            <Text className="mono" data-testid="broker-refused">{brokerBlock && `broker=${brokerBlock.refused}`}</Text>
            <Text className="mono" data-testid="cred-refused">{credBlock && `creds=${credBlock.refused}`}</Text>
            <Text className="mono" data-testid="real-order-refused">{realOrderBlock && `real_orders=${realOrderBlock.refused}`}</Text>
            <Text className="mono" data-testid="live-refused">{liveBlock && `live=${liveBlock.refused}`}</Text>
          </Card>
        )}
      </SignInGate>
    </div>
  );
}

function pill(color) {
  return { border: `1px solid ${color}`, color, padding: "2px 8px", borderRadius: 4, fontSize: 11 };
}
