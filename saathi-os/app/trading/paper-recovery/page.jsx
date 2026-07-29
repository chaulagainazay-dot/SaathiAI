"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function PaperRecoveryPage() {
  const d = useAuthMe();
  const [backup, setBackup] = useState(null);
  const [error, setError] = useState(null);

  const createBackup = async () => {
    if (!d.token) return;
    setError(null);
    try {
      setBackup(await plat("/tg/paper/backup", {
        method: "POST", token: d.token,
        body: { dest_dir: "data/platform/paper_backups" },
      }));
    } catch (e) { setError(e?.message || String(e)); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Recovery Center"
        subtitle="Backup verification and isolated recovery tests. Never overwrites the source store." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" style={pill("#F5A623")}>ISOLATED RECOVERY</span>
        </div>
        <Button data-testid="create-backup" onClick={createBackup}>Create backup</Button>
        {error ? <LoadError error={error} /> : null}
        {backup ? (
          <Card style={{ marginTop: 16 }} data-testid="backup-result">
            <Heading level={2} size="md">Backup · {backup.backup_id || backup.status}</Heading>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 280, overflow: "auto" }}>
              {JSON.stringify(backup, null, 2)}
            </pre>
          </Card>
        ) : null}
      </SignInGate>
    </div>
  );
}
function pill(c) { return { fontSize: 11, border: `1px solid ${c}`, color: c, borderRadius: 6, padding: "2px 8px" }; }
