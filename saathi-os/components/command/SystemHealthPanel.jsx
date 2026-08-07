"use client";

import Link from "next/link";
import { Heading, Text, StatusBadge, Button } from "@/components/ui";
import { truthStateToBadgeStatus } from "@/lib/command-authority";

export default function SystemHealthPanel({ systemHealth }) {
  const sh = systemHealth || { overall: "UNKNOWN", subsystems: [] };

  return (
    <section className="cmd-panel surface" aria-labelledby="cmd-health-heading">
      <div className="cmd-panel-head">
        <Heading level={2} size="md" id="cmd-health-heading">
          System state
        </Heading>
        <StatusBadge status={truthStateToBadgeStatus(sh.overall)} label={sh.overall || "UNKNOWN"} />
      </div>
      <ul className="cmd-health-list">
        {(sh.subsystems || []).map((s) => (
          <li key={s.id} className="cmd-health-row">
            <span className="cmd-health-label">{s.label}</span>
            <StatusBadge status={truthStateToBadgeStatus(s.state)} label={s.state} />
            <Text tone="disabled" size="xs" mono className="cmd-health-detail">
              {s.detail}
            </Text>
          </li>
        ))}
      </ul>
      <Text tone="muted" size="xs" as="p">
        Unknown is explicit. Disabled is not failure. No green without evidence.
      </Text>
      <div className="cmd-panel-actions">
        <Link href="/monitoring">
          <Button size="sm" variant="outline">
            Monitoring
          </Button>
        </Link>
        <Link href="/settings/voice">
          <Button size="sm" variant="outline">
            Voice settings
          </Button>
        </Link>
      </div>
    </section>
  );
}
