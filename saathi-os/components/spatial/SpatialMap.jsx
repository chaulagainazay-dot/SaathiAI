"use client";
/**
 * M58 — SpatialModuleNode, ConnectionLayer, SpatialMap.
 *
 * SpatialMap composes the SaathiCore, the floating module ring, and the animated
 * SVG connection layer. On desktop the modules orbit the core on a deterministic
 * ellipse; on compact viewports it degrades to an accessible node grid (no
 * absolute positioning, connections hidden) so it is usable, not just decorative.
 */
import { useEffect, useState } from "react";
import {
  MODULES,
  SIGNAL_TOKENS,
  moduleState,
  ringLayout,
  curvePath,
  connectionSignal,
  pct,
  pathD,
  round2,
} from "@/lib/spatial";
import { SaathiCore } from "./SaathiCore";
import { SpatialIcon } from "./icons";
import { StatusPulse, useReducedMotion } from "./frame";

function useMediaQuery(query) {
  const [match, setMatch] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return undefined;
    const mq = window.matchMedia(query);
    const on = () => setMatch(mq.matches);
    on();
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, [query]);
  return match;
}

/* ---- SpatialModuleNode ---- */
export function SpatialModuleNode({ module, state, selected, onSelect, style, compact = false }) {
  const tok = SIGNAL_TOKENS[state?.signal] || SIGNAL_TOKENS.idle;
  return (
    <button
      type="button"
      className="module-node"
      aria-current={selected ? "true" : undefined}
      aria-label={`${module.label}. ${state?.detail || tok.label}. Open ${module.label}.`}
      onClick={() => onSelect?.(module)}
      style={{ "--node-c": tok.color, ...(compact ? { width: "100%" } : { position: "absolute", transform: "translate(-50%, -50%)" }), ...style }}
    >
      <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ color: tok.color, display: "inline-flex" }}>
          <SpatialIcon name={module.icon} size={16} />
        </span>
        <span className="mono" style={{ fontSize: "var(--fs-xs)", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-primary)" }}>
          {module.label}
        </span>
        <StatusPulse signal={state?.signal || "idle"} size={7} label={`${module.label} ${tok.label}`} />
      </span>
      {state?.detail ? (
        <span style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
          {state.detail}
        </span>
      ) : null}
    </button>
  );
}

/* ---- ConnectionLayer — SVG paths from centre to each node ---- */
function ConnectionLayer({ points, selectedId, reduced }) {
  return (
    <svg
      className="connection-layer"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {points.map(({ module, state, pt }) => {
        const kind = connectionSignal(module, state);
        const d = pathD(curvePath({ x: 0.5, y: 0.5 }, { x: pt.x, y: pt.y }, 0.16));
        const active = selectedId === module.id;
        const dim = selectedId && !active;
        return (
          <g key={module.id} style={{ opacity: dim ? 0.28 : 1, transition: "opacity var(--motion-base)" }}>
            <path
              d={d}
              className={`connection-path connection-path--${kind}`}
              strokeWidth={active ? 1.1 : 0.6}
              vectorEffect="non-scaling-stroke"
              opacity={kind === "inactive" ? 0.5 : active ? 1 : 0.8}
            />
            {!reduced && kind !== "inactive" && (
              <path
                d={d}
                className={`connection-path connection-path--${kind} connection-flow`}
                strokeWidth={active ? 1.3 : 0.8}
                vectorEffect="non-scaling-stroke"
                opacity={active ? 0.9 : 0.5}
              />
            )}
          </g>
        );
      })}
    </svg>
  );
}

/* ---- SpatialMap ---- */
export function SpatialMap({ coreSignal, coreMetrics, data = {}, selectedId, onSelect }) {
  const reduced = useReducedMotion();
  const compact = useMediaQuery("(max-width: 900px)");

  const layout = ringLayout(MODULES.length, { cx: 0.5, cy: 0.5, rx: 0.43, ry: 0.4 });
  const nodes = MODULES.map((module, i) => ({
    module,
    state: moduleState(module.id, data),
    pt: layout[i],
  }));

  if (compact) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "var(--space-6)" }}>
        <SaathiCore signal={coreSignal} size={200} metrics={coreMetrics} />
        <div
          style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: "var(--space-3)", width: "100%" }}
          role="navigation"
          aria-label="System modules"
        >
          {nodes.map(({ module, state }) => (
            <SpatialModuleNode key={module.id} module={module} state={state} selected={selectedId === module.id} onSelect={onSelect} compact />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div
      className="spatial-map"
      style={{ position: "relative", width: "100%", aspectRatio: "1 / 0.82", maxWidth: 920, margin: "0 auto", minHeight: 560 }}
      role="navigation"
      aria-label="Spatial system map"
    >
      <ConnectionLayer points={nodes} selectedId={selectedId} reduced={reduced} />

      <div style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -50%)", zIndex: 1 }}>
        <SaathiCore signal={coreSignal} size={256} metrics={coreMetrics} />
      </div>

      {nodes.map(({ module, state, pt }, i) => (
        <div
          key={module.id}
          className={reduced ? undefined : "spatial-node-enter"}
          style={{ position: "absolute", left: pct(pt.x), top: pct(pt.y), zIndex: 2, animationDelay: reduced ? undefined : `${round2(0.04 * i)}s` }}
        >
          <SpatialModuleNode module={module} state={state} selected={selectedId === module.id} onSelect={onSelect} />
        </div>
      ))}
    </div>
  );
}
