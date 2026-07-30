"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

/** M319 — Connectivity Governance Control Center.
 *  GOVERNANCE ONLY. NO PROVIDER CONNECTION. NO CREDENTIALS. NO OAUTH.
 *  NO ACCOUNT ACCESS. NO ORDERS. NO CANARY. NO LIVE TRADING.
 */
export default function ConnectivityGovernancePage() {
  const d = useAuthMe();
  const [dash, setDash] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [charter, setCharter] = useState(null);
  const [authorities, setAuthorities] = useState(null);
  const [providers, setProviders] = useState(null);
  const [approvals, setApprovals] = useState(null);
  const [credPolicy, setCredPolicy] = useState(null);
  const [threats, setThreats] = useState(null);
  const [risks, setRisks] = useState(null);
  const [incidents, setIncidents] = useState(null);
  const [emergency, setEmergency] = useState(null);
  const [maturity, setMaturity] = useState(null);
  const [bootstrap, setBootstrap] = useState(null);
  const [cert, setCert] = useState(null);
  const [refuseConnect, setRefuseConnect] = useState(null);
  const [refuseOAuth, setRefuseOAuth] = useState(null);
  const [refuseOrder, setRefuseOrder] = useState(null);
  const [refuseAccount, setRefuseAccount] = useState(null);
  const [refuseCanary, setRefuseCanary] = useState(null);
  const [refuseLive, setRefuseLive] = useState(null);
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

  const loadAll = async () => {
    if (!d.token) return;
    setError(null);
    try {
      setDash(await plat("/tg/connectivity-governance/dashboard", { token: d.token }));
      setVerdict(await plat("/tg/connectivity-governance/verdict", { token: d.token }));
      setCharter(await plat("/tg/connectivity-governance/charter", { token: d.token }));
      setAuthorities(await plat("/tg/connectivity-governance/authorities", { token: d.token }));
      setProviders(await plat("/tg/connectivity-governance/providers", { token: d.token }));
      setApprovals(await plat("/tg/connectivity-governance/approvals", { token: d.token }));
      setCredPolicy(await plat("/tg/connectivity-governance/credential-policy", { token: d.token }));
      setThreats(await plat("/tg/connectivity-governance/threat-model", { token: d.token }));
      setRisks(await plat("/tg/connectivity-governance/risk-summary", { token: d.token }));
      setIncidents(await plat("/tg/connectivity-governance/incidents", { token: d.token }));
      setEmergency(await plat("/tg/connectivity-governance/emergency-shutdown", { token: d.token }));
      setMaturity(await plat("/tg/connectivity-governance/maturity", { token: d.token }));
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  return (
    <div className="page shell-page" data-testid="connectivity-governance-page">
      <TradingHeader
        title="Connectivity Governance Control Center"
        subtitle="GOVERNANCE ONLY — NO PROVIDER CONNECTION"
      />
      <TradingTabs />
      <SafetyBanner />
      <SignInGate ready={d.ready} authed={!!d.token}>
        <div className="stack gap-4" style={{ padding: "1rem" }}>
          <Card data-testid="cg-banner">
            <Heading level={2}>GOVERNANCE ONLY</Heading>
            <Text>
              NO PROVIDER CONNECTION · NO CREDENTIALS · NO OAUTH · NO ACCOUNT ACCESS · NO ORDERS · NO CANARY ACTIVATION · NO LIVE TRADING
            </Text>
            <Text data-testid="cg-approval-note">APPROVAL DOES NOT EQUAL ACTIVATION</Text>
            <Text data-testid="cg-maturity-banner">Current maturity: GOVERNANCE_ONLY</Text>
          </Card>

          {error && <LoadError message={error} />}

          <Card>
            <Heading level={3}>Actions</Heading>
            <div className="row gap-2" style={{ flexWrap: "wrap", display: "flex", gap: 8 }}>
              <Button data-testid="cg-load" onClick={loadAll}>Load Governance</Button>
              <Button data-testid="cg-bootstrap" onClick={() => load("/tg/connectivity-governance/bootstrap", setBootstrap, "POST")}>Bootstrap Demo</Button>
              <Button data-testid="cg-certify" onClick={() => load("/tg/connectivity-governance/certify", setCert, "POST")}>Certify</Button>
              <Button data-testid="cg-emergency" onClick={() => load("/tg/connectivity-governance/emergency-shutdown", setEmergency, "POST", { actor: "ui_operator", reason: "ui_drill" })}>Emergency Shutdown</Button>
              <Button data-testid="cg-refuse-connect" onClick={() => load("/tg/connectivity-governance/connect", setRefuseConnect, "POST")}>Refuse Connect</Button>
              <Button data-testid="cg-refuse-oauth" onClick={() => load("/tg/connectivity-governance/oauth", setRefuseOAuth, "POST")}>Refuse OAuth</Button>
              <Button data-testid="cg-refuse-order" onClick={() => load("/tg/connectivity-governance/orders", setRefuseOrder, "POST")}>Refuse Order</Button>
              <Button data-testid="cg-refuse-account" onClick={() => load("/tg/connectivity-governance/accounts", setRefuseAccount, "POST")}>Refuse Account</Button>
              <Button data-testid="cg-refuse-canary" onClick={() => load("/tg/connectivity-governance/canary/activate", setRefuseCanary, "POST")}>Refuse Canary</Button>
              <Button data-testid="cg-refuse-live" onClick={() => load("/tg/connectivity-governance/live/activate", setRefuseLive, "POST")}>Refuse Live</Button>
            </div>
            {/* Explicitly NO secret-entry fields, no password, no api_key inputs */}
          </Card>

          <Card data-testid="cg-overview">
            <Heading level={3}>Governance Overview</Heading>
            <pre data-testid="cg-verdict-json">{JSON.stringify(verdict || dash?.verdict_target || null, null, 2)}</pre>
            <pre data-testid="cg-dashboard-json">{JSON.stringify(dash, null, 2)}</pre>
            {verdict && (
              <>
                <Text data-testid="cg-terminal-verdict">Verdict: {verdict.verdict}</Text>
                <Text data-testid="cg-max-state">Max state: {verdict.max_state}</Text>
                <Text data-testid="cg-maturity-value">Maturity: {verdict.current_maturity || maturity?.current}</Text>
              </>
            )}
          </Card>

          <Card data-testid="cg-charter-section">
            <Heading level={3}>Connectivity Charter</Heading>
            <pre data-testid="cg-charter-json">{JSON.stringify(charter && {
              version: charter.charter_version,
              principles: charter.principles,
              prohibited_operations: charter.prohibited_operations,
              human_accountability: charter.human_accountability,
            }, null, 2)}</pre>
          </Card>

          <Card data-testid="cg-authority-section">
            <Heading level={3}>Authority Matrix</Heading>
            <Text data-testid="cg-authority-locks">
              LIVE_TRADING_AUTHORIZED={String(authorities?.LIVE_TRADING_AUTHORIZED ?? false)} ·
              REAL_CONNECTIVITY_AUTHORIZED={String(authorities?.REAL_CONNECTIVITY_AUTHORIZED ?? false)} ·
              ORDER_SUBMISSION_AUTHORIZED={String(authorities?.ORDER_SUBMISSION_AUTHORIZED ?? false)} ·
              CANARY_ACTIVATION_AUTHORIZED={String(authorities?.CANARY_ACTIVATION_AUTHORIZED ?? false)} ·
              ACCOUNT_ACCESS_AUTHORIZED={String(authorities?.ACCOUNT_ACCESS_AUTHORIZED ?? false)} ·
              OAUTH_AUTHORIZED={String(authorities?.OAUTH_AUTHORIZED ?? false)}
            </Text>
            <pre data-testid="cg-authority-json">{JSON.stringify(authorities && {
              domains: authorities.domains,
              authority_does_not_implicitly_expand: authorities.authority_does_not_implicitly_expand,
              deny_overrides_allow: authorities.deny_overrides_allow,
              sample: (authorities.capabilities || []).slice(0, 8),
            }, null, 2)}</pre>
          </Card>

          <Card data-testid="cg-provider-section">
            <Heading level={3}>Provider Registry</Heading>
            <pre data-testid="cg-providers-json">{JSON.stringify(providers && {
              count: providers.count,
              any_connected: providers.any_connected,
              any_active: providers.any_active,
              providers: (providers.providers || []).map(p => ({
                id: p.provider_id,
                name: p.provider_name,
                status: p.governance_status,
                domains: p.official_domains,
                connected: p.connected,
              })),
            }, null, 2)}</pre>
          </Card>

          <Card data-testid="cg-approval-section">
            <Heading level={3}>Approval Center</Heading>
            <Text data-testid="cg-maker-checker">Maker-checker required · No self-approval · No LLM approval</Text>
            <Text data-testid="cg-approval-not-activation">approval_does_not_equal_activation=true</Text>
            <pre data-testid="cg-approvals-json">{JSON.stringify(approvals, null, 2)}</pre>
            <pre data-testid="cg-bootstrap-json">{JSON.stringify(bootstrap, null, 2)}</pre>
          </Card>

          <Card data-testid="cg-credential-section">
            <Heading level={3}>Credential Policy</Heading>
            <Text data-testid="cg-raw-secret-ban">raw_credentials_forbidden=true</Text>
            <pre data-testid="cg-credential-json">{JSON.stringify(credPolicy && {
              raw_credentials_forbidden: credPolicy.raw_credentials_forbidden,
              max_state: credPolicy.max_state_this_milestone,
              permitted_reference_backends: credPolicy.permitted_reference_backends,
              forbidden_fields: credPolicy.forbidden_fields,
            }, null, 2)}</pre>
          </Card>

          <Card data-testid="cg-threat-section">
            <Heading level={3}>Threat Model</Heading>
            <pre data-testid="cg-risks-json">{JSON.stringify(risks, null, 2)}</pre>
            <pre data-testid="cg-threats-json">{JSON.stringify(threats && {
              total: threats.total,
              critical_count: threats.critical_count,
              high_count: threats.high_count,
              unresolved_critical_count: threats.unresolved_critical_count,
            }, null, 2)}</pre>
          </Card>

          <Card data-testid="cg-incident-section">
            <Heading level={3}>Incident and Revocation</Heading>
            <pre data-testid="cg-incidents-json">{JSON.stringify(incidents, null, 2)}</pre>
            <pre data-testid="cg-emergency-json">{JSON.stringify(emergency, null, 2)}</pre>
          </Card>

          <Card data-testid="cg-maturity-section">
            <Heading level={3}>Maturity Model</Heading>
            <Text data-testid="cg-maturity-current">Current: {maturity?.current || "GOVERNANCE_ONLY"}</Text>
            <pre data-testid="cg-maturity-json">{JSON.stringify(maturity, null, 2)}</pre>
          </Card>

          <Card data-testid="cg-evidence-section">
            <Heading level={3}>Evidence Center</Heading>
            <pre data-testid="cg-cert-json">{JSON.stringify(cert, null, 2)}</pre>
            <pre data-testid="cg-refusals-json">{JSON.stringify({
              connect: refuseConnect,
              oauth: refuseOAuth,
              order: refuseOrder,
              account: refuseAccount,
              canary: refuseCanary,
              live: refuseLive,
            }, null, 2)}</pre>
          </Card>
        </div>
      </SignInGate>
    </div>
  );
}
