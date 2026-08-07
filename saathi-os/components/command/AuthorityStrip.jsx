"use client";

import { StatusBadge, Text } from "@/components/ui";
import { truthStateToBadgeStatus } from "@/lib/command-authority";

/**
 * Compact truthful authority/status strip.
 * Disabled ≠ failure (neutral badge). Unknown is explicit.
 */
export default function AuthorityStrip({ authority }) {
  if (!authority?.chips?.length) {
    return (
      <div className="cmd-authority-strip" role="status" aria-label="Authority status unknown">
        <StatusBadge status="pending" label="AUTHORITY UNKNOWN" />
        <Text tone="muted" size="xs">
          No authority sources loaded
        </Text>
      </div>
    );
  }

  return (
    <div className="cmd-authority-strip" role="status" aria-label="Operating authority and system status">
      <ul className="cmd-authority-list">
        {authority.chips.map((chip) => (
          <li key={chip.id} className="cmd-authority-chip" title={chip.detail || chip.state}>
            <span className="cmd-authority-label">{chip.label}</span>
            <StatusBadge
              status={truthStateToBadgeStatus(chip.state)}
              label={chip.state}
            />
            {chip.detail ? (
              <span className="cmd-authority-detail mono">{chip.detail}</span>
            ) : null}
          </li>
        ))}
      </ul>
      {authority.freshness === "STALE" ? (
        <StatusBadge status="warning" label="STALE" />
      ) : null}
      {authority.degraded ? (
        <Text tone="muted" size="xs" as="p" className="cmd-authority-note">
          One or more chips degraded or blocked — not execution permission.
        </Text>
      ) : null}
    </div>
  );
}
