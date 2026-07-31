"use client";
import { useState } from "react";
import { Card, Heading, Text, Button } from "@/components/ui";
import {
  TradingTabs,
  TradingHeader,
  SafetyBanner,
  SignInGate,
  LoadError,
} from "@/components/trading/TradingShell";
import {
  OfflineProviderBoundary,
  ProviderContractsNav,
} from "@/components/trading/ProviderContractsNav";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";

/** M320–M327 — credentialless provider contracts and offline mock transport. */
export default function ProviderContractsPage() {
  const auth = useAuthMe();
  const [dashboard, setDashboard] = useState(null);
  const [providers, setProviders] = useState(null);
  const [sessions, setSessions] = useState(null);
  const [mockQuote, setMockQuote] = useState(null);
  const [certification, setCertification] = useState(null);
  const [error, setError] = useState(null);

  const load = async (path, setter, method = "GET", body = undefined) => {
    if (!auth.token) return;
    setError(null);
    try {
      setter(await plat(path, { token: auth.token, method, body }));
    } catch (cause) {
      setError(cause?.message || String(cause));
    }
  };

  const loadOverview = async () => {
    if (!auth.token) return;
    setError(null);
    try {
      const [nextDashboard, nextProviders, nextSessions] = await Promise.all([
        plat("/tg/provider-contracts/dashboard", { token: auth.token }),
        plat("/tg/provider-contracts/providers", { token: auth.token }),
        plat("/tg/provider-contracts/sessions", { token: auth.token }),
      ]);
      setDashboard(nextDashboard);
      setProviders(nextProviders);
      setSessions(nextSessions);
    } catch (cause) {
      setError(cause?.message || String(cause));
    }
  };

  return (
    <div className="page shell-page" data-testid="provider-contracts-page">
      <TradingHeader
        title="Credentialless Provider Contracts"
        subtitle="Provider-neutral interfaces with deterministic mock and replay fixtures. Offline only; no real provider connectivity."
      />
      <TradingTabs />
      <ProviderContractsNav />
      <OfflineProviderBoundary />
      <SignInGate ready={auth.ready} token={auth.token}>
        <SafetyBanner />
        <LoadError error={error} />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <Button data-testid="pc-load-overview" onClick={loadOverview}>Load Provider Contracts</Button>
          <Button data-testid="pc-mock-quote" onClick={() => load(
            "/tg/provider-contracts/requests",
            setMockQuote,
            "POST",
            {
              provider_id: "saathi.mock.market.v1",
              operation: "quotes.get",
              params: { symbol: "AAPL" },
              idempotency_key: "ui:mock:quote:AAPL:v1",
            },
          )}>Preview Mock Quote</Button>
          <Button data-testid="pc-certify" onClick={() => load(
            "/tg/provider-contracts/certify",
            setCertification,
            "POST",
          )}>Certify Offline Contracts</Button>
        </div>

        <Card data-testid="pc-maturity-card" style={{ marginBottom: 12 }}>
          <Heading level={2} size="md">Authority Boundary</Heading>
          <Text className="mono" data-testid="pc-maturity">Current maturity: MOCK_CONNECTIVITY_ONLY</Text>
          <Text className="mono" data-testid="pc-max-state">Maximum: MOCK_PROVIDER_READY_NO_REAL_CONNECTIVITY</Text>
          <Text className="mono" data-testid="pc-authority-locks">
            REAL_CONNECTIVITY_AUTHORIZED=false · OAUTH_AUTHORIZED=false ·
            CREDENTIAL_PROVISIONING_AUTHORIZED=false · ACCOUNT_ACCESS_AUTHORIZED=false ·
            BALANCE_READ_AUTHORIZED=false · POSITION_READ_AUTHORIZED=false ·
            ORDER_SUBMISSION_AUTHORIZED=false · ORDER_EXECUTION_AUTHORIZED=false ·
            CANARY_ACTIVATION_AUTHORIZED=false · LIVE_TRADING_AUTHORIZED=false
          </Text>
        </Card>

        {dashboard && (
          <Card data-testid="pc-dashboard-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">{dashboard.title}</Heading>
            <Text className="mono">Providers: {dashboard.overview?.provider_count}</Text>
            <Text className="mono">Mock transports: {dashboard.overview?.mock_transports}</Text>
            <Text className="mono">Replay transports: {dashboard.overview?.replay_transports}</Text>
            <Text className="mono">Network transports: {dashboard.overview?.network_transports}</Text>
            <Text className="mono">Real connections: {dashboard.overview?.real_connections}</Text>
          </Card>
        )}

        {providers && (
          <Card data-testid="pc-provider-list" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Offline Providers</Heading>
            {(providers.providers || []).map((provider) => (
              <div key={provider.provider_id} style={{ padding: "10px 0",
                borderBottom: "1px solid var(--border-subtle,#20242e)" }}>
                <Text className="mono">{provider.display_name}</Text>
                <Text className="mono" tone="muted">
                  {provider.provider_id} · {provider.transport} · {provider.session?.state}
                </Text>
                <Text className="mono" tone="muted">
                  credentialless={String(provider.credentialless)} · network_enabled={String(provider.network_enabled)}
                </Text>
              </div>
            ))}
          </Card>
        )}

        {sessions && (
          <Card data-testid="pc-session-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Credentialless Session State</Heading>
            <Text className="mono">authentication_state_exists={String(sessions.authentication_state_exists)}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto" }}>
              {JSON.stringify(sessions.sessions, null, 2)}
            </pre>
          </Card>
        )}

        {mockQuote && (
          <Card data-testid="pc-mock-response" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Deterministic Mock Response</Heading>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto" }}>
              {JSON.stringify(mockQuote.response, null, 2)}
            </pre>
          </Card>
        )}

        {certification && (
          <Card data-testid="pc-certification-card">
            <Heading level={2} size="md">Certification</Heading>
            <Text className="mono" data-testid="pc-verdict">{certification.verdict}</Text>
            <Text className="mono">Failures: {(certification.failures || []).length}</Text>
          </Card>
        )}
      </SignInGate>
    </div>
  );
}
