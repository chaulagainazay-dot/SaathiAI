"use client";

// One logical agent at its workstation. Lightweight inline SVG (no images).
// The monitor carries the activity cue (scan / chart / typing / review);
// the badge carries a non-colour glyph so state never depends on colour alone.

import { memo } from "react";
import { agentAriaLabel, motionFor, statusLabel, statusMeta } from "@/lib/organization";

function Screen({ motion }) {
  switch (motion) {
    case "scan":
      return (
        <g className="co-screen co-screen-scan">
          <rect x="9" y="25.5" width="12" height="1" rx=".5" />
          <rect x="9" y="27.5" width="8" height="1" rx=".5" />
          <circle className="co-scan-dot" cx="20" cy="27" r="1.1" />
        </g>
      );
    case "chart":
      return (
        <g className="co-screen co-screen-chart">
          <rect className="co-bar co-bar1" x="10" y="25" width="2" height="4" />
          <rect className="co-bar co-bar2" x="13.5" y="25" width="2" height="4" />
          <rect className="co-bar co-bar3" x="17" y="25" width="2" height="4" />
        </g>
      );
    case "type":
      return (
        <g className="co-screen co-screen-type">
          <rect x="9" y="25.5" width="9" height="1" rx=".5" />
          <rect className="co-caret" x="19" y="25" width="1.2" height="2.4" />
        </g>
      );
    case "review":
      return (
        <g className="co-screen co-screen-review">
          <rect x="10" y="24.8" width="7" height="4.6" rx=".6" />
          <path className="co-review-pen" d="M18 29.2l2.4-2.4" />
        </g>
      );
    case "done":
      return <path className="co-screen co-screen-done" d="M11 27.2l2 2 4.4-4.4" />;
    default:
      return null;
  }
}

function AgentWorker({ role, selected, onSelect, reducedMotion = false, size = "md", inMission = false }) {
  const meta = statusMeta(role.status);
  const motion = motionFor(role.status, reducedMotion);
  const busy = meta.group === "active" || meta.group === "review";
  return (
    <button
      type="button"
      className={`co-worker co-size-${size}${selected ? " is-selected" : ""}${inMission ? " in-mission" : ""}`}
      data-status={role.status}
      data-tone={meta.tone}
      data-motion={motion}
      data-role-id={role.role_id}
      data-tier={role.tier}
      aria-label={agentAriaLabel(role)}
      aria-pressed={selected ? "true" : "false"}
      title={`${role.name} — ${statusLabel(role)}${role.reason ? `: ${role.reason}` : ""}`}
      onClick={() => onSelect?.(role.role_id)}
    >
      <span className="co-badge" aria-hidden="true">{meta.glyph}</span>
      <svg viewBox="0 0 30 34" className="co-bot" aria-hidden="true" focusable="false">
        <g className={busy ? "co-body is-busy" : "co-body"}>
          <line x1="15" y1="1.6" x2="15" y2="4.4" className="co-antenna" />
          <circle cx="15" cy="1.8" r="1.3" className="co-eye" />
          <rect x="6" y="4.4" width="18" height="12" rx="5.2" className="co-head" />
          <rect x="8.6" y="7.4" width="12.8" height="6" rx="3" className="co-visor" />
          <circle cx="12.3" cy="10.4" r="1.4" className="co-eye" />
          <circle cx="17.7" cy="10.4" r="1.4" className="co-eye" />
          <rect x="10" y="17" width="10" height="5" rx="2.2" className="co-torso" />
        </g>
        <rect x="7.4" y="23.2" width="15.2" height="7.6" rx="1.2" className="co-monitor" />
        <Screen motion={motion} />
        <rect x="1" y="30.6" width="28" height="3" rx="1" className="co-desk" />
      </svg>
      <span className="co-worker-label">{role.title}</span>
    </button>
  );
}

export default memo(AgentWorker);
