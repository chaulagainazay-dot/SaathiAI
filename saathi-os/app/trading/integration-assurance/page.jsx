"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

/** M239 — Reproducibility and Authorization Control Center.
 *  REPRODUCIBILITY AND PLANNING ONLY.
 *  NO REAL CONNECTIVITY. NO CREDENTIALS. NO PROVIDER ACCOUNT ACCESS.
 *  NO ORDER CAPABILITY. LIVE TRADING NOT AUTHORIZED.
 */
export default function IntegrationAssurancePage() {
  const d = useAuthMe();
  const [dash, setDash] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [source, setSource] = useState(null);
  const [env, setEnv] = useState(null);
  const [deps, setDeps] = useState(null);
  const [locks, setLocks] = useState(null);
  const [sbom, setSbom] = useState(null);
  const [prov, setProv] = useState(null);
  const [sc, setSc] = useState(null);
  const [gates, setGates] = useState(null);
  const [auth, setAuth] = useState(null);
  const [elig, setElig] = useState(null);
  const [net, setNet] = useState(null);
  const [sec, setSec] = useState(null);
  const [ownerBlock, setOwnerBlock] = useState(null);
  const [activateBlock, setActivateBlock] = useState(null);
  const [llm, setLlm] = useState(null);
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
        title="Integration Assurance Control Center"
        subtitle="Reproducibility, supply-chain assurance and read-only authorization planning only."
      />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="repro-planning-only" style={pill("#5B8CFF")}>REPRODUCIBILITY AND PLANNING ONLY</span>
          <span className="mono" data-testid="no-real-connectivity" style={pill("#FF5A5A")}>NO REAL CONNECTIVITY</span>
          <span className="mono" data-testid="no-credentials" style={pill("#F5A623")}>NO CREDENTIALS</span>
          <span className="mono" data-testid="no-provider-account" style={pill("#F5A623")}>NO PROVIDER ACCOUNT ACCESS</span>
          <span className="mono" data-testid="no-order-capability" style={pill("#FF5A5A")}>NO ORDER CAPABILITY</span>
          <span className="mono" data-testid="live-trading-not-authorized" style={pill("#FF5A5A")}>LIVE TRADING NOT AUTHORIZED</span>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <Button data-testid="load-dashboard" onClick={() => load("/tg/integration-assurance/dashboard", setDash)}>
            Reproducibility Overview
          </Button>
          <Button data-testid="load-verdict" onClick={() => load("/tg/integration-assurance/verdict", setVerdict)}>
            Certification Summary
          </Button>
          <Button data-testid="load-source-audit" onClick={() => load("/tg/integration-assurance/source-audit", setSource)}>
            Required Source Audit
          </Button>
          <Button data-testid="load-environment" onClick={() => load("/tg/integration-assurance/environment", setEnv)}>
            Environment Contract
          </Button>
          <Button data-testid="load-preflight" onClick={() => load("/tg/integration-assurance/environment/preflight", setEnv, "POST")}>
            Env Preflight
          </Button>
          <Button data-testid="load-dependencies" onClick={() => load("/tg/integration-assurance/dependencies", setDeps)}>
            Dependency Inventory
          </Button>
          <Button data-testid="load-lockfiles" onClick={() => load("/tg/integration-assurance/lockfiles", setLocks)}>
            Lockfile Status
          </Button>
          <Button data-testid="load-sbom" onClick={() => load("/tg/integration-assurance/sbom", setSbom)}>
            SBOM Viewer
          </Button>
          <Button data-testid="load-provenance" onClick={() => load("/tg/integration-assurance/provenance", setProv)}>
            Provenance Viewer
          </Button>
          <Button data-testid="load-supply-chain" onClick={() => load("/tg/integration-assurance/supply-chain", setSc)}>
            Supply-Chain Risks
          </Button>
          <Button data-testid="load-gates" onClick={() => load("/tg/integration-assurance/assurance-gates", setGates)}>
            Assurance Gates
          </Button>
          <Button data-testid="load-auth-plan" onClick={() => load("/tg/integration-assurance/authorization/plan", setAuth, "POST")}>
            Authorization Planning
          </Button>
          <Button data-testid="load-domains" onClick={() => load("/tg/integration-assurance/authorization/domains", setAuth)}>
            Approval Domains
          </Button>
          <Button data-testid="load-eligibility" onClick={() => load("/tg/integration-assurance/authorization/eligibility", setElig)}>
            Read-Only Eligibility
          </Button>
          <Button data-testid="load-network" onClick={() => load("/tg/integration-assurance/network-policy", setNet)}>
            Network Policy
          </Button>
          <Button data-testid="load-security" onClick={() => load("/tg/integration-assurance/security/scan", setSec, "POST")}>
            Security Scan
          </Button>
          <Button data-testid="owner-signoff-block" onClick={() => load("/tg/integration-assurance/authorization/owner-signoff-attempt", setOwnerBlock, "POST")}>
            Attempt Owner Sign-off (must fail)
          </Button>
          <Button data-testid="activate-block" onClick={() => load("/tg/integration-assurance/authorization/activate", setActivateBlock, "POST")}>
            Attempt Activate Connectivity (must fail)
          </Button>
          <Button data-testid="load-certify" onClick={() => load("/tg/integration-assurance/certify", setVerdict, "POST")}>
            Run Certification
          </Button>
          <Button
            data-testid="llm-refuse"
            onClick={() => load("/tg/integration-assurance/llm/refuse", setLlm, "POST", { action: "owner_signoff" })}
          >
            LLM Owner Sign-off (refuse)
          </Button>
          <Button data-testid="load-evidence" onClick={() => load("/tg/integration-assurance/evidence", setDash)}>
            Evidence Center
          </Button>
        </div>

        {error && <LoadError message={error} />}

        <div style={{ display: "grid", gap: 12 }}>
          <Card data-testid="panel-clean-clone">
            <Heading level={3}>Clean-Clone Status</Heading>
            <Text className="mono">See certification summary / reproduction evidence. No provider connectivity.</Text>
            <pre className="mono" style={pre}>{JSON.stringify({
              source_audit: source && { ok: source.ok, verdict: source.verdict, m216: source.m216_baseline?.resolution },
              REAL_CONNECTIVITY_AUTHORIZED: false,
            }, null, 2)}</pre>
          </Card>

          <Card data-testid="panel-hidden-deps">
            <Heading level={3}>Hidden Dependency Findings</Heading>
            <pre className="mono" style={pre}>{JSON.stringify(source?.items?.filter(i => !i.committed && i.required) || source?.m216_baseline || { empty: true }, null, 2)}</pre>
          </Card>

          <Card data-testid="panel-environment">
            <Heading level={3}>Environment Contract</Heading>
            <pre className="mono" style={pre}>{JSON.stringify(env, null, 2)}</pre>
          </Card>

          <Card data-testid="panel-dependencies">
            <Heading level={3}>Dependency Inventory / Lockfiles</Heading>
            <pre className="mono" style={pre}>{JSON.stringify({
              deps: deps && { count: deps.count, unpinned_count: deps.unpinned_count, ok: deps.ok },
              locks,
            }, null, 2)}</pre>
          </Card>

          <Card data-testid="panel-sbom">
            <Heading level={3}>SBOM / Provenance</Heading>
            <pre className="mono" style={pre}>{JSON.stringify({
              sbom: sbom && { format: sbom.format, fingerprint: sbom.fingerprint, signed: sbom.signed, components: sbom.component_count },
              provenance: prov && { count: prov.count, signed: prov.signed },
            }, null, 2)}</pre>
          </Card>

          <Card data-testid="panel-supply-chain">
            <Heading level={3}>Supply-Chain Risks & Assurance Gates</Heading>
            <pre className="mono" style={pre}>{JSON.stringify({
              threats: sc && { count: sc.count },
              gates: gates && { all_pass: gates.all_pass, passed: gates.passed, failed: gates.failed },
            }, null, 2)}</pre>
          </Card>

          <Card data-testid="panel-authorization">
            <Heading level={3}>Authorization Planning</Heading>
            <Text>Missing approvals prevent eligibility. Automation cannot create owner sign-off.</Text>
            <pre className="mono" style={pre}>{JSON.stringify({
              auth,
              eligibility: elig,
              owner_signoff_attempt: ownerBlock,
              activate_attempt: activateBlock,
              real_connectivity_authorized: false,
            }, null, 2)}</pre>
          </Card>

          <Card data-testid="panel-network">
            <Heading level={3}>Network Policy</Heading>
            <pre className="mono" style={pre}>{JSON.stringify(net || sec, null, 2)}</pre>
          </Card>

          <Card data-testid="panel-certification">
            <Heading level={3}>Certification Summary</Heading>
            <pre className="mono" style={pre}>{JSON.stringify(verdict || dash, null, 2)}</pre>
          </Card>

          <Card data-testid="panel-llm">
            <Heading level={3}>LLM Boundary</Heading>
            <pre className="mono" style={pre}>{JSON.stringify(llm, null, 2)}</pre>
          </Card>

          <Card>
            <Heading level={3}>UI Constraints (hard)</Heading>
            <Text data-testid="no-credential-form">CREDENTIAL FORM: NONE</Text>
            <Text data-testid="no-provider-activation">PROVIDER ACTIVATION ACTION: NONE</Text>
            <Text data-testid="no-oauth">OAUTH / PROVIDER LOGIN: NONE</Text>
            <Text data-testid="no-order-surface">ORDER CAPABILITY SURFACE: NONE</Text>
            <Text data-testid="real-connectivity-false">REAL_CONNECTIVITY_AUTHORIZED=false</Text>
          </Card>
        </div>
      </SignInGate>
    </div>
  );
}

function pill(color) {
  return {
    fontSize: 11, letterSpacing: 0.4, color,
    border: `1px solid ${color}`, borderRadius: 6, padding: "2px 8px",
  };
}

const pre = {
  fontSize: 11, maxHeight: 280, overflow: "auto",
  background: "var(--surface-2, #12151c)", padding: 10, borderRadius: 8,
};
