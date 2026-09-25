"use client";

import Link from "next/link";
import { Heading, Text, StatusBadge, Button, EmptyState } from "@/components/ui";

function Field({ label, field }) {
  const available = field?.available;
  return (
    <div className={`cmd-metric ${available ? "" : "cmd-metric-na"}`}>
      <Text tone="muted" size="xs" mono>
        {label}
      </Text>
      {available ? (
        <div className="cmd-metric-value mono">{field.label}</div>
      ) : (
        <StatusBadge status="neutral" label="NOT AVAILABLE" />
      )}
      {!available && field?.reason ? (
        <Text tone="disabled" size="xs" mono>
          {field.reason}
        </Text>
      ) : null}
    </div>
  );
}

export default function InvestmentSnapshot({ investment }) {
  const inv = investment || {};
  const f = inv.fields || {};

  return (
    <section className="cmd-panel surface" aria-labelledby="cmd-invest-heading">
      <div className="cmd-panel-head">
        <Heading level={2} size="md" id="cmd-invest-heading">
          Investment state
        </Heading>
        <StatusBadge status="info" label="PAPER ONLY" />
        <StatusBadge status="blocked" label="LIVE UNAVAILABLE" />
      </div>

      <div className="cmd-invest-pipeline" aria-label="Investment lifecycle stages">
        <StatusBadge status="info" label="RESEARCH" />
        <span className="cmd-pipe">→</span>
        <StatusBadge status="info" label="PROPOSAL" />
        <span className="cmd-pipe">→</span>
        <StatusBadge status="pending" label="APPROVED" />
        <span className="cmd-pipe">→</span>
        <StatusBadge status="info" label="PAPER EXEC" />
        <span className="cmd-pipe">→</span>
        <StatusBadge status="blocked" label="LIVE EXEC" />
      </div>

      {!inv.ready && !f.paperNav ? (
        <EmptyState title="Paper state loading or unavailable" description={inv.note} />
      ) : (
        <div className="cmd-metric-grid">
          <Field label="Paper NAV / equity" field={f.paperNav} />
          <Field label="Cash" field={f.cash} />
          <Field label="P&L" field={f.pnl} />
          <Field label="Gross exposure" field={f.grossExposure} />
          <Field label="Net exposure" field={f.netExposure} />
          <Field label="Drawdown" field={f.drawdown} />
          <Field label="Risk state" field={f.riskState} />
          <Field label="Accounts" field={f.accounts} />
          <Field label="Unacked alerts" field={f.unackAlerts} />
          <Field label="Recon critical" field={f.reconExceptions} />
          <Field label="Blocking breakers" field={f.blockingBreakers} />
        </div>
      )}

      <Text tone="muted" size="xs" as="p">
        {inv.note || "Trading Guardian paper surface. No live orders."}
      </Text>
      <div className="cmd-panel-actions">
        <Link href="/trading">
          <Button size="sm" variant="secondary">
            Trading Guardian
          </Button>
        </Link>
        <Link href="/trading/paper-portfolio">
          <Button size="sm" variant="outline">
            Paper portfolio
          </Button>
        </Link>
        <Link href="/trading/paper-risk">
          <Button size="sm" variant="outline">
            Paper risk
          </Button>
        </Link>
      </div>
    </section>
  );
}
