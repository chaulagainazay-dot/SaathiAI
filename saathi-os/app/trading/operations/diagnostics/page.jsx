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

/** M333 — one diagnostics centre producing one unified report. Never remediates. */
export default function OperationsDiagnosticsPage() {
  const auth = useAuthMe();
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState(null);
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
    <div className="page shell-page" data-testid="operations-diagnostics-page">
      <TradingHeader
        title="Operational Diagnostics"
        subtitle="Provider contracts, replay engine, authority system, approval engine, storage, configuration and browser certification history."
      />
      <TradingTabs />
      <OperationsNav />
      <OperationsBoundary />
      <SignInGate ready={auth.ready} token={auth.token}>
        <SafetyBanner />
        {error && <Card style={{ marginBottom: 12 }}><Text className="mono">{error}</Text></Card>}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <Button data-testid="diagnostics-run" onClick={() => fetchPath(
            "/tg/operations/diagnostics", setReport, "POST",
          )}>Run Offline Diagnostics</Button>
          <Button data-testid="diagnostics-load-history" onClick={() => fetchPath(
            "/tg/operations/certification-history", setHistory,
          )}>Load Certification History</Button>
        </div>
        <OperationsAuthorityBoundary />

        {report && (
          <Card data-testid="diagnostics-report-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Unified Diagnostic Report</Heading>
            <Text className="mono" data-testid="diagnostics-report-id">{report.report_id}</Text>
            <Text className="mono">
              Checks: {report.check_count} · failures: {(report.failures || []).length}
            </Text>
            <Text className="mono" tone="muted">
              coverage_complete={String(report.coverage_complete)} ·
              auto_remediation={String(report.auto_remediation)}
            </Text>
            {(report.results || []).map((result) => (
              <div key={result.check_id} style={{ padding: "8px 0",
                borderBottom: "1px solid var(--border-subtle,#20242e)" }}>
                <Text className="mono">{result.subsystem}: {result.status}</Text>
                <Text className="mono" tone="muted">{result.summary}</Text>
              </div>
            ))}
          </Card>
        )}

        {history && (
          <Card data-testid="diagnostics-history-card">
            <Heading level={2} size="md">Browser Certification History</Heading>
            <Text className="mono" tone="muted">
              read_only={String(history.read_only)} · history_mutated={String(history.history_mutated)}
            </Text>
            {(history.records || []).map((record) => (
              <Text key={record.path} className="mono" tone="muted">
                {record.milestone}: {record.verdict || "not recorded"}
              </Text>
            ))}
          </Card>
        )}
      </SignInGate>
    </div>
  );
}
