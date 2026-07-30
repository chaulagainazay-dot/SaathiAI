"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

/** M231 — Read-Only Broker Readiness Control Center.
 *  SIMULATION ONLY. NO REAL CONNECTION. NO REAL CREDENTIAL. NO ORDER SUBMISSION.
 */
export default function BrokerReadinessPage() {
  const d = useAuthMe();
  const [dash, setDash] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [providers, setProviders] = useState(null);
  const [adapters, setAdapters] = useState(null);
  const [caps, setCaps] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [creds, setCreds] = useState(null);
  const [scope, setScope] = useState(null);
  const [session, setSession] = useState(null);
  const [snap, setSnap] = useState(null);
  const [recon, setRecon] = useState(null);
  const [drill, setDrill] = useState(null);
  const [security, setSecurity] = useState(null);
  const [audit, setAudit] = useState(null);
  const [llm, setLlm] = useState(null);
  const [transport, setTransport] = useState(null);
  const [error, setError] = useState(null);
  // Secret input attempt — must be rejected client-side; never send secrets.
  const [secretAttempt, setSecretAttempt] = useState("");

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

  const rejectSecretInput = () => {
    if (!secretAttempt) return;
    // Never call API with secret-shaped content
    setError("SECRET_MATERIAL_REJECTED: UI does not accept raw secrets. Use credential references only.");
    setSecretAttempt("");
  };

  return (
    <div className="page shell-page">
      <TradingHeader
        title="Broker Readiness Control Center"
        subtitle="Read-only architecture readiness. Simulation only — no real broker connection."
      />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="simulation-only" style={pill("#5B8CFF")}>SIMULATION ONLY</span>
          <span className="mono" data-testid="no-real-connection" style={pill("#FF5A5A")}>NO REAL CONNECTION</span>
          <span className="mono" data-testid="no-real-credential" style={pill("#F5A623")}>NO REAL CREDENTIAL</span>
          <span className="mono" data-testid="read-only-architecture" style={pill("#10C98A")}>READ-ONLY ARCHITECTURE</span>
          <span className="mono" data-testid="no-order-submission" style={pill("#FF5A5A")}>NO ORDER SUBMISSION</span>
          <span className="mono" data-testid="live-trading-not-authorized" style={pill("#FF5A5A")}>LIVE TRADING NOT AUTHORIZED</span>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <Button data-testid="load-dashboard" onClick={() => load("/tg/broker-readiness/dashboard", setDash)}>
            Readiness Overview
          </Button>
          <Button data-testid="load-verdict" onClick={() => load("/tg/broker-readiness/verdict", setVerdict)}>
            Certification
          </Button>
          <Button data-testid="load-providers" onClick={() => load("/tg/broker-readiness/providers", setProviders)}>
            Providers
          </Button>
          <Button data-testid="load-adapters" onClick={() => load("/tg/broker-readiness/adapters", setAdapters)}>
            Adapter Contracts
          </Button>
          <Button data-testid="load-capabilities" onClick={() => load("/tg/broker-readiness/capabilities", setCaps)}>
            Capabilities
          </Button>
          <Button
            data-testid="load-policy-read"
            onClick={() => load("/tg/broker-readiness/policy/evaluate", setPolicy, "POST", {
              operation: "balances", scopes: ["BALANCE_READ"], environment: "SIMULATION",
            })}
          >
            Policy (read)
          </Button>
          <Button
            data-testid="load-policy-write"
            onClick={() => load("/tg/broker-readiness/policy/evaluate", setPolicy, "POST", {
              operation: "place_order", scopes: ["ORDER_CREATE"], trading_permission: true,
            })}
          >
            Policy (write deny)
          </Button>
          <Button
            data-testid="load-scope-write"
            onClick={() => load("/tg/broker-readiness/scope/validate", setScope, "POST", {
              requested: ["BALANCE_READ", "ORDER_CREATE"],
              declared: ["BALANCE_READ", "ORDER_CREATE"],
              approved: ["BALANCE_READ", "ORDER_CREATE"],
            })}
          >
            Scope (mixed reject)
          </Button>
          <Button
            data-testid="propose-credential"
            onClick={() => load("/tg/broker-readiness/credentials", setCreds, "POST", {
              provider_id: "sim.readonly.fixture",
              declared_scopes: ["ACCOUNT_METADATA_READ", "BALANCE_READ", "POSITION_READ"],
              environment: "SIMULATION",
              metadata: { label: "sim-ref-ui" },
            })}
          >
            Propose Credential Ref
          </Button>
          <Button
            data-testid="simulate-session"
            onClick={async () => {
              if (!d.token) return;
              try {
                const created = await plat("/tg/broker-readiness/sessions", {
                  token: d.token, method: "POST",
                });
                const sid = created?.session?.id;
                if (sid) {
                  setSession(await plat(`/tg/broker-readiness/sessions/${sid}/simulate`, {
                    token: d.token, method: "POST",
                  }));
                } else setSession(created);
              } catch (e) {
                setError(e?.message || String(e));
              }
            }}
          >
            Simulate Connection
          </Button>
          <Button
            data-testid="real-connection-forbidden"
            onClick={() => load("/tg/broker-readiness/transport/probe", setTransport, "POST", {
              url: "https://api.binance.com/api/v3/account",
            })}
          >
            Real Connection (must fail)
          </Button>
          <Button data-testid="load-snapshot" onClick={() => load("/tg/broker-readiness/snapshots/load", setSnap, "POST")}>
            Account Snapshot
          </Button>
          <Button data-testid="load-expiry" onClick={() => load("/tg/broker-readiness/drills/expiry", setDrill, "POST")}>
            Expiry Drill
          </Button>
          <Button data-testid="load-revocation" onClick={() => load("/tg/broker-readiness/drills/revocation", setDrill, "POST")}>
            Revocation Drill
          </Button>
          <Button data-testid="load-security" onClick={() => load("/tg/broker-readiness/security/scan", setSecurity, "POST")}>
            Security Scan
          </Button>
          <Button data-testid="load-audit" onClick={() => load("/tg/broker-readiness/audit", setAudit)}>
            Audit Timeline
          </Button>
          <Button data-testid="load-certify" onClick={() => load("/tg/broker-readiness/certify", setVerdict, "POST")}>
            Certify
          </Button>
          <Button
            data-testid="llm-approve-refuse"
            onClick={() => load("/tg/broker-readiness/llm/refuse", setLlm, "POST", {
              action: "approve_credentials",
            })}
          >
            LLM Approve (must refuse)
          </Button>
          <Button
            data-testid="llm-connect-refuse"
            onClick={() => load("/tg/broker-readiness/llm/refuse", setLlm, "POST", {
              action: "connect_brokers",
            })}
          >
            LLM Connect (must refuse)
          </Button>
          <Button
            data-testid="llm-trade-refuse"
            onClick={() => load("/tg/broker-readiness/llm/refuse", setLlm, "POST", {
              action: "authorize_live_trading",
            })}
          >
            LLM Live Trade (must refuse)
          </Button>
        </div>

        {/* No secret form — attempt field only demonstrates rejection */}
        <Card style={{ marginBottom: 12 }} data-testid="secret-reject-panel">
          <Heading level={3} size="sm">Secret Entry (Rejected)</Heading>
          <Text size="sm">No UI workflow accepts raw API keys, secrets, or tokens.</Text>
          <input
            data-testid="secret-input-attempt"
            type="password"
            placeholder="Do not enter real secrets"
            value={secretAttempt}
            onChange={(e) => setSecretAttempt(e.target.value)}
            style={{ marginRight: 8, padding: 6 }}
          />
          <Button data-testid="secret-submit-attempt" onClick={rejectSecretInput}>
            Attempt Submit (Rejected)
          </Button>
          {/* Explicitly no order submission surface */}
          <div data-testid="no-order-surface" style={{ marginTop: 8 }}>
            <Text mono size="sm">ORDER SUBMISSION SURFACE: NONE</Text>
            <Text mono size="sm">ENABLE TRADING BUTTON: NONE</Text>
            <Text mono size="sm">REAL CONNECTION BUTTON: FORBIDDEN ONLY</Text>
          </div>
        </Card>

        {error ? <LoadError error={error} /> : null}

        {verdict ? (
          <Card style={{ marginTop: 12 }} data-testid="br-verdict">
            <Heading level={2} size="md">Readiness Certification · {verdict.verdict}</Heading>
            <Text mono size="sm">live_trading_authorized={String(verdict.live_trading_authorized)}</Text>
            <Text mono size="sm">simulation_only={String(verdict.simulation_only)}</Text>
            <ul className="mono" style={{ fontSize: 12 }} data-testid="br-statements">
              {(verdict.statements || []).map((s) => <li key={s}>{s}</li>)}
            </ul>
          </Card>
        ) : null}

        {providers ? (
          <Card style={{ marginTop: 12 }} data-testid="br-providers">
            <Heading level={2} size="md">Providers · SIMULATED_NOT_CONNECTED</Heading>
            <Text mono size="sm">
              all_simulated_not_connected={String(providers.all_simulated_not_connected)}
            </Text>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 200, overflow: "auto" }}>
              {JSON.stringify(providers.providers || providers, null, 2)}
            </pre>
          </Card>
        ) : null}

        {adapters ? (
          <Card style={{ marginTop: 12 }} data-testid="br-adapters">
            <Heading level={2} size="md">Provider Adapter Contracts</Heading>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 200, overflow: "auto" }}>
              {JSON.stringify(adapters, null, 2)}
            </pre>
          </Card>
        ) : null}

        {caps ? (
          <Card style={{ marginTop: 12 }} data-testid="br-capabilities">
            <Heading level={2} size="md">Capability Policy · Read vs Write</Heading>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 220, overflow: "auto" }}>
              {JSON.stringify(caps, null, 2)}
            </pre>
          </Card>
        ) : null}

        {policy ? (
          <Card style={{ marginTop: 12 }} data-testid="br-policy">
            <Heading level={2} size="md">Capability Policy Result</Heading>
            <Text mono size="sm" data-testid="policy-decision">decision={policy.decision}</Text>
            <Text mono size="sm">allowed={String(policy.allowed)}</Text>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
              {JSON.stringify(policy, null, 2)}
            </pre>
          </Card>
        ) : null}

        {scope ? (
          <Card style={{ marginTop: 12 }} data-testid="br-scope">
            <Heading level={2} size="md">Scope Validator</Heading>
            <Text mono size="sm" data-testid="scope-outcome">outcome={scope.outcome}</Text>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
              {JSON.stringify(scope, null, 2)}
            </pre>
          </Card>
        ) : null}

        {creds ? (
          <Card style={{ marginTop: 12 }} data-testid="br-credentials">
            <Heading level={2} size="md">Credential Lifecycle (metadata only)</Heading>
            <Text mono size="sm">
              usable_for_real={String(
                creds.credential?.credential_usable_for_real_connection
                ?? creds.credential_usable_for_real_connection
                ?? false
              )}
            </Text>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 200, overflow: "auto" }}>
              {JSON.stringify(creds, null, 2)}
            </pre>
          </Card>
        ) : null}

        {session ? (
          <Card style={{ marginTop: 12 }} data-testid="br-session">
            <Heading level={2} size="md">Connection State</Heading>
            <Text mono size="sm" data-testid="session-state">
              state={session.session?.state || session.state}
            </Text>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
              {JSON.stringify(session, null, 2)}
            </pre>
          </Card>
        ) : null}

        {transport ? (
          <Card style={{ marginTop: 12 }} data-testid="br-transport">
            <Heading level={2} size="md">Network Isolation</Heading>
            <Text mono size="sm" data-testid="transport-result">result={transport.result}</Text>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 120, overflow: "auto" }}>
              {JSON.stringify(transport, null, 2)}
            </pre>
          </Card>
        ) : null}

        {snap ? (
          <Card style={{ marginTop: 12 }} data-testid="br-snapshot">
            <Heading level={2} size="md">Account Snapshot Viewer</Heading>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 200, overflow: "auto" }}>
              {JSON.stringify(snap, null, 2)}
            </pre>
          </Card>
        ) : null}

        {recon ? (
          <Card style={{ marginTop: 12 }} data-testid="br-recon">
            <Heading level={2} size="md">Reconciliation Center</Heading>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 160, overflow: "auto" }}>
              {JSON.stringify(recon, null, 2)}
            </pre>
          </Card>
        ) : null}

        {drill ? (
          <Card style={{ marginTop: 12 }} data-testid="br-drill">
            <Heading level={2} size="md">Incident / Expiry / Revocation Drill</Heading>
            <Text mono size="sm">fail_closed={String(drill.fail_closed)}</Text>
            <Text mono size="sm">session_invalidated={String(drill.session_invalidated)}</Text>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 200, overflow: "auto" }}>
              {JSON.stringify(drill, null, 2)}
            </pre>
          </Card>
        ) : null}

        {security ? (
          <Card style={{ marginTop: 12 }} data-testid="br-security">
            <Heading level={2} size="md">Security Results</Heading>
            <Text mono size="sm">all_pass={String(security.all_pass)}</Text>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 200, overflow: "auto" }}>
              {JSON.stringify({ passed: security.passed, failed: security.failed, all_pass: security.all_pass }, null, 2)}
            </pre>
          </Card>
        ) : null}

        {llm ? (
          <Card style={{ marginTop: 12 }} data-testid="br-llm">
            <Heading level={2} size="md">LLM Boundary</Heading>
            <Text mono size="sm" data-testid="llm-error">error={llm.error}</Text>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 120, overflow: "auto" }}>
              {JSON.stringify(llm, null, 2)}
            </pre>
          </Card>
        ) : null}

        {audit ? (
          <Card style={{ marginTop: 12 }} data-testid="br-audit">
            <Heading level={2} size="md">Audit Timeline / Evidence Center</Heading>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 200, overflow: "auto" }}>
              {JSON.stringify(audit, null, 2)}
            </pre>
          </Card>
        ) : null}

        {dash ? (
          <Card style={{ marginTop: 12 }} data-testid="br-dashboard">
            <Heading level={2} size="md">
              Control Center · {dash.labels?.simulation_only} · {dash.labels?.no_real_connection}
            </Heading>
            <Text mono size="sm" data-testid="br-disclaimer">{dash.disclaimer}</Text>
            <pre className="mono" style={{ fontSize: 10, maxHeight: 240, overflow: "auto" }}>
              {JSON.stringify({
                labels: dash.labels,
                credential_lifecycle: dash.credential_lifecycle,
                connection_state: dash.connection_state,
                ui_constraints: dash.ui_constraints,
              }, null, 2)}
            </pre>
          </Card>
        ) : null}
      </SignInGate>
    </div>
  );
}

function pill(color) {
  return {
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: 4,
    border: `1px solid ${color}`,
    color,
    fontSize: 11,
    fontWeight: 600,
  };
}
