"use client";
import { useMemo } from "react";

// Deterministic, patient starfield — a calm, drifting particle field.
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export default function Stars({ count = 140 }) {
  const stars = useMemo(() => {
    const r = mulberry32(11);
    return Array.from({ length: count }, () => {
      const s = r();
      return {
        left: r() * 100,
        top: r() * 100,
        size: 0.5 + s * s * 1.8,
        opacity: 0.06 + s * s * s * 0.5,
        dur: 6 + r() * 10,
        delay: -r() * 10,
      };
    });
  }, [count]);

  return (
    <div className="stars">
      {stars.map((st, i) => (
        <span
          key={i}
          style={{
            position: "absolute",
            left: `${st.left}%`,
            top: `${st.top}%`,
            width: st.size,
            height: st.size,
            borderRadius: "50%",
            background: "#9fb2d8",
            opacity: st.opacity,
            animation: `floaty ${st.dur}s ease-in-out ${st.delay}s infinite alternate`,
          }}
        />
      ))}
    </div>
  );
}
