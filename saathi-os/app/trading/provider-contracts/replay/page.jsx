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

export default function ProviderReplayPage() {
  const auth = useAuthMe();
  const [fixtures, setFixtures] = useState(null);
  const [replay, setReplay] = useState(null);
  const [error, setError] = useState(null);

  const call = async (path, setter, method = "GET", body = undefined) => {
    if (!auth.token) return;
    setError(null);
    try {
      setter(await plat(path, { token: auth.token, method, body }));
    } catch (cause) {
      setError(cause?.message || String(cause));
    }
  };

  return (
    <div className="page shell-page" data-testid="provider-replay-page">
      <TradingHeader
        title="Deterministic Provider Replay"
        subtitle="Recorded request/response fixtures are replayed in process. No network capture, authentication, or provider session."
      />
      <TradingTabs />
      <ProviderContractsNav />
      <OfflineProviderBoundary />
      <SignInGate ready={auth.ready} token={auth.token}>
        <SafetyBanner />
        <LoadError error={error} />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <Button data-testid="pc-load-replay-fixtures" onClick={() => call(
            "/tg/provider-contracts/replay/fixtures",
            setFixtures,
          )}>Load Recorded Fixtures</Button>
          <Button data-testid="pc-run-replay" onClick={() => call(
            "/tg/provider-contracts/requests",
            setReplay,
            "POST",
            {
              provider_id: "saathi.replay.market.v1",
              operation: "quotes.get",
              params: { symbol: "AAPL" },
              idempotency_key: "ui:replay:quote:AAPL:v1",
            },
          )}>Replay AAPL Quote</Button>
        </div>

        <Card data-testid="pc-replay-boundary" style={{ marginBottom: 12 }}>
          <Heading level={2} size="md">Replay Contract</Heading>
          <Text className="mono">transport=replay · network_enabled=false</Text>
          <Text className="mono">deterministic=true · recorded_offline=true</Text>
          <Text className="mono">source_type=REPLAY · live=false · synthetic=true</Text>
          <Text className="mono">account_derived=false · execution_capable=false</Text>
          <Text className="mono">Every request requires an idempotency key.</Text>
        </Card>

        {fixtures && (
          <Card data-testid="pc-replay-fixtures" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Recorded Request / Response Fixtures</Heading>
            <Text className="mono">Fixture count: {fixtures.count}</Text>
            {(fixtures.fixtures || []).map((fixture) => (
              <div key={fixture.fixture_id} style={{ padding: "10px 0",
                borderBottom: "1px solid var(--border-subtle,#20242e)" }}>
                <Text className="mono">{fixture.fixture_id}</Text>
                <Text className="mono" tone="muted">
                  {fixture.recorded_request?.operation} · {fixture.recorded_response_hash}
                </Text>
                <Text className="mono" tone="muted">
                  integrity_valid={String(fixture.integrity_valid)}
                </Text>
              </div>
            ))}
          </Card>
        )}

        {replay && (
          <Card data-testid="pc-replay-result">
            <Heading level={2} size="md">Replay Result</Heading>
            <Text className="mono">fixture_id={replay.response?.fixture_id}</Text>
            <Text className="mono">response_hash={replay.response?.response_hash}</Text>
            <Text className="mono">real_connectivity={String(replay.response?.real_connectivity)}</Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto" }}>
              {JSON.stringify(replay.response?.data, null, 2)}
            </pre>
          </Card>
        )}
      </SignInGate>
    </div>
  );
}
