"use client";

import Link from "next/link";
import { Heading, Text, StatusBadge, AuthorityBadge, EmptyState, Button } from "@/components/ui";

function MissionRow({ m }) {
  return (
    <Link href={m.href || "/missions"} className="cmd-row">
      <div className="cmd-row-main">
        <div className="cmd-row-title">{m.name}</div>
        <Text tone="muted" size="xs" mono>
          stage: {m.progressLabel}
          {m.owner ? ` · owner: ${m.owner}` : ""}
          {m.agent ? ` · agent: ${m.agent}` : ""}
        </Text>
        {m.blocker ? (
          <Text tone="muted" size="xs">
            blocker: {m.blocker}
          </Text>
        ) : null}
        {m.nextAction ? (
          <Text tone="muted" size="xs">
            next: {m.nextAction}
          </Text>
        ) : null}
      </div>
      <div className="cmd-row-meta">
        <StatusBadge status="info" label={m.status} />
        {m.approvalRequired ? <AuthorityBadge authority="approval-required" /> : <AuthorityBadge authority="advisory" />}
      </div>
    </Link>
  );
}

function AgentRow({ a }) {
  return (
    <Link href={a.href || "/agents"} className="cmd-row">
      <div className="cmd-row-main">
        <div className="cmd-row-title">{a.name}</div>
        <Text tone="muted" size="xs" mono>
          {a.role ? `role: ${a.role}` : "role: unknown"}
          {a.missionId ? ` · mission: ${a.missionId}` : ""}
        </Text>
      </div>
      <StatusBadge status="info" label={String(a.status)} />
    </Link>
  );
}

export default function ActivityPanel({ activity }) {
  const active = activity?.activeMissions || [];
  const blocked = activity?.blockedMissions || [];
  const agents = activity?.agents || [];
  const empty = !active.length && !blocked.length && !agents.length;

  return (
    <section className="cmd-panel surface" aria-labelledby="cmd-activity-heading">
      <div className="cmd-panel-head">
        <Heading level={2} size="md" id="cmd-activity-heading">
          Current activity
        </Heading>
        <Text tone="muted" size="xs" mono>
          missions: {activity?.missionsStatus || "unknown"} · agents: {activity?.agentsStatus || "unknown"}
        </Text>
      </div>

      {empty ? (
        <EmptyState
          title="No active missions or agents"
          description="Start from Command or open Missions. Progress is stage-based — no invented percentages."
          action={
            <Link href="/missions/new">
              <Button size="sm" variant="secondary">
                New mission
              </Button>
            </Link>
          }
        />
      ) : (
        <>
          {active.length > 0 && (
            <div className="cmd-subblock">
              <Text tone="muted" size="xs" mono>
                Active missions
              </Text>
              {active.map((m) => (
                <MissionRow key={m.id || m.name} m={m} />
              ))}
            </div>
          )}
          {blocked.length > 0 && (
            <div className="cmd-subblock">
              <Text tone="muted" size="xs" mono>
                Blocked / attention
              </Text>
              {blocked.map((m) => (
                <MissionRow key={`b-${m.id || m.name}`} m={m} />
              ))}
            </div>
          )}
          {agents.length > 0 && (
            <div className="cmd-subblock">
              <Text tone="muted" size="xs" mono>
                Agents
              </Text>
              {agents.map((a) => (
                <AgentRow key={a.id || a.name} a={a} />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
