"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

/** M311 — Read-Only Market Observation Control Center.
 *  VALIDATION — NOT TRADING. NO BROKER LOGIN. NO OAUTH. NO CREDENTIALS.
 *  NO ORDERS. NO ACCOUNT / PORTFOLIO / BALANCE ACCESS.
 */
export default function MarketObservationPage() {
  const d = useAuthMe();
  const [dash, setDash] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [bootstrap, setBootstrap] = useState(null);
  const [symbols, setSymbols] = useState(null);
  const [quotes, setQuotes] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [history, setHistory] = useState(null);
  const [exchanges, setExchanges] = useState(null);
  const [ca, setCa] = useState(null);
  const [benchmarks, setBenchmarks] = useState(null);
  const [brokerBlock, setBrokerBlock] = useState(null);
  const [oauthBlock, setOauthBlock] = useState(null);
  const [credBlock, setCredBlock] = useState(null);
  const [orderBlock, setOrderBlock] = useState(null);
  const [accountBlock, setAccountBlock] = useState(null);
  const [portfolioBlock, setPortfolioBlock] = useState(null);
  const [balanceBlock, setBalanceBlock] = useState(null);
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
      const boot = await plat("/tg/market-observation/bootstrap", { token: d.token, method: "POST" });
      setBootstrap(boot);
      setSymbols(await plat("/tg/market-observation/symbols", { token: d.token }));
      setQuotes(await plat("/tg/market-observation/quotes", { token: d.token }));
      setSnapshot(await plat("/tg/market-observation/snapshots", { token: d.token, method: "POST" }));
      setHistory(await plat("/tg/market-observation/history/SPY/refresh", { token: d.token, method: "POST" }));
      setExchanges(await plat("/tg/market-observation/exchanges", { token: d.token }));
      setCa(await plat("/tg/market-observation/corporate-actions?symbol=AAPL", { token: d.token }));
      setBenchmarks(await plat("/tg/market-observation/benchmarks/update", { token: d.token, method: "POST" }));
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  return (
    <div className="page shell-page">
      <TradingHeader
        title="Read-Only Market Observation"
        subtitle="Offline observation for validation — not trading. No broker login, OAuth, credentials, orders, or account access."
      />
      <TradingTabs />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        <span className="mono" data-testid="read-only" style={pill("#5B8CFF")}>READ-ONLY OBSERVATION</span>
        <span className="mono" data-testid="validation-not-trading" style={pill("#5B8CFF")}>VALIDATION — NOT TRADING</span>
        <span className="mono" data-testid="offline-first" style={pill("#5B8CFF")}>OFFLINE-FIRST</span>
        <span className="mono" data-testid="no-broker-login" style={pill("#FF5A5A")}>NO BROKER LOGIN</span>
        <span className="mono" data-testid="no-oauth" style={pill("#FF5A5A")}>NO OAUTH</span>
        <span className="mono" data-testid="no-credentials" style={pill("#FF5A5A")}>NO CREDENTIAL STORAGE</span>
        <span className="mono" data-testid="no-orders" style={pill("#FF5A5A")}>NO ORDERS</span>
        <span className="mono" data-testid="no-account" style={pill("#FF5A5A")}>NO ACCOUNT ACCESS</span>
        <span className="mono" data-testid="no-live-trading" style={pill("#FF5A5A")}>NO LIVE TRADING</span>
      </div>
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        {error && <LoadError message={error} />}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <Button data-testid="load-dashboard" onClick={() => load("/tg/market-observation/dashboard", setDash)}>Dashboard</Button>
          <Button data-testid="load-verdict" onClick={() => load("/tg/market-observation/verdict", setVerdict)}>Verdict</Button>
          <Button data-testid="run-bootstrap" onClick={afterBootstrap}>Bootstrap Observation</Button>
          <Button data-testid="load-symbols" onClick={() => load("/tg/market-observation/symbols", setSymbols)}>Symbols</Button>
          <Button data-testid="load-quotes" onClick={() => load("/tg/market-observation/quotes", setQuotes)}>Quotes</Button>
          <Button data-testid="load-snapshot" onClick={() => load("/tg/market-observation/snapshots", setSnapshot, "POST")}>Snapshot</Button>
          <Button data-testid="load-history" onClick={() => load("/tg/market-observation/history/SPY/refresh", setHistory, "POST")}>History Refresh</Button>
          <Button data-testid="load-exchanges" onClick={() => load("/tg/market-observation/exchanges", setExchanges)}>Exchanges</Button>
          <Button data-testid="load-ca" onClick={() => load("/tg/market-observation/corporate-actions?symbol=AAPL", setCa)}>Corp Actions</Button>
          <Button data-testid="load-benchmarks" onClick={() => load("/tg/market-observation/benchmarks/update", setBenchmarks, "POST")}>Benchmarks</Button>
          <Button data-testid="refuse-broker-login" onClick={() => load("/tg/market-observation/broker/login", setBrokerBlock, "POST")}>Probe Broker Login</Button>
          <Button data-testid="refuse-oauth" onClick={() => load("/tg/market-observation/oauth", setOauthBlock, "POST")}>Probe OAuth</Button>
          <Button data-testid="refuse-credentials" onClick={() => load("/tg/market-observation/credentials", setCredBlock, "POST", { api_key: "x" })}>Probe Creds</Button>
          <Button data-testid="refuse-orders" onClick={() => load("/tg/market-observation/orders", setOrderBlock, "POST")}>Probe Orders</Button>
          <Button data-testid="refuse-accounts" onClick={() => load("/tg/market-observation/accounts", setAccountBlock, "POST")}>Probe Accounts</Button>
          <Button data-testid="refuse-portfolios" onClick={() => load("/tg/market-observation/portfolios", setPortfolioBlock, "POST")}>Probe Portfolios</Button>
          <Button data-testid="refuse-balances" onClick={() => load("/tg/market-observation/balances", setBalanceBlock, "POST")}>Probe Balances</Button>
          <Button data-testid="refuse-live" onClick={() => load("/tg/market-observation/live/activate", setLiveBlock, "POST")}>Probe Live</Button>
          <Button data-testid="run-certify" onClick={() => load("/tg/market-observation/certify", setVerdict, "POST")}>Certify</Button>
        </div>

        {dash && (
          <Card data-testid="dashboard-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Observation Overview</Heading>
            <Text data-testid="dashboard-title">{dash.title}</Text>
            <Text className="mono" data-testid="symbol-count">Symbols: {dash.overview?.symbol_count}</Text>
            <Text className="mono" data-testid="quote-count">Quotes: {dash.overview?.quote_count}</Text>
            <Text className="mono" data-testid="auth-live-false">authenticated_live={String(dash.overview?.authenticated_live)}</Text>
            <Text className="mono" data-testid="purpose">{dash.overview?.purpose}</Text>
            <Text className="mono" data-testid="authority-live-false">LIVE_TRADING_AUTHORIZED={String(dash.LIVE_TRADING_AUTHORIZED)}</Text>
            <Text className="mono" data-testid="account-access-false">ACCOUNT_ACCESS_AUTHORIZED={String(dash.ACCOUNT_ACCESS_AUTHORIZED)}</Text>
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
            <Text className="mono" data-testid="snapshot-id">Snapshot: {bootstrap.snapshot_id}</Text>
            <Text className="mono" data-testid="history-bars">History bars: {bootstrap.history_bars}</Text>
          </Card>
        )}
        {symbols && (
          <Card data-testid="symbols-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Symbol Metadata</Heading>
            <Text className="mono" data-testid="symbols-count">Count: {symbols.count}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 140 }}>{JSON.stringify((symbols.symbols || []).slice(0, 4), null, 2)}</pre>
          </Card>
        )}
        {quotes && (
          <Card data-testid="quotes-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Read-Only Quotes</Heading>
            <Text className="mono" data-testid="quotes-count">Count: {quotes.count}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 140 }}>{JSON.stringify((quotes.quotes || []).slice(0, 3), null, 2)}</pre>
          </Card>
        )}
        {snapshot && (
          <Card data-testid="snapshot-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Market Snapshot</Heading>
            <Text className="mono" data-testid="snapshot-label">{snapshot.label}</Text>
            <Text className="mono" data-testid="snapshot-source">{snapshot.source}</Text>
          </Card>
        )}
        {history && (
          <Card data-testid="history-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Historical Refresh (Offline)</Heading>
            <Text className="mono" data-testid="history-symbol">{history.symbol}</Text>
            <Text className="mono" data-testid="history-count">Bars: {history.bar_count}</Text>
            <Text className="mono">authenticated_live={String(history.authenticated_live)}</Text>
          </Card>
        )}
        {exchanges && (
          <Card data-testid="exchanges-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Exchange Status</Heading>
            <pre className="mono" style={{ fontSize: 11 }}>{JSON.stringify(exchanges.exchanges, null, 2)}</pre>
          </Card>
        )}
        {ca && (
          <Card data-testid="ca-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Corporate Actions (Read-Only)</Heading>
            <Text className="mono" data-testid="ca-count">Count: {ca.count}</Text>
          </Card>
        )}
        {benchmarks && (
          <Card data-testid="benchmarks-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Benchmark Updates</Heading>
            <Text className="mono" data-testid="bm-count">Count: {benchmarks.count}</Text>
            <pre className="mono" style={{ fontSize: 11 }}>{JSON.stringify(benchmarks.benchmarks || benchmarks, null, 2)}</pre>
          </Card>
        )}
        {(brokerBlock || oauthBlock || credBlock || orderBlock || accountBlock || portfolioBlock || balanceBlock || liveBlock) && (
          <Card data-testid="refusal-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Boundary Refusals</Heading>
            <Text className="mono" data-testid="broker-refused">{brokerBlock && `broker_login=${brokerBlock.refused}`}</Text>
            <Text className="mono" data-testid="oauth-refused">{oauthBlock && `oauth=${oauthBlock.refused}`}</Text>
            <Text className="mono" data-testid="cred-refused">{credBlock && `creds=${credBlock.refused}`}</Text>
            <Text className="mono" data-testid="order-refused">{orderBlock && `orders=${orderBlock.refused}`}</Text>
            <Text className="mono" data-testid="account-refused">{accountBlock && `accounts=${accountBlock.refused}`}</Text>
            <Text className="mono" data-testid="portfolio-refused">{portfolioBlock && `portfolios=${portfolioBlock.refused}`}</Text>
            <Text className="mono" data-testid="balance-refused">{balanceBlock && `balances=${balanceBlock.refused}`}</Text>
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
