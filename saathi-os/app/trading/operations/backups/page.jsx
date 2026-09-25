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

/** M332 — local snapshots, integrity verification and recovery simulation. */
export default function OperationsBackupsPage() {
  const auth = useAuthMe();
  const [snapshots, setSnapshots] = useState(null);
  const [verification, setVerification] = useState(null);
  const [recovery, setRecovery] = useState(null);
  const [error, setError] = useState(null);

  const fetchPath = async (path, setter, method = "GET", body = undefined) => {
    if (!auth.token) return;
    setError(null);
    try {
      setter(await plat(path, { token: auth.token, method, body }));
    } catch (cause) {
      setError(cause?.message || String(cause));
    }
  };

  return (
    <div className="page shell-page" data-testid="operations-backups-page">
      <TradingHeader
        title="Backups and Recovery"
        subtitle="Configuration, replay snapshot and database manifests stored locally. Recovery is simulated; live state is never mutated."
      />
      <TradingTabs />
      <OperationsNav />
      <OperationsBoundary />
      <SignInGate ready={auth.ready} token={auth.token}>
        <SafetyBanner />
        {error && <Card style={{ marginBottom: 12 }}><Text className="mono">{error}</Text></Card>}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <Button data-testid="backups-load" onClick={() => fetchPath(
            "/tg/operations/backups", setSnapshots,
          )}>Load Snapshots</Button>
          <Button data-testid="backups-verify" onClick={() => fetchPath(
            "/tg/operations/backups/verify", setVerification, "POST",
          )}>Verify Snapshot Integrity</Button>
          <Button data-testid="backups-simulate-recovery" onClick={() => fetchPath(
            "/tg/operations/backups/simulate-recovery", setRecovery, "POST", { snapshot_id: null },
          )}>Simulate Recovery</Button>
        </div>
        <OperationsAuthorityBoundary />

        {snapshots && (
          <Card data-testid="backups-list-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Local Snapshots</Heading>
            <Text className="mono">Count: {snapshots.count}</Text>
            <Text className="mono" tone="muted" data-testid="backups-storage-target">
              storage_target={snapshots.storage_target} · cloud targets: {(snapshots.cloud_targets || []).length}
            </Text>
            {(snapshots.snapshots || []).map((snapshot) => (
              <div key={snapshot.snapshot_id} style={{ padding: "8px 0",
                borderBottom: "1px solid var(--border-subtle,#20242e)" }}>
                <Text className="mono">{snapshot.kind} · {snapshot.label}</Text>
                <Text className="mono" tone="muted">
                  {snapshot.size_bytes} bytes · digest {snapshot.payload_digest.slice(0, 16)}
                </Text>
                <Text className="mono" tone="muted">
                  cloud_replicated={String(snapshot.cloud_replicated)} ·
                  contains_credentials={String(snapshot.contains_credentials)}
                </Text>
              </div>
            ))}
          </Card>
        )}

        {verification && (
          <Card data-testid="backups-verification-card" style={{ marginBottom: 12 }}>
            <Heading level={2} size="md">Integrity Verification</Heading>
            <Text className="mono">
              Verified: {verification.verified_count} · failures: {(verification.failures || []).length}
            </Text>
          </Card>
        )}

        {recovery && (
          <Card data-testid="backups-recovery-card">
            <Heading level={2} size="md">Recovery Simulation</Heading>
            <Text className="mono" data-testid="recovery-outcome">
              {recovery.recovery?.outcome}
            </Text>
            <Text className="mono" tone="muted">
              live_state_mutated={String(recovery.recovery?.live_state_mutated)} ·
              applied_to_production={String(recovery.recovery?.applied_to_production)}
            </Text>
            <Text className="mono" tone="muted">
              restored_credentials={recovery.recovery?.restored_credentials} ·
              restored_accounts={recovery.recovery?.restored_accounts} ·
              restored_orders={recovery.recovery?.restored_orders}
            </Text>
          </Card>
        )}
      </SignInGate>
    </div>
  );
}
