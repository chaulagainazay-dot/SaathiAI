"use client";
import { useState } from "react";
import { Card, Heading, Text, Button } from "@/components/ui";
import {
  TradingTabs,
  TradingHeader,
  SafetyBanner,
  SignInGate,
} from "@/components/trading/TradingShell";
import {
  HealthPill,
  OperationsAuthorityBoundary,
  OperationsBoundary,
  OperationsNav,
} from "@/components/trading/OperationsNav";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";

/** M328 — system health framework across all seven required domains. */
export default function OperationsHealthPage() {
  const auth = useAuthMe();
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    if (!auth.token) return;
    setError(null);
    try {
      setHealth(await plat("/tg/operations/health", { token: auth.token }));
    } catch (cause) {
      setError(cause?.message || String(cause));
    }
  };

  return (
    <div className="page shell-page" data-testid="operations-health-page">
      <TradingHeader
        title="System Health"
        subtitle="Platform, module, dependency, storage, scheduler, replay and provider registry health. Observation only."
      />
      <TradingTabs />
      <OperationsNav />
      <OperationsBoundary />
      <SignInGate ready={auth.ready} token={auth.token}>
        <SafetyBanner />
        {error && <Card style={{ marginBottom: 12 }}><Text className="mono">{error}</Text></Card>}
        <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
          <Button data-testid="health-load" onClick={load}>Load System Health</Button>
        </div>
        <OperationsAuthorityBoundary />

        <Card data-testid="health-states-card" style={{ marginBottom: 12 }}>
          <Heading level={2} size="md">Supported States</Heading>
          <Text className="mono" data-testid="health-supported-states">
            HEALTHY · WARNING · DEGRADED · FAILED · MAINTENANCE
          </Text>
          <Text className="mono" tone="muted">
            A degraded or failed component never remediates, escalates, or grants authority.
          </Text>
        </Card>

        {health && (
          <>
            <Card data-testid="health-overall-card" style={{ marginBottom: 12 }}>
              <Heading level={2} size="md">Overall</Heading>
              <Text className="mono" data-testid="health-overall-state">
                <HealthPill state={health.overall_state} />
              </Text>
              <Text className="mono" tone="muted">
                Components: {health.component_count} · coverage complete={String(health.domain_coverage_complete)}
              </Text>
              <Text className="mono" tone="muted">
                health_grants_authority={String(health.health_grants_authority)} ·
                degradation_triggers_remediation={String(health.degradation_triggers_remediation)}
              </Text>
            </Card>

            {(health.domains || []).map((domain) => (
              <Card key={domain.domain} data-testid={`health-domain-${domain.domain}`}
                style={{ marginBottom: 12 }}>
                <Heading level={2} size="md">{domain.domain}</Heading>
                <Text className="mono"><HealthPill state={domain.state} /></Text>
                {(domain.components || []).map((component) => (
                  <div key={component.component_id} style={{ padding: "8px 0",
                    borderBottom: "1px solid var(--border-subtle,#20242e)" }}>
                    <Text className="mono">{component.component_id} · {component.state}</Text>
                    <Text className="mono" tone="muted">{component.reason}</Text>
                  </div>
                ))}
              </Card>
            ))}
          </>
        )}
      </SignInGate>
    </div>
  );
}
