"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

/** M303 — Institutional Portfolio & Risk Intelligence Control Center.
 *  PAPER/RESEARCH ONLY. NO BROKER. NO ORDERS. NO LIVE TRADING. NOT INVESTMENT ADVICE.
 */
export default function PortfolioRiskPage() {
  const d = useAuthMe();
  const [dash, setDash] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [bootstrap, setBootstrap] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [limits, setLimits] = useState(null);
  const [attr, setAttr] = useState(null);
  const [opt, setOpt] = useState(null);
  const [scenarios, setScenarios] = useState(null);
  const [committee, setCommittee] = useState(null);
  const [brokerBlock, setBrokerBlock] = useState(null);
  const [credBlock, setCredBlock] = useState(null);
  const [orderBlock, setOrderBlock] = useState(null);
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
      const boot = await plat("/tg/portfolio-risk/bootstrap", { token: d.token, method: "POST" });
      setBootstrap(boot);
      setAnalytics(boot?.analytics || await plat("/tg/portfolio-risk/analytics", { token: d.token }));
      setLimits(boot?.limits || await plat("/tg/portfolio-risk/limits", { token: d.token }));
      setAttr(boot?.attribution);
      setOpt(boot?.optimisation);
      setScenarios(boot?.scenarios);
      setCommittee(boot?.committee);
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  return (
    <div className="page shell-page">
      <TradingHeader
        title="Institutional Portfolio & Risk Intelligence"
        subtitle="Analytics, attribution, exposures, limits, optimiser V2, scenarios and committee V2 — paper research only."
      />
      <TradingTabs />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        <span className="mono" data-testid="research-only" style={pill("#5B8CFF")}>PAPER / RESEARCH ONLY</span>
        <span className="mono" data-testid="not-advice" style={pill("#F5A623")}>NOT INVESTMENT ADVICE</span>
        <span className="mono" data-testid="not-regulatory" style={pill("#F5A623")}>NOT REGULATORY-GRADE RISK</span>
        <span className="mono" data-testid="no-broker" style={pill("#FF5A5A")}>NO BROKER CONNECTIVITY</span>
        <span className="mono" data-testid="no-order-execution" style={pill("#FF5A5A")}>NO ORDER EXECUTION</span>
        <span className="mono" data-testid="no-live-trading" style={pill("#FF5A5A")}>NO LIVE TRADING</span>
        <span className="mono" data-testid="no-guaranteed-profit" style={pill("#F5A623")}>NO GUARANTEED PROFITABILITY</span>
      </div>
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        {error && <LoadError message={error} />}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <Button data-testid="load-dashboard" onClick={() => load("/tg/portfolio-risk/dashboard", setDash)}>Dashboard</Button>
          <Button data-testid="load-verdict" onClick={() => load("/tg/portfolio-risk/verdict", setVerdict)}>Verdict</Button>
          <Button data-testid="run-bootstrap" onClick={afterBootstrap}>Bootstrap Pipeline</Button>
          <Button data-testid="load-analytics" onClick={() => load("/tg/portfolio-risk/analytics", setAnalytics)}>Analytics</Button>
          <Button data-testid="load-limits" onClick={() => load("/tg/portfolio-risk/limits", setLimits)}>Limits</Button>
          <Button data-testid="load-attribution" onClick={() => load("/tg/portfolio-risk/attribution", setAttr)}>Attribution</Button>
          <Button data-testid="run-optimise" onClick={() => load("/tg/portfolio-risk/optimise", setOpt, "POST")}>Optimiser V2</Button>
          <Button data-testid="run-scenarios" onClick={() => load("/tg/portfolio-risk/scenarios", setScenarios, "POST")}>Scenarios</Button>
          <Button data-testid="run-committee" onClick={() => load("/tg/portfolio-risk/committee", setCommittee, "POST")}>Committee V2</Button>
          <Button data-testid="refuse-broker" onClick={() => load("/tg/portfolio-risk/broker/connect", setBrokerBlock, "POST")}>Probe Broker</Button>
          <Button data-testid="refuse-credentials" onClick={() => load("/tg/portfolio-risk/credentials", setCredBlock, "POST", { api_key: "x" })}>Probe Creds</Button>
          <Button data-testid="refuse-orders" onClick={() => load("/tg/portfolio-risk/orders", setOrderBlock, "POST")}>Probe Orders</Button>
          <Button data-testid="refuse-live" onClick={() => load("/tg/portfolio-risk/live/activate", setLiveBlock, "POST")}>Probe Live</Button>
          <Button data-testid="run-certify" onClick={() => load("/tg/portfolio-risk/certify", setVerdict, "POST")}>Certify</Button>
        </div>

        {dash && (
          <Card data-testid="dashboard-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Risk Overview</Heading>
            <Text data-testid="dashboard-title">{dash.title}</Text>
            <Text className="mono" data-testid="equity">Equity: {dash.overview?.equity}</Text>
            <Text className="mono" data-testid="var95">VaR 95: {dash.overview?.var_95}</Text>
            <Text className="mono" data-testid="es95">ES 95: {dash.overview?.es_95}</Text>
            <Text className="mono" data-testid="limits-state">Limits: {dash.overview?.limits_state}</Text>
            <Text className="mono" data-testid="committee-action">Committee: {dash.overview?.committee_action}</Text>
            <Text className="mono" data-testid="authority-live-false">LIVE_TRADING_AUTHORIZED={String(dash.LIVE_TRADING_AUTHORIZED)}</Text>
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
            <Heading level={2} size="md">Bootstrap</Heading>
            <Text className="mono" data-testid="bootstrap-ok">ok={String(bootstrap.ok)}</Text>
          </Card>
        )}
        {analytics && (
          <Card data-testid="analytics-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Portfolio Analytics</Heading>
            <Text className="mono" data-testid="portfolio-beta">Beta: {analytics.analytics?.portfolio_beta}</Text>
            <Text className="mono" data-testid="diversification">Diversification: {analytics.diversification?.ratio}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 140 }}>{JSON.stringify(analytics.factor_exposure, null, 2)}</pre>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 120 }}>{JSON.stringify(analytics.sector_exposure, null, 2)}</pre>
          </Card>
        )}
        {limits && (
          <Card data-testid="limits-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Exposure Limits / Drawdown Manager</Heading>
            <Text className="mono" data-testid="limits-state-value">{limits.state}</Text>
            <Text className="mono" data-testid="breach-count">Breaches: {(limits.breaches || []).length}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 140 }}>{JSON.stringify({ breaches: limits.breaches, risk_budgets: limits.risk_budgets }, null, 2)}</pre>
          </Card>
        )}
        {attr && (
          <Card data-testid="attribution-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Performance Attribution</Heading>
            <Text className="mono" data-testid="attr-method">{attr.method}</Text>
            <Text className="mono" data-testid="attr-label">{attr.label}</Text>
          </Card>
        )}
        {opt && (
          <Card data-testid="optimiser-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Portfolio Optimiser V2</Heading>
            <Text className="mono" data-testid="opt-state">{opt.state}</Text>
            <Text className="mono" data-testid="opt-method">{opt.method}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 140 }}>{JSON.stringify(opt.weights || opt.message, null, 2)}</pre>
          </Card>
        )}
        {scenarios && (
          <Card data-testid="scenarios-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Stress / Liquidity / ES Dashboards</Heading>
            <Text className="mono" data-testid="worst-scenario">
              Worst: {scenarios.stress_dashboard?.worst_scenario?.name} loss={scenarios.stress_dashboard?.worst_scenario?.portfolio_loss_pct}
            </Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 160 }}>
              {JSON.stringify({
                stress: (scenarios.stress_dashboard?.scenarios || []).slice(0, 3),
                liquidity: scenarios.liquidity_dashboard,
                es: scenarios.expected_shortfall_dashboard,
              }, null, 2)}
            </pre>
          </Card>
        )}
        {committee && (
          <Card data-testid="committee-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Investment Committee V2</Heading>
            <Text className="mono" data-testid="committee-rec">{committee.synthesis?.final_recommendation}</Text>
            <Text className="mono" data-testid="committee-consensus">{committee.synthesis?.consensus}</Text>
            <Text className="mono" data-testid="committee-no-exec">authorizes_execution={String(committee.authorizes_execution)}</Text>
          </Card>
        )}
        {(brokerBlock || credBlock || orderBlock || liveBlock) && (
          <Card data-testid="refusal-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Boundary Refusals</Heading>
            <Text className="mono" data-testid="broker-refused">{brokerBlock && `broker=${brokerBlock.refused}`}</Text>
            <Text className="mono" data-testid="cred-refused">{credBlock && `creds=${credBlock.refused}`}</Text>
            <Text className="mono" data-testid="order-refused">{orderBlock && `orders=${orderBlock.refused}`}</Text>
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
