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

export default function ProviderCapabilitiesPage() {
  const auth = useAuthMe();
  const [catalog, setCatalog] = useState(null);
  const [negotiation, setNegotiation] = useState(null);
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
    <div className="page shell-page" data-testid="provider-capabilities-page">
      <TradingHeader
        title="Provider Capability Contracts"
        subtitle="Negotiation describes offline support; it never activates access or executes an operation."
      />
      <TradingTabs />
      <ProviderContractsNav />
      <OfflineProviderBoundary />
      <SignInGate ready={auth.ready} token={auth.token}>
        <SafetyBanner />
        <LoadError error={error} />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <Button data-testid="pc-load-capabilities" onClick={() => call(
            "/tg/provider-contracts/capabilities",
            setCatalog,
          )}>Load Capability Matrix</Button>
          <Button data-testid="pc-negotiate-capabilities" onClick={() => call(
            "/tg/provider-contracts/capabilities/negotiate",
            setNegotiation,
            "POST",
            {
              provider_id: "saathi.mock.market.v1",
              capabilities: [
                "quotes",
                "candles",
                "trades",
                "orderbook",
                "symbols",
                "market_status",
                "positions",
                "balances",
                "orders",
                "transfers",
              ],
            },
          )}>Negotiate Offline Scope</Button>
        </div>

        <Card data-testid="pc-capability-boundary" style={{ marginBottom: 12 }}>
          <Heading level={2} size="md">Capability Boundary</Heading>
          <Text className="mono">quotes · candles · trades · orderbook · symbols · market_status = SUPPORTED_OFFLINE</Text>
          <Text className="mono">positions · balances · orders · transfers = FORBIDDEN_BY_GOVERNANCE</Text>
          <Text className="mono">Other negotiated states: UNSUPPORTED · UNAVAILABLE</Text>
          <Text className="mono">negotiation_only=true · executes=false</Text>
          <Text className="mono">Declaration does not grant permission, connectivity, account access, or order authority.</Text>
        </Card>

        {catalog && (
          <Card data-testid="pc-capability-catalog" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Provider-Neutral Capability Matrix</Heading>
            {(catalog.capabilities || []).map((capability) => (
              <div key={capability.name} style={{ padding: "10px 0",
                borderBottom: "1px solid var(--border-subtle,#20242e)" }}>
                <Text className="mono">{capability.name} · {capability.access}</Text>
                <Text tone="muted">{capability.reason}</Text>
              </div>
            ))}
          </Card>
        )}

        {negotiation && (
          <Card data-testid="pc-negotiation-result">
            <Heading level={2} size="md">Negotiation Result</Heading>
            <Text className="mono">Granted: {(negotiation.granted || []).join(", ")}</Text>
            <Text className="mono">Denied: {(negotiation.denied || []).join(", ")}</Text>
            <Text className="mono">executes={String(negotiation.executes)}</Text>
          </Card>
        )}
      </SignInGate>
    </div>
  );
}
