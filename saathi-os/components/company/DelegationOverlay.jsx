"use client";

// Draws the live delegation path (owner → Saathi → … → busiest specialist) over
// the building. Measured from [data-role-id] elements only when the path
// changes or the viewport resizes — no animation loop. The dash animation is a
// CSS transform/offset and is disabled under prefers-reduced-motion.

import { useEffect, useLayoutEffect, useState } from "react";

export default function DelegationOverlay({ containerRef, path }) {
  const [segs, setSegs] = useState([]);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const key = path.join(">");

  const measure = () => {
    const root = containerRef.current;
    if (!root || path.length < 2) { setSegs([]); return; }
    const box = root.getBoundingClientRect();
    setSize({ w: box.width, h: box.height });
    const pts = path.map((id) => {
      const el = root.querySelector(`[data-role-id="${CSS.escape(id)}"]`);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.left - box.left + r.width / 2, y: r.top - box.top + r.height / 2 };
    }).filter(Boolean);
    const out = [];
    for (let i = 1; i < pts.length; i += 1) out.push([pts[i - 1], pts[i]]);
    setSegs(out);
  };

  useLayoutEffect(measure, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (typeof ResizeObserver === "undefined" || !containerRef.current) return undefined;
    const ro = new ResizeObserver(() => measure());
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!segs.length) return null;
  return (
    <svg className="co-overlay" width={size.w} height={size.h} aria-hidden="true" focusable="false">
      {segs.map(([a, b], i) => {
        const mx = (a.x + b.x) / 2;
        const my = Math.min(a.y, b.y) - 24;
        return (
          <g key={i}>
            <path className="co-trace-path" d={`M${a.x},${a.y} Q${mx},${my} ${b.x},${b.y}`} />
            <circle className="co-trace-node" cx={b.x} cy={b.y} r="3.2" />
          </g>
        );
      })}
    </svg>
  );
}
