"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

/** M223 — Sandbox Control Center. SANDBOX ONLY. NO LIVE BROKER. */
export default function BrokerSandboxPage() {
  const d = useAuthMe();
  const [dash, setDash] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [brokers, setBrokers] = useState(null);
  const [caps, setCaps] = useState(null);
  const [security, setSecurity] = useState(null);
  const [audit, setAudit] = useState(null);
  const [error, setError] = useState(null);

  const load = async (path, setter, method = "GET") => {
    if (!d.token) return;
    setError(null);
    try {
      setter(await plat(path, { token: d.token, method }));
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  return (
    <div className="page shell-page">
      <TradingHeader
        title="Broker Sandbox Control Center"
        subtitle="Architecture for future broker integrations. Physically disconnected from every real exchange."
      />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="sandbox-only" style={pill("#5B8CFF")}>SANDBOX ONLY</span>
          <span className="mono" data-testid="no-live-broker" style={pill("#FF5A5A")}>NO LIVE BROKER</span>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER ONLY</span>
          <span className="mono" data-testid="no-api-credentials" style={pill("#F5A623")}>NO API CREDENTIALS</span>
          <span className="mono" data-testid="no-real-orders" style={pill("#FF5A5A")}>CANNOT EXECUTE REAL ORDERS</span>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <Button data-testid="load-dashboard" onClick={() => load("/tg/broker-sandbox/dashboard", setDash)}>
            Control Center
          </Button>
          <Button data-testid="load-verdict" onClick={() => load("/tg/broker-sandbox/verdict", setVerdict)}>
            Certification Verdict
          </Button>
          <Button data-testid="load-brokers" onClick={() => load("/tg/broker-sandbox/brokers", setBrokers)}>
            Broker Registry
          </Button>
          <Button data-testid="load-capabilities" onClick={() => load("/tg/broker-sandbox/capabilities", setCaps)}>
            Capability Viewer
          </Button>
          <Button data-testid="load-security" onClick={() => load("/tg/broker-sandbox/security/validate", setSecurity, "POST")}>
            Security Dashboard
          </Button>
          <Button data-testid="load-audit" onClick={() => load("/tg/broker-sandbox/audit", setAudit)}>
            Audit Timeline
          </Button>
        </div>
        {error ? <LoadError error={error} /> : null}

        {verdict ? (
          <Card style={{ marginTop: 12 }} data-testid="bs-verdict">
            <Heading level={2} size="md">Verdict · {verdict.verdict}</Heading>
            <Text mono size="sm">live_trading_authorized={String(verdict.live_trading_authorized)}</Text>
            <Text mono size="sm">broker_connections_exist={String(verdict.broker_connections_exist)}</Text>
            <Text mono size="sm">api_credentials_created={String(verdict.api_credentials_created)}</Text>
            <Text mono size="sm">sandbox_can_execute_real_orders={String(verdict.sandbox_can_execute_real_orders)}</Text>
            <ul className="mono" style={{ fontSize: 12 }} data-testid="bs-statements">
              {(verdict.statements || []).map((s) => <li key={s}>{s}</li>)}
            </ul>
          </Card>
        ) : null}

        {brokers ? (
          <Card style={{ marginTop: 12 }} data-testid="bs-broker-registry">
            <Heading level={2} size="md">Broker Registry · SANDBOX ONLY</Heading>
            <Text size="sm">All catalog brokers remain NOT_CONNECTED. Emulator is SANDBOX_ONLY.</Text>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 280, overflow: "auto" }}>
              {JSON.stringify(brokers.brokers || brokers, null, 2)}
            </pre>
          </Card>
        ) : null}

        {caps ? (
          <Card style={{ marginTop: 12 }} data-testid="bs-capability-viewer">
            <Heading level={2} size="md">Capability Viewer</Heading>
            <Text mono size="sm">
              connection_invariant.ok={String(caps.connection_invariant?.ok)}
            </Text>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 240, overflow: "auto" }}>
              {JSON.stringify(caps.capabilities || caps, null, 2)}
            </pre>
          </Card>
        ) : null}

        {dash ? (
          <Card style={{ marginTop: 12 }} data-testid="bs-dashboard">
            <Heading level={2} size="md">
              Control Center · {dash.labels?.sandbox_only} · {dash.labels?.no_live_broker}
            </Heading>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <section data-testid="trust-center">
                <Heading level={3} size="sm">Trust Center</Heading>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify(dash.trust_center || {}, null, 2)}
                </pre>
              </section>
              <section data-testid="approval-pipeline">
                <Heading level={3} size="sm">Approval Pipeline</Heading>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify(dash.approval_pipeline || {}, null, 2)}
                </pre>
              </section>
              <section data-testid="credential-metadata">
                <Heading level={3} size="sm">Credential Metadata</Heading>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify(dash.credential_metadata || {}, null, 2)}
                </pre>
              </section>
              <section data-testid="sandbox-emulator">
                <Heading level={3} size="sm">Sandbox Emulator</Heading>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify(dash.sandbox_emulator || {}, null, 2)}
                </pre>
              </section>
              <section data-testid="recovery-center">
                <Heading level={3} size="sm">Recovery Center</Heading>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify(dash.recovery_center || {}, null, 2)}
                </pre>
              </section>
              <section data-testid="security-dashboard">
                <Heading level={3} size="sm">Security Dashboard</Heading>
                <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
                  {JSON.stringify(dash.security_dashboard || {}, null, 2)}
                </pre>
              </section>
            </div>
            <Text mono size="sm" style={{ marginTop: 8 }} data-testid="bs-disclaimer">
              {dash.disclaimer}
            </Text>
          </Card>
        ) : null}

        {security ? (
          <Card style={{ marginTop: 12 }} data-testid="bs-security">
            <Heading level={2} size="md">
              Security Validation · all_passed={String(security.all_passed)}
            </Heading>
            <Text size="sm">{security.passed_count}/{security.total} checks passed</Text>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 280, overflow: "auto" }}>
              {JSON.stringify(security.checks || security, null, 2)}
            </pre>
          </Card>
        ) : null}

        {audit ? (
          <Card style={{ marginTop: 12 }} data-testid="bs-audit-timeline">
            <Heading level={2} size="md">Audit Timeline</Heading>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 240, overflow: "auto" }}>
              {JSON.stringify(audit.events || audit, null, 2)}
            </pre>
          </Card>
        ) : null}
      </SignInGate>
    </div>
  );
}

function pill(color) {
  return {
    fontSize: 11,
    letterSpacing: 0.5,
    border: `1px solid ${color}`,
    color,
    borderRadius: 6,
    padding: "2px 8px",
  };
}
