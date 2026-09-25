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

/** M335 — read-only operations control centre. No execution or deployment control. */
export default function OperationsControlCenterPage() {
  const auth = useAuthMe();
  const [control, setControl] = useState(null);
  const [certification, setCertification] = useState(null);
  const [error, setError] = useState(null);

  const load = async (path, setter, method = "GET") => {
    if (!auth.token) return;
    setError(null);
    try {
      setter(await plat(path, { token: auth.token, method }));
    } catch (cause) {
      setError(cause?.message || String(cause));
    }
  };

  const panels = control?.panels || {};

  return (
    <div className="page shell-page" data-testid="operations-page">
      <TradingHeader
        title="Operations Control Center"
        subtitle="Read-only offline operations posture. Health, metrics, alerts, diagnostics, backups, replay health, authority and certification history."
      />
      <TradingTabs />
      <OperationsNav />
      <OperationsBoundary />
      <SignInGate ready={auth.ready} token={auth.token}>
        <SafetyBanner />
        {error && (
          <Card data-testid="operations-error" style={{ marginBottom: 12 }}>
            <Text className="mono">{error}</Text>
          </Card>
        )}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <Button data-testid="operations-load" onClick={() => load(
            "/tg/operations/control-center", setControl,
          )}>Load Operations Posture</Button>
          <Button data-testid="operations-certify" onClick={() => load(
            "/tg/operations/certify", setCertification, "POST",
          )}>Run Operations Certification</Button>
        </div>

        <OperationsAuthorityBoundary />

        {control && (
          <>
            <Card data-testid="operations-health-panel" style={{ marginBottom: 12 }}>
              <Heading level={2} size="md">System Health</Heading>
              <Text className="mono" data-testid="operations-overall-health">
                Overall: <HealthPill state={panels.system_health?.overall_state} />
              </Text>
              <Text className="mono" tone="muted">
                Components: {panels.system_health?.component_count} · coverage complete={String(panels.system_health?.coverage_complete)}
              </Text>
              {(panels.system_health?.domains || []).map((domain) => (
                <Text key={domain.domain} className="mono" tone="muted">
                  {domain.domain}: {domain.state} ({domain.component_count})
                </Text>
              ))}
            </Card>

            <Card data-testid="operations-metrics-panel" style={{ marginBottom: 12 }}>
              <Heading level={2} size="md">Metrics</Heading>
              <Text className="mono">
                Series: {panels.metrics?.series_count} · samples: {panels.metrics?.sample_count}
              </Text>
              <Text className="mono" tone="muted">
                Kinds: {(panels.metrics?.covered_kinds || []).join(" · ")}
              </Text>
              <Text className="mono" tone="muted">
                Threshold breaches: {panels.metrics?.breach_count} (advisory only; nothing is scaled or restarted)
              </Text>
            </Card>

            <Card data-testid="operations-alerts-panel" style={{ marginBottom: 12 }}>
              <Heading level={2} size="md">Alerts</Heading>
              <Text className="mono">
                Total: {panels.alerts?.count} · open critical: {panels.alerts?.open_critical}
              </Text>
              <Text className="mono" tone="muted">
                Destinations: {(panels.alerts?.destinations || []).join(" · ")}
              </Text>
              <Text className="mono" tone="muted">
                No email, SMS, push, or webhook delivery exists.
              </Text>
            </Card>

            <Card data-testid="operations-diagnostics-panel" style={{ marginBottom: 12 }}>
              <Heading level={2} size="md">Diagnostics</Heading>
              <Text className="mono">
                Subsystems: {panels.diagnostics?.subsystem_count}
              </Text>
              <Text className="mono" tone="muted">
                {(panels.diagnostics?.subsystems || []).join(" · ")}
              </Text>
              <Text className="mono" tone="muted">
                auto_remediation={String(panels.diagnostics?.auto_remediation)}
              </Text>
            </Card>

            <Card data-testid="operations-backups-panel" style={{ marginBottom: 12 }}>
              <Heading level={2} size="md">Backups and Recovery</Heading>
              <Text className="mono">
                Snapshots: {panels.backups?.snapshot_count} · recovery runs: {panels.backups?.recovery_runs}
              </Text>
              <Text className="mono" tone="muted">
                cloud_backup={String(panels.backups?.cloud_backup)} · recovery is simulation only
              </Text>
            </Card>

            <Card data-testid="operations-replay-panel" style={{ marginBottom: 12 }}>
              <Heading level={2} size="md">Replay Health</Heading>
              <Text className="mono">
                {panels.replay_health?.reason} · fixtures: {panels.replay_health?.fixture_count}
              </Text>
              <Text className="mono" tone="muted">
                deterministic={String(panels.replay_health?.deterministic)}
              </Text>
            </Card>

            <Card data-testid="operations-authority-panel" style={{ marginBottom: 12 }}>
              <Heading level={2} size="md">Authority Summary</Heading>
              <Text className="mono" data-testid="operations-all-locks-false">
                all_locks_false={String(panels.authority_summary?.all_locks_false)}
              </Text>
              <Text className="mono" tone="muted">
                deny_overrides_allow={String(panels.authority_summary?.deny_overrides_allow)} ·
                authority_does_not_implicitly_expand={String(panels.authority_summary?.authority_does_not_implicitly_expand)}
              </Text>
              <Text className="mono" tone="muted">
                operations_layer_grants_authority={String(panels.authority_summary?.operations_layer_grants_authority)}
              </Text>
            </Card>

            <Card data-testid="operations-certification-history-panel" style={{ marginBottom: 12 }}>
              <Heading level={2} size="md">Certification History</Heading>
              <Text className="mono" tone="muted">
                read_only={String(panels.certification_history?.read_only)}
              </Text>
              {(panels.certification_history?.records || []).map((record) => (
                <Text key={record.path} className="mono" tone="muted">
                  {record.milestone}: {record.verdict || "not recorded"}
                </Text>
              ))}
            </Card>
          </>
        )}

        {certification && (
          <Card data-testid="operations-certification-card">
            <Heading level={2} size="md">Certification</Heading>
            <Text className="mono" data-testid="operations-verdict">{certification.verdict}</Text>
            <Text className="mono">Checks: {certification.check_count}</Text>
            <Text className="mono">Failures: {(certification.failures || []).length}</Text>
          </Card>
        )}
      </SignInGate>
    </div>
  );
}
