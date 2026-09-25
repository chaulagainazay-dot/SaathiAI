"use client";

import Link from "next/link";
import { Heading, Text, EmptyState, StatusBadge } from "@/components/ui";

export default function EvidenceTimeline({ timeline }) {
  const events = timeline?.events || [];

  return (
    <section className="cmd-panel surface cmd-timeline" aria-labelledby="cmd-timeline-heading">
      <div className="cmd-panel-head">
        <Heading level={2} size="md" id="cmd-timeline-heading">
          Evidence / activity
        </Heading>
        {timeline?.incompleteProvenance ? (
          <StatusBadge status="pending" label={`${timeline.incompleteProvenance} incomplete provenance`} />
        ) : null}
      </div>
      {!events.length ? (
        <EmptyState
          title="No recent events"
          description="Evidence and mission activity will list here when sources respond."
        />
      ) : (
        <ol className="cmd-timeline-list">
          {events.map((ev) => (
            <li key={ev.id} className="cmd-timeline-item">
              <Link href={ev.href || "/evidence"} className="cmd-timeline-link">
                <Text tone="muted" size="xs" mono>
                  {ev.timestamp || "time unknown"}
                  {ev.actor ? ` · ${ev.actor}` : " · actor unknown"}
                </Text>
                <div className="cmd-timeline-action">{ev.action}</div>
                <Text tone="disabled" size="xs" mono>
                  {ev.mission ? `mission ${ev.mission} · ` : ""}
                  {ev.authority ? `authority ${ev.authority} · ` : "authority n/a · "}
                  {ev.result ? `result ${ev.result} · ` : ""}
                  {ev.evidenceRef ? `evidence ${ev.evidenceRef}` : "no evidence ref"}
                  {` · src ${ev.source}`}
                </Text>
              </Link>
            </li>
          ))}
        </ol>
      )}
      <Text tone="muted" size="xs" as="p">
        {timeline?.note || "Missing provenance is shown as unknown — never invented."}
      </Text>
    </section>
  );
}
