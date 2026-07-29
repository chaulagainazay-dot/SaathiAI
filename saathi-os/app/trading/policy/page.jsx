"use client";
// M169/M174 — Policy Configuration + Kill Switch status (read-focused)
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useEffect, useState } from "react";

export default function TradingPolicyPage() {
  const d = useAuthMe();
  const [policy, setPolicy] = useState(null);
  const [ks, setKs] = useState([]);
  const [posture, setPosture] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    if (!d.token) return;
    try {
      const [p, k, pos] = await Promise.all([
        plat("/tg/policies", { token: d.token }),
        plat("/tg/kill-switch", { token: d.token }),
        plat("/tg/posture", { token: d.token }),
      ]);
      setPolicy((p.policies || [])[0] || null);
      setKs(k.kill_switches || []);
      setPosture(pos);
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  useEffect(() => { load(); }, [d.token]);

  const trip = async () => {
    if (!d.token || busy) return;
    setBusy(true);
    try {
      await plat("/tg/kill-switch/activate", {
        method: "POST", token: d.token,
        body: { scope: "GLOBAL", reason: "operator UI kill switch" },
      });
      await load();
    } catch (e) {
      setError(e?.message || String(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Policy & Kill Switch"
        subtitle="Versioned policy gates and persistent kill switches. Strategy/LLM cannot override." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" style={pill("#5B8CFF")}>NO LIVE ORDERS</span>
          <span className="mono" style={pill("#8FA0C4")}>SIMULATED FUNDS</span>
          <span className="mono" data-testid="authority-mode" style={pill("#F5A623")}>
            MODE: {posture?.authority_mode || "ADVISORY"}
          </span>
        </div>
        {error ? <LoadError error={error} /> : null}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 12 }}>
          <Card>
            <Heading level={2} size="md">Policy</Heading>
            {policy ? (
              <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 360 }}>
                {JSON.stringify(policy, null, 2)}
              </pre>
            ) : <Text tone="muted">Loading…</Text>}
          </Card>
          <Card>
            <Heading level={2} size="md">Kill Switch</Heading>
            <Button onClick={trip} disabled={busy} data-testid="activate-kill-switch">
              Activate global kill switch
            </Button>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", marginTop: 12 }}>
              {JSON.stringify(ks, null, 2)}
            </pre>
            <Text tone="muted" size="sm" as="p">
              Live trading authorized: {String(posture?.live_trading_authorized ?? false)}
            </Text>
          </Card>
        </div>
      </SignInGate>
    </div>
  );
}

function pill(c) {
  return { fontSize: 11, border: `1px solid ${c}`, color: c, borderRadius: 6, padding: "2px 8px" };
}
