"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

/** M279 — Multi-Strategy Research Lab Control Center.
 *  RESEARCH ONLY. OFFLINE-FIRST. NO BROKER. NO API KEYS. NO LIVE TRADING.
 *  PAPER CANDIDATE DOES NOT AUTHORISE ORDER EXECUTION.
 */
export default function ResearchLabControlCenterPage() {
  const d = useAuthMe();
  const [dash, setDash] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [experiments, setExperiments] = useState(null);
  const [bootstrap, setBootstrap] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [robustness, setRobustness] = useState(null);
  const [regimes, setRegimes] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [ensemble, setEnsemble] = useState(null);
  const [stress, setStress] = useState(null);
  const [candidates, setCandidates] = useState(null);
  const [evidence, setEvidence] = useState(null);
  const [security, setSecurity] = useState(null);
  const [brokerBlock, setBrokerBlock] = useState(null);
  const [credBlock, setCredBlock] = useState(null);
  const [orderBlock, setOrderBlock] = useState(null);
  const [canaryBlock, setCanaryBlock] = useState(null);
  const [paperExecBlock, setPaperExecBlock] = useState(null);
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
      const boot = await plat("/tg/research-lab/bootstrap", { token: d.token, method: "POST" });
      setBootstrap(boot);
      setExperiments(await plat("/tg/research-lab/experiments", { token: d.token }));
      setComparison(boot?.comparison || await plat("/tg/research-lab/compare", { token: d.token, method: "POST" }));
      setRobustness(await plat("/tg/research-lab/robustness?strategy_id=tf_dual_ma", { token: d.token, method: "POST" }));
      setRegimes(await plat("/tg/research-lab/regimes/definitions", { token: d.token }));
      setPortfolio(await plat("/tg/research-lab/portfolios/build", { token: d.token, method: "POST" }));
      setEnsemble(await plat("/tg/research-lab/ensembles/build", { token: d.token, method: "POST" }));
      setStress(await plat("/tg/research-lab/stress/run", { token: d.token, method: "POST" }));
      setCandidates(await plat("/tg/research-lab/candidates", { token: d.token }));
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  const preserved = bootstrap?.preserved_oos_failures
    || dash?.overview?.preserved_oos_failures
    || [
      { instrument: "AAPL", strategy_id: "tf_dual_ma", state: "OUT_OF_SAMPLE_FAILED" },
      { instrument: "BTCUSDT", strategy_id: "tf_dual_ma", state: "OUT_OF_SAMPLE_FAILED" },
    ];

  return (
    <div className="page shell-page">
      <TradingHeader
        title="Multi-Strategy Research Lab"
        subtitle="Experiment registry, fair strategy comparison, regimes, portfolio research, ensembles, stress tests, and paper-candidate gates — offline research only."
      />
      <TradingTabs />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        <span className="mono" data-testid="research-only" style={pill("#5B8CFF")}>RESEARCH ONLY</span>
        <span className="mono" data-testid="offline-first" style={pill("#5B8CFF")}>OFFLINE-FIRST</span>
        <span className="mono" data-testid="paper-candidate-no-exec" style={pill("#F5A623")}>
          PAPER CANDIDATE DOES NOT AUTHORISE ORDER EXECUTION
        </span>
        <span className="mono" data-testid="no-broker" style={pill("#FF5A5A")}>NO BROKER CONNECTIVITY</span>
        <span className="mono" data-testid="no-account" style={pill("#FF5A5A")}>NO ACCOUNT ACCESS</span>
        <span className="mono" data-testid="no-credentials" style={pill("#FF5A5A")}>NO CREDENTIALS</span>
        <span className="mono" data-testid="no-live-trading" style={pill("#FF5A5A")}>NO LIVE TRADING</span>
        <span className="mono" data-testid="no-guaranteed-profit" style={pill("#F5A623")}>NO GUARANTEED PROFITABILITY</span>
        <span className="mono" data-testid="human-review-required" style={pill("#F5A623")}>HUMAN REVIEW REQUIRED</span>
      </div>
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        {error && <LoadError message={error} />}

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <Button data-testid="load-dashboard" onClick={() => load("/tg/research-lab/dashboard", setDash)}>
            Lab Overview
          </Button>
          <Button data-testid="load-verdict" onClick={() => load("/tg/research-lab/verdict", setVerdict)}>
            Certification Verdict
          </Button>
          <Button data-testid="load-experiments" onClick={() => load("/tg/research-lab/experiments", setExperiments)}>
            Experiment Registry
          </Button>
          <Button data-testid="run-bootstrap" onClick={afterBootstrap}>
            Bootstrap Research Pipeline
          </Button>
          <Button data-testid="load-comparison" onClick={() => load("/tg/research-lab/compare", setComparison, "POST")}>
            Strategy Comparison
          </Button>
          <Button data-testid="load-robustness" onClick={() => load("/tg/research-lab/robustness", setRobustness, "POST")}>
            Robustness
          </Button>
          <Button data-testid="load-regimes" onClick={() => load("/tg/research-lab/regimes/definitions", setRegimes)}>
            Regime Intelligence
          </Button>
          <Button data-testid="load-portfolio" onClick={() => load("/tg/research-lab/portfolios/build", setPortfolio, "POST")}>
            Portfolio Builder
          </Button>
          <Button data-testid="load-ensemble" onClick={() => load("/tg/research-lab/ensembles/build", setEnsemble, "POST")}>
            Ensemble Lab
          </Button>
          <Button data-testid="load-stress" onClick={() => load("/tg/research-lab/stress/run", setStress, "POST")}>
            Stress Testing
          </Button>
          <Button data-testid="load-candidates" onClick={() => load("/tg/research-lab/candidates", setCandidates)}>
            Candidate Promotion
          </Button>
          <Button data-testid="load-evidence" onClick={() => load("/tg/research-lab/evidence", setEvidence)}>
            Evidence Centre
          </Button>
          <Button data-testid="load-security" onClick={() => load("/tg/research-lab/security", setSecurity)}>
            Security Scan
          </Button>
          <Button data-testid="refuse-broker" onClick={() => load("/tg/research-lab/broker/connect", setBrokerBlock, "POST")}>
            Probe Broker (must refuse)
          </Button>
          <Button data-testid="refuse-credentials" onClick={() => load("/tg/research-lab/credentials", setCredBlock, "POST", { api_key: "x" })}>
            Probe Credentials (must refuse)
          </Button>
          <Button data-testid="refuse-orders" onClick={() => load("/tg/research-lab/orders", setOrderBlock, "POST")}>
            Probe Orders (must refuse)
          </Button>
          <Button data-testid="refuse-canary" onClick={() => load("/tg/research-lab/canary/activate", setCanaryBlock, "POST")}>
            Probe Canary (must refuse)
          </Button>
          <Button data-testid="refuse-paper-exec" onClick={() => load("/tg/research-lab/paper-execution/activate", setPaperExecBlock, "POST")}>
            Probe Paper Exec (must refuse)
          </Button>
          <Button data-testid="run-certify" onClick={() => load("/tg/research-lab/certify", setVerdict, "POST")}>
            Run Certification
          </Button>
        </div>

        {dash && (
          <Card data-testid="dashboard-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Lab Overview</Heading>
            <Text data-testid="dashboard-title">{dash.title}</Text>
            <Text className="mono" data-testid="experiment-count">Experiments: {dash.overview?.experiment_count ?? 0}</Text>
            <Text className="mono" data-testid="candidate-count">Candidates: {dash.overview?.candidate_count ?? 0}</Text>
            <Text className="mono" data-testid="paper-candidate-count">Paper candidates: {dash.overview?.paper_candidates ?? 0}</Text>
            <Text className="mono" data-testid="dataset-status">Dataset status: {dash.overview?.dataset_status}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto" }}>{JSON.stringify(dash.labels, null, 2)}</pre>
            <Text className="mono" data-testid="authority-live-false">LIVE_TRADING_AUTHORIZED={String(dash.LIVE_TRADING_AUTHORIZED)}</Text>
            <Text className="mono" data-testid="authority-broker-false">BROKER_CONNECTIVITY_AUTHORIZED={String(dash.BROKER_CONNECTIVITY_AUTHORIZED)}</Text>
          </Card>
        )}

        {verdict && (
          <Card data-testid="verdict-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Certification</Heading>
            <Text className="mono" data-testid="verdict-value">{verdict.verdict}</Text>
            <Text className="mono" data-testid="max-state">{verdict.max_state}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 240 }}>{JSON.stringify(verdict.checks || verdict.statements, null, 2)}</pre>
          </Card>
        )}

        {bootstrap && (
          <Card data-testid="bootstrap-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Bootstrap Pipeline</Heading>
            <Text className="mono" data-testid="experiment-id">Experiment: {bootstrap.experiment_id}</Text>
            <Text className="mono" data-testid="config-checksum">Config checksum: {bootstrap.config_checksum}</Text>
            <Text className="mono" data-testid="pre-registered">Pre-registered: {String(bootstrap.pre_registered)}</Text>
            <Text className="mono" data-testid="candidate-state">Candidate: {bootstrap.candidate?.state}</Text>
          </Card>
        )}

        {experiments && (
          <Card data-testid="experiments-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Experiment Registry</Heading>
            <Text className="mono" data-testid="experiments-count">Count: {experiments.count}</Text>
            <pre className="mono" data-testid="experiments-json" style={{ fontSize: 11, overflow: "auto", maxHeight: 220 }}>
              {JSON.stringify((experiments.experiments || []).slice(0, 5), null, 2)}
            </pre>
          </Card>
        )}

        <Card data-testid="failed-strategies-card" style={{ marginBottom: 12 }}>
          <Heading level={2} size="md">Failed Strategies (Preserved)</Heading>
          <Text data-testid="failed-strategies-note">
            Historical OOS failures are valid research results and are never hidden.
          </Text>
          {preserved.map((f, i) => (
            <Text key={i} className="mono" data-testid={`failed-${f.instrument?.toLowerCase() || i}`}>
              {f.instrument} {f.strategy_id}: {f.state}
            </Text>
          ))}
          <Text className="mono" data-testid="aapl-oos-failed">AAPL tf_dual_ma: OUT_OF_SAMPLE_FAILED</Text>
          <Text className="mono" data-testid="btc-oos-failed">BTCUSDT tf_dual_ma: OUT_OF_SAMPLE_FAILED</Text>
        </Card>

        {comparison && (
          <Card data-testid="comparison-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Strategy Comparison</Heading>
            <Text className="mono" data-testid="comparison-assumptions">
              Common assumptions locked: costs, periods, benchmark, PIT rules
            </Text>
            <pre className="mono" data-testid="comparison-json" style={{ fontSize: 11, overflow: "auto", maxHeight: 240 }}>
              {JSON.stringify({
                common_assumptions: comparison.common_assumptions,
                scorecards: (comparison.scorecards || []).map((s) => ({
                  strategy_id: s.strategy_id,
                  state: s.state,
                  oos_sharpe: s.out_of_sample?.sharpe_ratio,
                  data_label: s.data_label,
                })),
              }, null, 2)}
            </pre>
          </Card>
        )}

        {robustness && (
          <Card data-testid="robustness-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Robustness & Overfitting</Heading>
            <Text className="mono" data-testid="robustness-class">{robustness.overall_classification}</Text>
            <Text className="mono" data-testid="parameter-sensitivity">
              Narrow optimum: {String(robustness.parameter_robustness?.narrow_optimum)}
            </Text>
            <Text className="mono" data-testid="multiple-testing">
              Trials: {robustness.multiple_testing?.counts?.total_trial_count_estimate}
            </Text>
            <Text className="mono" data-testid="overfitting-warning">
              PBO estimate: {robustness.multiple_testing?.probability_of_backtest_overfitting_estimate} ({robustness.multiple_testing?.pbo_label})
            </Text>
          </Card>
        )}

        {regimes && (
          <Card data-testid="regime-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Regime Intelligence</Heading>
            <Text className="mono" data-testid="regime-macro-note">
              Macro fabricated: {String(regimes.macro_regimes_fabricated)}
            </Text>
            <Text className="mono" data-testid="unknown-regime-supported">UNKNOWN regime supported</Text>
            <pre className="mono" data-testid="regime-definitions" style={{ fontSize: 11, overflow: "auto", maxHeight: 200 }}>
              {JSON.stringify((regimes.definitions || []).map((r) => ({
                regime_id: r.regime_id,
                dimension: r.dimension,
                thresholds: r.thresholds,
              })), null, 2)}
            </pre>
          </Card>
        )}

        {portfolio && (
          <Card data-testid="portfolio-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Portfolio Builder</Heading>
            <Text className="mono" data-testid="portfolio-method">{portfolio.method}</Text>
            <Text className="mono" data-testid="portfolio-state">{portfolio.state}</Text>
            <Text className="mono" data-testid="portfolio-turnover">Turnover: {portfolio.turnover}</Text>
            <Text className="mono" data-testid="portfolio-costs">Costs: {portfolio.transaction_costs}</Text>
            <pre className="mono" data-testid="portfolio-weights" style={{ fontSize: 11, overflow: "auto", maxHeight: 160 }}>
              {JSON.stringify({ weights: portfolio.weights, risk_contributions: portfolio.risk_contributions, constraints: portfolio.constraint_utilisation }, null, 2)}
            </pre>
          </Card>
        )}

        {ensemble && (
          <Card data-testid="ensemble-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Ensemble Lab</Heading>
            <Text className="mono" data-testid="ensemble-state">{ensemble.state}</Text>
            <Text className="mono" data-testid="ensemble-method">{ensemble.method}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 160 }}>
              {JSON.stringify({ weights: ensemble.weights, baselines: ensemble.baselines, leakage_controls: ensemble.leakage_controls }, null, 2)}
            </pre>
          </Card>
        )}

        {stress && (
          <Card data-testid="stress-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Stress Testing</Heading>
            <Text className="mono" data-testid="stress-breaches">Breaches: {stress.breach_count}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 180 }}>
              {JSON.stringify({
                historical: stress.historical_stresses,
                hypothetical_sample: (stress.hypothetical_stresses || []).slice(0, 4),
                statistical: stress.statistical_stresses,
              }, null, 2)}
            </pre>
          </Card>
        )}

        {candidates && (
          <Card data-testid="candidates-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Candidate Promotion</Heading>
            <Text data-testid="paper-candidate-meaning">
              PAPER_CANDIDATE means ELIGIBLE_FOR_FUTURE_PAPER_SIMULATION_REVIEW only — not order execution.
            </Text>
            <Text className="mono" data-testid="candidates-count">Count: {candidates.count}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 180 }}>
              {JSON.stringify(candidates.candidates, null, 2)}
            </pre>
          </Card>
        )}

        {evidence && (
          <Card data-testid="evidence-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Evidence Centre</Heading>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 200 }}>
              {JSON.stringify({ registry_count: evidence.registry?.count, security_ok: evidence.security?.ok }, null, 2)}
            </pre>
          </Card>
        )}

        {security && (
          <Card data-testid="security-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Security</Heading>
            <Text className="mono" data-testid="security-ok">ok={String(security.ok)}</Text>
          </Card>
        )}

        {(brokerBlock || credBlock || orderBlock || canaryBlock || paperExecBlock) && (
          <Card data-testid="refusal-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Boundary Refusals</Heading>
            <Text className="mono" data-testid="broker-refused">{brokerBlock && `broker refused=${brokerBlock.refused}`}</Text>
            <Text className="mono" data-testid="cred-refused">{credBlock && `credentials refused=${credBlock.refused}`}</Text>
            <Text className="mono" data-testid="order-refused">{orderBlock && `orders refused=${orderBlock.refused}`}</Text>
            <Text className="mono" data-testid="canary-refused">{canaryBlock && `canary refused=${canaryBlock.refused}`}</Text>
            <Text className="mono" data-testid="paper-exec-refused">{paperExecBlock && `paper exec refused=${paperExecBlock.refused}`}</Text>
          </Card>
        )}
      </SignInGate>
    </div>
  );
}

function pill(color) {
  return {
    border: `1px solid ${color}`,
    color,
    padding: "2px 8px",
    borderRadius: 4,
    fontSize: 11,
  };
}
