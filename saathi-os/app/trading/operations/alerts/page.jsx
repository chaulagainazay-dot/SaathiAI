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

/** M331 — offline alerts. Control centre, local logs and audit history only. */
export default function OperationsAlertsPage() {
  const auth = useAuthMe();
  const [alerts, setAlerts] = useState(null);
  const [policy, setPolicy] = useState(null);
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

  const refresh = () => fetchPath("/tg/operations/alerts", setAlerts);

  const transition = async (alertId, action) => {
    if (!auth.token) return;
    setError(null);
    try {
      await plat(`/tg/operations/alerts/${alertId}/${action}`, {
        token: auth.token, method: "POST", body: { actor: "operator" },
      });
      await refresh();
    } catch (cause) {
      setError(cause?.message || String(cause));
    }
  };

  return (
    <div className="page shell-page" data-testid="operations-alerts-page">
      <TradingHeader
        title="Operations Alerts"
        subtitle="Informational, warning and critical alerts delivered offline. No email, SMS, push, or webhook transport exists."
      />
      <TradingTabs />
      <OperationsNav />
      <OperationsBoundary />
      <SignInGate ready={auth.ready} token={auth.token}>
        <SafetyBanner />
        {error && <Card style={{ marginBottom: 12 }}><Text className="mono">{error}</Text></Card>}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <Button data-testid="alerts-load" onClick={refresh}>Load Alert History</Button>
          <Button data-testid="alerts-load-policy" onClick={() => fetchPath(
            "/tg/operations/alerts/policy", setPolicy,
          )}>Load Destination Policy</Button>
        </div>
        <OperationsAuthorityBoundary />

        {policy && (
          <Card data-testid="alerts-policy-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Destination Policy</Heading>
            <Text className="mono" data-testid="alerts-severities">
              Severities: {(policy.severities || []).join(" · ")}
            </Text>
            <Text className="mono" data-testid="alerts-destinations">
              Destinations: {(policy.allowed_destinations || []).join(" · ")}
            </Text>
            <Text className="mono" tone="muted">
              alerts_trigger_actions={String(policy.alerts_trigger_actions)} ·
              alerts_grant_authority={String(policy.alerts_grant_authority)}
            </Text>
            <Text className="mono" tone="muted">
              Forbidden: {(policy.forbidden_destinations || []).join(" · ")}
            </Text>
          </Card>
        )}

        {alerts && (
          <Card data-testid="alerts-list-card">
            <Heading level={2} size="md">Alert History</Heading>
            <Text className="mono">
              Total: {alerts.count} · open critical: {alerts.open_critical}
            </Text>
            {(alerts.alerts || []).map((alert) => (
              <div key={alert.alert_id} style={{ padding: "10px 0",
                borderBottom: "1px solid var(--border-subtle,#20242e)" }}>
                <Text className="mono">
                  [{alert.severity}] {alert.title} · {alert.state}
                </Text>
                <Text className="mono" tone="muted">
                  {alert.source} · trace {alert.trace_id}
                </Text>
                <Text className="mono" tone="muted">
                  email_sent={String(alert.email_sent)} · sms_sent={String(alert.sms_sent)} ·
                  push_sent={String(alert.push_sent)} · triggers_execution={String(alert.triggers_execution)}
                </Text>
                {alert.state !== "RESOLVED" && (
                  <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                    {alert.state === "OPEN" && (
                      <Button data-testid={`alert-ack-${alert.alert_id}`}
                        onClick={() => transition(alert.alert_id, "acknowledge")}>
                        Acknowledge
                      </Button>
                    )}
                    <Button data-testid={`alert-resolve-${alert.alert_id}`}
                      onClick={() => transition(alert.alert_id, "resolve")}>
                      Resolve
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </Card>
        )}
      </SignInGate>
    </div>
  );
}
