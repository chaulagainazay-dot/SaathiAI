"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

/** M263 — Market Data & Research Validation Control Center.
 *  RESEARCH ONLY. OFFLINE-FIRST. NO BROKER. NO API KEYS. NO LIVE TRADING.
 *  Planning / research actions only — no broker, credential, or order controls.
 */
export default function ResearchDataControlCenterPage() {
  const d = useAuthMe();
  const [dash, setDash] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [datasets, setDatasets] = useState(null);
  const [features, setFeatures] = useState(null);
  const [bootstrap, setBootstrap] = useState(null);
  const [quality, setQuality] = useState(null);
  const [bias, setBias] = useState(null);
  const [validation, setValidation] = useState(null);
  const [evidence, setEvidence] = useState(null);
  const [security, setSecurity] = useState(null);
  const [brokerBlock, setBrokerBlock] = useState(null);
  const [credBlock, setCredBlock] = useState(null);
  const [orderBlock, setOrderBlock] = useState(null);
  const [canaryBlock, setCanaryBlock] = useState(null);
  const [provenance, setProvenance] = useState(null);
  const [licence, setLicence] = useState(null);
  const [ingestion, setIngestion] = useState(null);
  const [corpActions, setCorpActions] = useState(null);
  const [split, setSplit] = useState(null);
  const [lineage, setLineage] = useState(null);
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
      const boot = await plat("/tg/research-data/bootstrap", { token: d.token, method: "POST" });
      setBootstrap(boot);
      const id = boot?.dataset_id;
      const ver = boot?.dataset_version || "v1";
      if (id) {
        setDatasets(await plat("/tg/research-data/datasets", { token: d.token }));
        setProvenance(await plat(`/tg/research-data/datasets/${id}/provenance?version=${ver}`, { token: d.token }));
        setLicence(await plat(`/tg/research-data/datasets/${id}/licence?version=${ver}`, { token: d.token }));
        setIngestion(await plat(`/tg/research-data/datasets/${id}/ingestion-report`, { token: d.token }));
        setQuality(await plat(`/tg/research-data/datasets/${id}/quality-report?version=${ver}`, { token: d.token }));
        setCorpActions(await plat(`/tg/research-data/datasets/${id}/corporate-actions?version=${ver}`, { token: d.token }));
        setBias(await plat(`/tg/research-data/datasets/${id}/bias-check?version=${ver}`, { token: d.token, method: "POST" }));
        setSplit(await plat(`/tg/research-data/datasets/${id}/split?version=${ver}`, { token: d.token, method: "POST" }));
        setValidation(await plat(`/tg/research-data/datasets/${id}/validate`, {
          token: d.token, method: "POST", body: { strategy_id: "tf_dual_ma", version: ver },
        }));
        setLineage(await plat("/tg/research-data/features/sma_10/lineage", { token: d.token }));
      }
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  return (
    <div className="page shell-page">
      <TradingHeader
        title="Research Data Control Center"
        subtitle="Market-data foundation, dataset governance, and research-grade signal validation — offline research only."
      />
      <TradingTabs />
      {/* Authority labels always visible */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        <span className="mono" data-testid="research-only" style={pill("#5B8CFF")}>RESEARCH ONLY</span>
        <span className="mono" data-testid="offline-first" style={pill("#5B8CFF")}>OFFLINE-FIRST</span>
        <span className="mono" data-testid="no-broker" style={pill("#FF5A5A")}>NO BROKER CONNECTIVITY</span>
        <span className="mono" data-testid="no-account" style={pill("#FF5A5A")}>NO ACCOUNT ACCESS</span>
        <span className="mono" data-testid="no-order-execution" style={pill("#FF5A5A")}>NO ORDER EXECUTION</span>
        <span className="mono" data-testid="no-live-trading" style={pill("#FF5A5A")}>NO LIVE TRADING</span>
        <span className="mono" data-testid="no-guaranteed-profit" style={pill("#F5A623")}>NO GUARANTEED PROFITABILITY</span>
      </div>
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        {error && <LoadError message={error} />}

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <Button data-testid="load-dashboard" onClick={() => load("/tg/research-data/dashboard", setDash)}>
            Overview
          </Button>
          <Button data-testid="load-verdict" onClick={() => load("/tg/research-data/verdict", setVerdict)}>
            Certification Verdict
          </Button>
          <Button data-testid="load-datasets" onClick={() => load("/tg/research-data/datasets", setDatasets)}>
            Dataset Catalogue
          </Button>
          <Button data-testid="run-bootstrap" onClick={afterBootstrap}>
            Bootstrap Fixture Pipeline
          </Button>
          <Button data-testid="load-features" onClick={() => load("/tg/research-data/features", setFeatures)}>
            Feature Store
          </Button>
          <Button data-testid="load-evidence" onClick={() => load("/tg/research-data/evidence", setEvidence)}>
            Evidence Centre
          </Button>
          <Button data-testid="load-security" onClick={() => load("/tg/research-data/security", setSecurity)}>
            Security Scan
          </Button>
          <Button data-testid="refuse-broker" onClick={() => load("/tg/research-data/broker/connect", setBrokerBlock, "POST")}>
            Probe Broker (must refuse)
          </Button>
          <Button data-testid="refuse-credentials" onClick={() => load("/tg/research-data/credentials", setCredBlock, "POST", { api_key: "x" })}>
            Probe Credentials (must refuse)
          </Button>
          <Button data-testid="refuse-orders" onClick={() => load("/tg/research-data/orders", setOrderBlock, "POST")}>
            Probe Orders (must refuse)
          </Button>
          <Button data-testid="refuse-canary" onClick={() => load("/tg/research-data/canary/activate", setCanaryBlock, "POST")}>
            Probe Canary (must refuse)
          </Button>
          <Button data-testid="run-certify" onClick={() => load("/tg/research-data/certify", setVerdict, "POST")}>
            Run Certification
          </Button>
        </div>

        {dash && (
          <Card data-testid="dashboard-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Overview</Heading>
            <Text data-testid="dashboard-title">{dash.title}</Text>
            <Text className="mono" data-testid="dataset-count">Datasets: {dash.overview?.dataset_count ?? 0}</Text>
            <Text className="mono" data-testid="approved-count">Approved: {dash.overview?.approved_count ?? 0}</Text>
            <Text className="mono" data-testid="quarantined-count">Quarantined: {dash.overview?.quarantined_count ?? 0}</Text>
            <Text className="mono" data-testid="synthetic-count">Synthetic: {dash.overview?.synthetic_count ?? 0}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto" }}>{JSON.stringify(dash.labels, null, 2)}</pre>
          </Card>
        )}

        {verdict && (
          <Card data-testid="verdict-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Certification</Heading>
            <Text className="mono" data-testid="cert-verdict">{verdict.verdict || verdict.max_state}</Text>
            <Text data-testid="no-profit-claim">STRATEGY RESULTS DO NOT GUARANTEE FUTURE PERFORMANCE.</Text>
            <Text data-testid="no-live-claim">RESEARCH VALIDATION DOES NOT AUTHORIZE LIVE TRADING.</Text>
            <Text className="mono" data-testid="live-trading-false">LIVE_TRADING_AUTHORIZED={String(verdict.LIVE_TRADING_AUTHORIZED)}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 240 }}>{JSON.stringify(verdict, null, 2)}</pre>
          </Card>
        )}

        {datasets && (
          <Card data-testid="datasets-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Dataset Catalogue</Heading>
            <Text className="mono" data-testid="datasets-count">count={datasets.count}</Text>
            {(datasets.datasets || []).slice(0, 5).map((ds) => (
              <div key={`${ds.dataset_id}@${ds.dataset_version}`} data-testid="dataset-row" style={{ marginBottom: 8, borderBottom: "1px solid #222", paddingBottom: 6 }}>
                <Text className="mono" data-testid="dataset-id">{ds.dataset_id}</Text>
                <Text className="mono" data-testid="dataset-version">v={ds.dataset_version}</Text>
                <Text className="mono" data-testid="dataset-source">{ds.source_type} · {ds.provider}</Text>
                <Text className="mono" data-testid="dataset-checksum">checksum={ds.checksum?.slice(0, 16)}…</Text>
                <Text className="mono" data-testid="dataset-licence">licence={ds.licence_type}</Text>
                <Text className="mono" data-testid="dataset-quality">quality={ds.quality_status || "n/a"}</Text>
                <Text className="mono" data-testid="dataset-state">state={ds.state}</Text>
                {ds.is_synthetic && <Text className="mono" data-testid="synthetic-label">SYNTHETIC_TEST_DATA</Text>}
                <Text data-testid="dataset-limitations">{(ds.limitations || []).join("; ")}</Text>
              </div>
            ))}
          </Card>
        )}

        {bootstrap && (
          <Card data-testid="bootstrap-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Ingestion / Pipeline</Heading>
            <Text className="mono" data-testid="bootstrap-dataset">{bootstrap.dataset_id}@{bootstrap.dataset_version}</Text>
            <Text className="mono" data-testid="accepted-rows">accepted={bootstrap.ingestion?.accepted_row_count}</Text>
            <Text className="mono" data-testid="rejected-rows">rejected={bootstrap.ingestion?.rejected_row_count}</Text>
            <Text className="mono" data-testid="source-checksum">source_checksum={bootstrap.ingestion?.source_checksum?.slice(0, 16)}…</Text>
            {bootstrap.SYNTHETIC_TEST_DATA && <Text data-testid="pipeline-synthetic">SYNTHETIC_TEST_DATA</Text>}
            {bootstrap.REAL_HISTORICAL_DATA_VALIDATION_INCOMPLETE && (
              <Text data-testid="historical-incomplete">REAL_HISTORICAL_DATA_VALIDATION_INCOMPLETE</Text>
            )}
          </Card>
        )}

        {provenance && (
          <Card data-testid="provenance-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Provenance</Heading>
            <Text className="mono" data-testid="prov-publisher">{provenance.original_publisher}</Text>
            <Text className="mono" data-testid="prov-source">{provenance.source_location}</Text>
            <Text className="mono" data-testid="prov-hash">evidence_hash={provenance.evidence_hash?.slice(0, 16)}…</Text>
          </Card>
        )}

        {licence && (
          <Card data-testid="licence-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Licence</Heading>
            <Text className="mono" data-testid="licence-allowed">allowed={String(licence.allowed)}</Text>
            <Text className="mono" data-testid="licence-class">{licence.governance_class}</Text>
          </Card>
        )}

        {ingestion && (
          <Card data-testid="ingestion-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Ingestion Report</Heading>
            <Text className="mono" data-testid="ing-accepted">accepted={ingestion.accepted_row_count}</Text>
            <Text className="mono" data-testid="ing-rejected">rejected={ingestion.rejected_row_count}</Text>
            <Text className="mono" data-testid="ing-quarantined">quarantined={ingestion.quarantined_row_count}</Text>
            <Text className="mono" data-testid="ing-duplicates">duplicates={ingestion.duplicate_count}</Text>
          </Card>
        )}

        {quality && (
          <Card data-testid="quality-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Data Quality</Heading>
            <Text className="mono" data-testid="quality-class">{quality.classification}</Text>
            <Text className="mono" data-testid="blocking-defects">
              blocking={JSON.stringify(quality.blocking_defects || [])}
            </Text>
            <Text className="mono" data-testid="price-integrity">price={quality.price_integrity}</Text>
            <Text className="mono" data-testid="timestamp-integrity">timestamp={quality.timestamp_integrity}</Text>
            <Text className="mono" data-testid="volume-integrity">volume={quality.volume_integrity}</Text>
            <Text data-testid="raw-adjusted-note">Raw OHLC preserved; adjusted_close is separate.</Text>
          </Card>
        )}

        {corpActions && (
          <Card data-testid="corporate-actions-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Corporate Actions</Heading>
            <Text className="mono" data-testid="ca-count">count={corpActions.count}</Text>
            <Text className="mono" data-testid="raw-preserved">raw_prices_preserved={String(corpActions.raw_prices_preserved)}</Text>
          </Card>
        )}

        {bias && (
          <Card data-testid="bias-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Bias Controls</Heading>
            <Text className="mono" data-testid="lookahead-status">
              future_information_available={String(bias.invariants?.future_information_available)}
            </Text>
            <Text className="mono" data-testid="survivorship-status">
              survivorship_bias_unreported={String(bias.invariants?.survivorship_bias_unreported)}
            </Text>
            <Text className="mono" data-testid="leakage-status">
              train_test_leakage_detected={String(bias.invariants?.train_test_leakage_detected)}
            </Text>
          </Card>
        )}

        {split && (
          <Card data-testid="split-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Dataset Splits</Heading>
            <Text className="mono" data-testid="split-kind">{split.kind}</Text>
            <Text className="mono" data-testid="embargo-bars">embargo_bars={split.embargo_bars}</Text>
            <Text className="mono" data-testid="purge-bars">purge_bars={split.purge_bars}</Text>
            <Text className="mono" data-testid="train-count">train={split.train?.count}</Text>
            <Text className="mono" data-testid="test-count">test={split.test?.count}</Text>
          </Card>
        )}

        {features && (
          <Card data-testid="features-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Feature Store</Heading>
            <Text className="mono" data-testid="feature-count">count={features.count}</Text>
            {(features.features || []).slice(0, 6).map((f) => (
              <div key={`${f.feature_id}@${f.feature_version}`} data-testid="feature-row">
                <Text className="mono" data-testid="feature-id">{f.feature_id}@{f.feature_version}</Text>
                <Text className="mono" data-testid="feature-formula">{f.formula}</Text>
              </div>
            ))}
          </Card>
        )}

        {lineage && (
          <Card data-testid="lineage-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Feature Lineage</Heading>
            <Text className="mono" data-testid="lineage-feature">{lineage.feature_id}@{lineage.feature_version}</Text>
            <pre className="mono" style={{ fontSize: 11 }}>{JSON.stringify(lineage.lineage, null, 2)}</pre>
          </Card>
        )}

        {validation && (
          <Card data-testid="validation-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Signal Validation</Heading>
            <Text className="mono" data-testid="val-state">{validation.state || validation.confidence_classification}</Text>
            <Text className="mono" data-testid="val-oos">oos_trades={validation.out_of_sample?.n ?? validation.trade_count}</Text>
            <Text className="mono" data-testid="val-wf">walk_forward={JSON.stringify(validation.walk_forward?.optimized_on_evaluation_set)}</Text>
            <Text className="mono" data-testid="val-mc">mc_p_loss={validation.monte_carlo?.probability_of_loss}</Text>
            <Text className="mono" data-testid="val-regime">{validation.regime_analysis?.dominant}</Text>
            <Text className="mono" data-testid="val-costs">
              costs={validation.transaction_cost_assumptions?.commission_bps}bps /
              slip={validation.slippage_assumptions?.slippage_bps}bps
            </Text>
            {validation.is_synthetic && <Text data-testid="val-synthetic">SYNTHETIC_TEST_DATA</Text>}
            <Text data-testid="val-disclaimer">{validation.disclaimer}</Text>
          </Card>
        )}

        {evidence && (
          <Card data-testid="evidence-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Evidence Centre</Heading>
            <Text className="mono" data-testid="evidence-registry-count">
              registry={evidence.registry?.count}
            </Text>
            <Text className="mono" data-testid="evidence-security">{String(evidence.security?.ok)}</Text>
          </Card>
        )}

        {security && (
          <Card data-testid="security-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Security</Heading>
            <Text className="mono" data-testid="security-ok">ok={String(security.ok)}</Text>
          </Card>
        )}

        {brokerBlock && (
          <Card data-testid="broker-block-card" style={{ marginBottom: 12 }}>
            <Text className="mono" data-testid="broker-refused">broker_ok={String(brokerBlock.ok)} code={brokerBlock.code}</Text>
          </Card>
        )}
        {credBlock && (
          <Card data-testid="cred-block-card" style={{ marginBottom: 12 }}>
            <Text className="mono" data-testid="cred-refused">cred_ok={String(credBlock.ok)} accepted={String(credBlock.accepted)}</Text>
          </Card>
        )}
        {orderBlock && (
          <Card data-testid="order-block-card" style={{ marginBottom: 12 }}>
            <Text className="mono" data-testid="order-refused">order_ok={String(orderBlock.ok)} code={orderBlock.code}</Text>
          </Card>
        )}
        {canaryBlock && (
          <Card data-testid="canary-block-card" style={{ marginBottom: 12 }}>
            <Text className="mono" data-testid="canary-refused">canary_ok={String(canaryBlock.ok)} code={canaryBlock.code}</Text>
          </Card>
        )}
      </SignInGate>
    </div>
  );
}

function pill(color) {
  return {
    fontSize: 11,
    letterSpacing: 0.4,
    color,
    border: `1px solid ${color}`,
    borderRadius: 6,
    padding: "2px 8px",
  };
}
