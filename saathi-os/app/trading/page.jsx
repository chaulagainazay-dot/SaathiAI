"use client";
import {
  Card,
  Heading,
  Text,
  AuthorityBadge,
  RiskBadge,
  StatusBadge,
  BlockedState,
  EvidenceBadge,
} from "@/components/ui";

/**
 * Trading Guardian — ADVISORY ONLY.
 * No order buttons, no broker prompts, no fake positions or prices.
 */
export default function TradingGuardianPage() {
  return (
    <div className="page shell-page">
      <div className="shell-page-header">
        <Text tone="muted" size="xs" mono>
          Run the business · Trading Guardian
        </Text>
        <Heading level={1} size="xl">
          Trading Guardian
        </Heading>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
          <AuthorityBadge authority="not-exercised" label="Not exercised" />
          <AuthorityBadge authority="advisory" label="Advisory only" />
          <RiskBadge risk="critical" label="Risk critical surface" />
          <StatusBadge status="blocked" label="Execution disabled" />
          <EvidenceBadge present={false} label="No live trading evidence" />
        </div>
      </div>

      <Card>
        <BlockedState
          title="Trading execution is not available"
          reason="NO_TRADING_AUTHORITY"
          description="Mode: Advisory only. Production authority: not granted. Leverage: disabled by default. Withdrawal permission: prohibited. This UI will not request broker credentials or place orders."
        />
        <dl className="shell-guardian-dl">
          <div>
            <dt>Mode</dt>
            <dd>Advisory only</dd>
          </div>
          <div>
            <dt>Execution</dt>
            <dd>Disabled</dd>
          </div>
          <div>
            <dt>Production authority</dt>
            <dd>Not granted</dd>
          </div>
          <div>
            <dt>Leverage</dt>
            <dd>Disabled by default</dd>
          </div>
          <div>
            <dt>Withdrawal permission</dt>
            <dd>Prohibited</dd>
          </div>
          <div>
            <dt>Live prices / positions</dt>
            <dd>Not shown — no approved read-only feed wired in this milestone</dd>
          </div>
        </dl>
        {/* Explicit: no order / connect / trade buttons anywhere on this page */}
      </Card>
    </div>
  );
}
