"use client";
// SaathiOS Orbit — the command constellation.
//
// One screen that answers "what is my system doing right now?" without reading a
// table. Core = SaathiOS itself; the ring = the specialist agents; colour = state.
// Read-only by construction: selecting a node reveals detail, it never commands.
import { useMemo, useState } from "react";
import "./orbit.css";
import AgentOrbit from "@/components/orbit/AgentOrbit";
import { orbitSummary, statusToneFor } from "@/lib/orbit";
import { useOrbitAgents, SOURCE_LABEL } from "@/lib/orbit-data";
import { Panel, Eyebrow, Heading, Text, StatusBadge, Divider, Stack } from "@/components/ui";

// Reference shape — the roster the view expects. Used only when the live fleet is
// unreachable or the operator is signed out, and the surface SAYS so when it is.
const ROSTER = [
  { id: "chief", label: "Chief of Staff", tier: 1, state: "active", detail: "Routes work, holds the daily plan" },
  { id: "research", label: "Research", tier: 1, state: "active", detail: "Evidence, theses, challenge protocol" },
  { id: "trading", label: "Trading", tier: 1, state: "paused", detail: "Paper only — no live orders" },
  { id: "content", label: "Content", tier: 1, state: "active", detail: "Mr Yeti pipeline, publishing queue" },
  { id: "finance", label: "Finance", tier: 1, state: "active", detail: "Ledger, runway, reconciliation" },
  { id: "ops", label: "Ops", tier: 1, state: "warning", detail: "Health watchdog, restarts" },

  { id: "memory", label: "Memory", tier: 2, state: "active", detail: "Durable decisions and lessons" },
  { id: "studio", label: "Studio", tier: 2, state: "idle", detail: "Video and asset generation" },
  { id: "learning", label: "Learning", tier: 2, state: "active", detail: "IELTS coach, daily practice" },
  { id: "security", label: "Security", tier: 2, state: "active", detail: "Egress guard, secret scanning" },
  { id: "evidence", label: "Evidence", tier: 2, state: "active", detail: "Shared memory, provenance" },
  { id: "voice", label: "Voice", tier: 2, state: "idle", detail: "Observation only — never executes" },
  { id: "connectors", label: "Connectors", tier: 2, state: "pending", detail: "Governed provider registry" },
  { id: "canteen", label: "Canteen", tier: 2, state: "active", detail: "HCG operations" },
];

export default function OrbitPage() {
  const [selectedId, setSelectedId] = useState("");
  const { agents, source, loading, error, reload } = useOrbitAgents(ROSTER);
  const summary = useMemo(() => orbitSummary(agents), [agents]);
  const selected = agents.find((a) => a.id === selectedId) || null;
  const isLive = source === "live";

  return (
    <div className="orbit-root page shell-page">
      <Stack gap={5}>
        <div>
          <Eyebrow>Command</Eyebrow>
          <Heading level={1} size="2xl">Orbit</Heading>
          <Text tone="muted" as="p">
            Every specialist your system runs, in one field. Colour is state, distance is
            tier, edges are reporting lines. Read-only — this surface observes, it never commands.
          </Text>
          <div className="orbit-source" data-testid="orbit-source">
            <StatusBadge status={isLive ? "success" : "warning"} label={SOURCE_LABEL[source]} />
            {loading ? <Text tone="muted" size="xs">loading fleet…</Text> : null}
            {error ? <Text tone="warning" size="xs">{error}</Text> : null}
            <button type="button" className="orbit-reload" onClick={reload}>refresh</button>
          </div>
        </div>

        <Panel>
          <AgentOrbit
            agents={agents}
            selectedId={selectedId}
            onSelect={(n) => setSelectedId(n.id === selectedId ? "" : n.id)}
          />
        </Panel>

        <div className="orbit-detail-grid">
          <Panel>
            <Eyebrow>Selected</Eyebrow>
            {selected ? (
              <Stack gap={2}>
                <Heading level={2} size="md">{selected.label}</Heading>
                <StatusBadge status={statusToneFor(selected.state)} label={selected.state} />
                <Text tone="muted" size="sm" as="p">{selected.detail}</Text>
              </Stack>
            ) : (
              <Text tone="disabled" size="sm" as="p">
                Select an agent in the constellation to inspect it.
              </Text>
            )}
          </Panel>

          <Panel>
            <Eyebrow>Fleet</Eyebrow>
            <Stack gap={2}>
              <Text size="sm" as="p">{summary.total} agents in orbit</Text>
              <Divider />
              <Text tone="muted" size="sm" as="p">
                {summary.healthy} healthy · {summary.attention} need attention
              </Text>
              <StatusBadge status={summary.worst} label={`worst: ${summary.worst}`} />
            </Stack>
          </Panel>
        </div>
      </Stack>
    </div>
  );
}
