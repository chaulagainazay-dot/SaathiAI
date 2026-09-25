"use client";
// SaathiOS Orbit — the agent constellation.
//
// Deliberately restrained: the design system says "premium, calm, legible; not neon,
// not casino". So this takes the *structure* of a command constellation (a core with
// specialists in orbit, connective edges, status by colour) and renders it in the
// SOVEREIGN_ORBIT register — deep navy ground, one warm core, cool low-alpha edges,
// clinical mono labels. Glow is a hairline, not a bloom.
//
// Styling is TOKEN-ONLY (var(--…)). No hex literals, no inline colour values — this
// component is the reference for the token migration the UI audit calls for.
import { useMemo } from "react";
import { layoutOrbit, orbitEdges, orbitSummary, orbitTextSummary, CORE_ID } from "@/lib/orbit";

export default function AgentOrbit({
  agents = [],
  size = 720,
  coreLabel = "SaathiOS",
  coreSub = "core",
  onSelect,
  selectedId = "",
}) {
  const layout = useMemo(() => layoutOrbit(agents, { size }), [agents, size]);
  const edges = useMemo(() => orbitEdges(layout), [layout]);
  const summary = useMemo(() => orbitSummary(agents), [agents]);
  const text = orbitTextSummary(agents);

  return (
    <div className="orbit-wrap">
      <svg
        className="orbit-svg"
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={text}
        data-testid="agent-orbit"
      >
        <defs>
          <radialGradient id="orbit-core-glow">
            <stop offset="0%" stopColor="var(--orbit-core)" stopOpacity="0.55" />
            <stop offset="70%" stopColor="var(--orbit-core)" stopOpacity="0.10" />
            <stop offset="100%" stopColor="var(--orbit-core)" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* orbit rings — structure, not decoration */}
        {[0.42, 0.72].map((f) => (
          <circle
            key={f}
            className="orbit-ring"
            cx={size / 2}
            cy={size / 2}
            r={(size / 2) * f}
          />
        ))}

        {/* connective tissue */}
        <g className="orbit-edges">
          {edges.map((e) => (
            <line
              key={`${e.from}-${e.to}`}
              x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2}
              className={`orbit-edge orbit-edge--${e.kind}`}
            />
          ))}
        </g>

        {/* core */}
        <g className="orbit-core" data-testid="orbit-core">
          <circle cx={layout.core.x} cy={layout.core.y} r={size * 0.14} fill="url(#orbit-core-glow)" />
          <circle cx={layout.core.x} cy={layout.core.y} r={size * 0.052} className="orbit-core-ring" />
          <circle cx={layout.core.x} cy={layout.core.y} r={size * 0.018} className="orbit-core-dot" />
          <text x={layout.core.x} y={layout.core.y + size * 0.095} className="orbit-core-label">
            {coreLabel}
          </text>
          <text x={layout.core.x} y={layout.core.y + size * 0.125} className="orbit-core-sub">
            {coreSub}
          </text>
        </g>

        {/* agents */}
        <g className="orbit-nodes">
          {layout.nodes.map((n) => {
            const selected = n.id === selectedId;
            const anchor = n.x < size / 2 ? "end" : "start";
            const dx = n.x < size / 2 ? -14 : 14;
            return (
              <g
                key={n.id}
                className={`orbit-node${selected ? " is-selected" : ""}`}
                onClick={onSelect ? () => onSelect(n) : undefined}
                tabIndex={onSelect ? 0 : undefined}
                role={onSelect ? "button" : undefined}
                aria-label={onSelect ? `${n.label} — ${n.tone}` : undefined}
                onKeyDown={
                  onSelect
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(n); }
                      }
                    : undefined
                }
              >
                <circle cx={n.x} cy={n.y} r={13} className="orbit-node-halo" style={{ fill: n.color }} />
                <circle cx={n.x} cy={n.y} r={5.5} className="orbit-node-dot" style={{ fill: n.color }} />
                <text x={n.x + dx} y={n.y + 4} textAnchor={anchor} className="orbit-node-label">
                  {n.label}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      {/* text equivalent — never image-only */}
      <p className="orbit-sr" data-testid="orbit-text-summary">{text}</p>
      <ul className="orbit-legend" data-testid="orbit-legend">
        <li><span className="orbit-key" style={{ background: "var(--status-success)" }} />healthy {summary.healthy}</li>
        <li><span className="orbit-key" style={{ background: "var(--status-warning)" }} />attention {summary.attention}</li>
        <li><span className="orbit-key" style={{ background: "var(--status-neutral)" }} />total {summary.total}</li>
      </ul>
    </div>
  );
}

export { CORE_ID };
