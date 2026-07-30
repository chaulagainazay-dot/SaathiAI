"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

/** M255 — Portfolio Command Center / Institutional Investment Intelligence.
 *  PAPER ONLY. NO BROKER CONNECTIVITY. NO API KEYS. NO LIVE TRADING.
 *  Analysis and planning only — no broker, credential, or connection controls.
 */
export default function IntelligenceCommandCenterPage() {
  const d = useAuthMe();
  const [dash, setDash] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [strategies, setStrategies] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [risk, setRisk] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [backtest, setBacktest] = useState(null);
  const [mc, setMc] = useState(null);
  const [wf, setWf] = useState(null);
  const [committee, setCommittee] = useState(null);
  const [explain, setExplain] = useState(null);
  const [decisions, setDecisions] = useState(null);
  const [conf, setConf] = useState(null);
  const [watch, setWatch] = useState(null);
  const [alerts, setAlerts] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [brokerBlock, setBrokerBlock] = useState(null);
  const [credBlock, setCredBlock] = useState(null);
  const [orderBlock, setOrderBlock] = useState(null);
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

  return (
    <div className="page shell-page">
      <TradingHeader
        title="Portfolio Command Center"
        subtitle="Institutional investment intelligence — paper portfolios, strategies, risk, simulations, and committee analysis only."
      />
      <TradingTabs />
      {/* Authority labels always visible — not behind sign-in (M255 boundary). */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        <span className="mono" data-testid="paper-only" style={pill("#5B8CFF")}>PAPER ONLY</span>
        <span className="mono" data-testid="no-broker" style={pill("#FF5A5A")}>NO BROKER CONNECTIVITY</span>
        <span className="mono" data-testid="no-api-keys" style={pill("#F5A623")}>NO API KEYS</span>
        <span className="mono" data-testid="no-live-market" style={pill("#F5A623")}>NO LIVE MARKET ACCESS</span>
        <span className="mono" data-testid="no-order-execution" style={pill("#FF5A5A")}>NO ORDER EXECUTION</span>
        <span className="mono" data-testid="no-live-trading" style={pill("#FF5A5A")}>NO LIVE TRADING</span>
      </div>
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <Button data-testid="load-dashboard" onClick={() => load("/tg/intelligence/dashboard", setDash)}>
            Command Center Overview
          </Button>
          <Button data-testid="load-verdict" onClick={() => load("/tg/intelligence/verdict", setVerdict)}>
            Certification Verdict
          </Button>
          <Button data-testid="load-strategies" onClick={() => load("/tg/intelligence/strategies", setStrategies)}>
            Strategy Library
          </Button>
          <Button data-testid="load-portfolio" onClick={() => load("/tg/intelligence/portfolio", setPortfolio)}>
            Portfolio Overview
          </Button>
          <Button data-testid="load-risk" onClick={() => load("/tg/intelligence/risk", setRisk)}>
            Risk Dashboard
          </Button>
          <Button data-testid="load-analytics" onClick={() => load("/tg/intelligence/analytics", setAnalytics)}>
            Performance Dashboard
          </Button>
          <Button data-testid="run-backtest" onClick={() => load("/tg/intelligence/backtests", setBacktest, "POST", { strategy_id: "tf_dual_ma", seed: 42 })}>
            Run Backtest
          </Button>
          <Button data-testid="run-monte-carlo" onClick={() => load("/tg/intelligence/simulations/monte-carlo", setMc, "POST", { n_simulations: 100, seed: 42 })}>
            Monte Carlo
          </Button>
          <Button data-testid="run-walk-forward" onClick={() => load("/tg/intelligence/simulations/walk-forward", setWf, "POST", { strategy_id: "tf_dual_ma", seed: 42 })}>
            Walk-Forward
          </Button>
          <Button data-testid="run-committee" onClick={() => load("/tg/intelligence/committee", setCommittee, "POST", { instrument: "SPY", context: { trend: "up", regime: "risk_on" } })}>
            Investment Committee
          </Button>
          <Button data-testid="run-explain" onClick={() => load("/tg/intelligence/explanations", setExplain, "POST", { instrument: "SPY", strategy_id: "tf_dual_ma" })}>
            Explainable Recommendation
          </Button>
          <Button data-testid="load-decisions" onClick={() => load("/tg/intelligence/decisions", setDecisions)}>
            Historical Decisions
          </Button>
          <Button data-testid="load-confidence" onClick={() => load("/tg/intelligence/confidence-trends", setConf)}>
            Confidence Trends
          </Button>
          <Button data-testid="load-watchlists" onClick={() => load("/tg/intelligence/watchlists", setWatch)}>
            Watchlists
          </Button>
          <Button data-testid="load-alerts" onClick={() => load("/tg/intelligence/alerts", setAlerts)}>
            Alerts
          </Button>
          <Button data-testid="load-timeline" onClick={() => load("/tg/intelligence/timeline", setTimeline)}>
            Decision Timeline
          </Button>
          <Button data-testid="try-broker" onClick={() => load("/tg/intelligence/broker/connect", setBrokerBlock, "POST")}>
            Try Broker Connect (must fail)
          </Button>
          <Button data-testid="try-credentials" onClick={() => load("/tg/intelligence/credentials", setCredBlock, "POST", { api_key: "should-reject" })}>
            Try Credentials (must fail)
          </Button>
          <Button data-testid="try-order" onClick={() => load("/tg/intelligence/orders", setOrderBlock, "POST")}>
            Try Order (must fail)
          </Button>
        </div>

        {error && <LoadError message={error} />}

        <Section title="Command Center" testid="panel-dashboard" data={dash} />
        <Section title="Verdict" testid="panel-verdict" data={verdict} />
        <Section title="Strategy Library" testid="panel-strategies" data={strategies} />
        <Section title="Portfolio Overview" testid="panel-portfolio" data={portfolio} />
        <Section title="Risk Dashboard" testid="panel-risk" data={risk} />
        <Section title="Performance / Analytics" testid="panel-analytics" data={analytics} />
        <Section title="Backtest" testid="panel-backtest" data={backtest} />
        <Section title="Monte Carlo" testid="panel-monte-carlo" data={mc} />
        <Section title="Walk-Forward" testid="panel-walk-forward" data={wf} />
        <Section title="Investment Committee" testid="panel-committee" data={committee} />
        <Section title="Explainable Recommendation" testid="panel-explain" data={explain} />
        <Section title="Historical Decisions" testid="panel-decisions" data={decisions} />
        <Section title="Confidence Trends" testid="panel-confidence" data={conf} />
        <Section title="Watchlists" testid="panel-watchlists" data={watch} />
        <Section title="Alerts" testid="panel-alerts" data={alerts} />
        <Section title="Decision Timeline" testid="panel-timeline" data={timeline} />
        <Section title="Broker Connect Refusal" testid="panel-broker-block" data={brokerBlock} />
        <Section title="Credentials Refusal" testid="panel-cred-block" data={credBlock} />
        <Section title="Order Refusal" testid="panel-order-block" data={orderBlock} />

        <Card style={{ marginTop: 16, padding: 16 }}>
          <Heading level={3}>Boundary</Heading>
          <Text>
            This surface is analysis-only. There are no broker connection controls,
            no credential entry forms, and no order tickets. Trading Guardian remains
            paper-only until a future, separately authorized milestone.
          </Text>
        </Card>
      </SignInGate>
    </div>
  );
}

function Section({ title, testid, data }) {
  if (!data) return null;
  return (
    <Card data-testid={testid} style={{ marginTop: 12, padding: 16 }}>
      <Heading level={3}>{title}</Heading>
      <pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: 12, overflow: "auto", maxHeight: 360 }}>
        {JSON.stringify(data, null, 2)}
      </pre>
    </Card>
  );
}

function pill(color) {
  return {
    display: "inline-block",
    padding: "4px 10px",
    borderRadius: 999,
    border: `1px solid ${color}`,
    color,
    fontSize: 11,
    letterSpacing: 0.4,
  };
}
