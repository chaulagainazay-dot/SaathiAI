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
  OperationsAuthorityBoundary,
  OperationsBoundary,
  OperationsNav,
} from "@/components/trading/OperationsNav";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";

/** M330 + M334 — local metrics and offline load validation. No cloud monitoring. */
export default function OperationsMetricsPage() {
  const auth = useAuthMe();
  const [metrics, setMetrics] = useState(null);
  const [load, setLoad] = useState(null);
  const [error, setError] = useState(null);

  const fetchPath = async (path, setter, method = "GET") => {
    if (!auth.token) return;
    setError(null);
    try {
      setter(await plat(path, { token: auth.token, method }));
    } catch (cause) {
      setError(cause?.message || String(cause));
    }
  };

  return (
    <div className="page shell-page" data-testid="operations-metrics-page">
      <TradingHeader
        title="Operations Metrics"
        subtitle="API latency, task duration, queue depth, cache, replay, UI and database metrics — measured locally and never exported."
      />
      <TradingTabs />
      <OperationsNav />
      <OperationsBoundary />
      <SignInGate ready={auth.ready} token={auth.token}>
        <SafetyBanner />
        {error && <Card style={{ marginBottom: 12 }}><Text className="mono">{error}</Text></Card>}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <Button data-testid="metrics-load" onClick={() => fetchPath(
            "/tg/operations/metrics", setMetrics,
          )}>Load Metrics Summary</Button>
          <Button data-testid="metrics-run-load-validation" onClick={() => fetchPath(
            "/tg/operations/load-validation", setLoad, "POST",
          )}>Run Offline Load Validation</Button>
        </div>
        <OperationsAuthorityBoundary />

        {metrics && (
          <Card data-testid="metrics-summary-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Metric Summary</Heading>
            <Text className="mono">
              Series: {metrics.series_count} · samples: {metrics.sample_count}
            </Text>
            <Text className="mono" tone="muted" data-testid="metrics-covered-kinds">
              Kinds: {(metrics.covered_kinds || []).join(" · ")}
            </Text>
            <Text className="mono" tone="muted">
              thresholds_are_advisory={String(metrics.thresholds_are_advisory)} ·
              autoscaling_triggered={String(metrics.autoscaling_triggered)}
            </Text>
            {Object.entries(metrics.by_kind || {}).map(([kind, entries]) => (
              <div key={kind} style={{ padding: "8px 0",
                borderBottom: "1px solid var(--border-subtle,#20242e)" }}>
                <Text className="mono">{kind}</Text>
                {entries.map((entry) => (
                  <Text key={entry.name} className="mono" tone="muted">
                    {entry.name}: p50={entry.p50} p95={entry.p95} p99={entry.p99} {entry.unit} · {entry.classification}
                  </Text>
                ))}
              </div>
            ))}
          </Card>
        )}

        {load && (
          <Card data-testid="metrics-load-card">
            <Heading level={2} size="md">Offline Load Validation</Heading>
            <Text className="mono">
              Profiles: {load.profile_count} · breaches: {(load.breaches || []).length}
            </Text>
            <Text className="mono" tone="muted" data-testid="load-repeatability">
              deterministic_repeatability={String(load.repeatability?.identical)}
            </Text>
            <Text className="mono" tone="muted">
              simulation_only={String(load.simulation_only)} — no traffic is generated and no orders are submitted.
            </Text>
            {(load.runs || []).map((run) => (
              <Text key={run.profile.profile_id} className="mono" tone="muted">
                {run.profile.dimension}: p95={run.p95_ms}ms objective={run.objective_ms}ms · {run.classification}
              </Text>
            ))}
          </Card>
        )}
      </SignInGate>
    </div>
  );
}
