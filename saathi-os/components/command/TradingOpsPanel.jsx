"use client";

import { Heading, Text, StatusBadge } from "@/components/ui";
import { truthStateToBadgeStatus } from "@/lib/command-authority";
import { deterministicSummary, tradingOpsView } from "@/lib/trading-ops-view";

/**
 * Trading operations status. RENDER ONLY.
 *
 * Every state shown here was classified by the backend's canonical snapshot.
 * This component maps and lays out; it does not decide whether anything is
 * healthy, and it exposes no control that could change trading state.
 *
 * Two presentation rules carry safety meaning:
 *
 *   A STALE SNAPSHOT IS NOT SHOWN AS HEALTH. When the collector has stopped, the
 *   badge reads STALE and the age is stated in words, because a frozen green
 *   panel is indistinguishable from a live one and that is how an operator gets
 *   misled.
 *
 *   MODE IS AS PROMINENT AS HEALTH. A perfectly healthy shadow stack must never
 *   look like a live one, so the mode sits beside the overall badge rather than
 *   in a footnote.
 */
export default function TradingOpsPanel({ status }) {
  const view = tradingOpsView(status);
  const summary = deterministicSummary(view);

  return (
    <section className="cmd-panel surface" aria-labelledby="cmd-tradingops-heading">
      <div className="cmd-panel-head">
        <Heading level={2} size="md" id="cmd-tradingops-heading">
          Trading operations
        </Heading>
        {/* Label text, never colour alone — the state must survive being read
            by someone who cannot distinguish the badge colours. */}
        <StatusBadge
          status={truthStateToBadgeStatus(view.displayState)}
          label={view.displayState}
        />
      </div>

      <div className="cmd-tradingops-mode">
        <Text size="xs" tone="muted">Mode</Text>
        <StatusBadge status="neutral" label={view.mode} />
        {!view.liveTradingAuthorized ? (
          <Text tone="muted" size="xs" as="span">Live trading not authorised</Text>
        ) : null}
      </div>

      {view.stale ? (
        <Text tone="warning" size="xs" as="p" role="status">
          {view.freshness === "NEVER_COLLECTED"
            ? "Not collected yet — no trading health is being reported."
            : `Stale — collected ${view.ageSeconds}s ago. These values describe that moment, not now.`}
        </Text>
      ) : (
        <Text tone="disabled" size="xs" as="p">
          Collected {view.ageSeconds}s ago.
        </Text>
      )}

      {view.primaryIncident ? (
        <div className="cmd-tradingops-incident">
          <Text size="sm" as="p">
            <strong>{view.primaryIncident.subsystem}</strong> — {view.primaryIncident.summary}
          </Text>
          {view.primaryIncident.symptoms.length ? (
            <Text tone="muted" size="xs" as="p">
              {/* Root cause first: the symptoms are consequences, and naming them
                  as such is what stops an operator chasing the wrong subsystem. */}
              Also affected: {view.primaryIncident.symptoms.map((s) => s.label).join(", ")}
            </Text>
          ) : null}
          <Text tone="disabled" size="xs" mono as="p">
            Owned by {view.primaryIncident.authority}
          </Text>
        </div>
      ) : null}

      <ul className="cmd-health-list">
        {view.subsystems.map((s) => (
          <li key={s.id} className="cmd-health-row">
            <span className="cmd-health-label">{s.label}</span>
            <StatusBadge status={truthStateToBadgeStatus(s.state)} label={s.state} />
            <Text tone="disabled" size="xs" mono className="cmd-health-detail">
              {s.detail}
            </Text>
          </li>
        ))}
      </ul>

      {view.actions.length ? (
        <div className="cmd-tradingops-actions">
          <Text size="xs" tone="muted" as="p">Needs an operator</Text>
          <ul>
            {view.actions.map((a) => (
              <li key={`${a.action}:${a.subsystem}`}>
                <Text size="xs" as="span">
                  {a.action.replace(/_/g, " ").toLowerCase()} — {a.detail}
                </Text>{" "}
                {/* Stated, not offered. This milestone renders no control that
                    mutates trading state, so the owning authority is named and
                    the operator goes there deliberately. */}
                <Text tone="disabled" size="xs" mono as="span">({a.authority})</Text>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <Text tone="muted" size="xs" as="p">
        {summary}
      </Text>
    </section>
  );
}
