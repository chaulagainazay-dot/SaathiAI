"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import { graph } from "@/lib/data";
import { Panel, Eyebrow } from "@/components/ui";

const W = 1200, H = 620;

export default function Knowledge() {
  const [hover, setHover] = useState(null);
  const N = graph.nodes;
  const px = (k) => ({ x: N[k].x * W, y: N[k].y * H });

  return (
    <div style={{ maxWidth: 1620, margin: "0 auto" }}>
      {/* search */}
      <div style={{ display: "flex", justifyContent: "center", marginBottom: 20 }}>
        <div className="glass" style={{ width: 560, padding: "12px 20px", display: "flex", alignItems: "center", gap: 12 }}>
          <span className="mono" style={{ color: "var(--color-ink-500)", fontSize: 12 }}>⌕</span>
          <input placeholder="Search — goal, strategy, capability, evidence…"
            style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: "var(--color-ink-200)", fontSize: 14 }} />
        </div>
      </div>

      <Panel style={{ padding: 0, position: "relative", overflow: "hidden" }}>
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
          {graph.edges.map(([a, b], i) => {
            const p = px(a), q = px(b);
            const active = hover && (hover === a || hover === b);
            const mx = (p.x + q.x) / 2, my = (p.y + q.y) / 2 + 16;
            return (
              <path key={i} d={`M ${p.x} ${p.y} Q ${mx} ${my} ${q.x} ${q.y}`} fill="none"
                stroke={active ? "#8FB4FF" : "#5C79B8"} strokeOpacity={active ? 0.7 : 0.28}
                strokeWidth={active ? 1.6 : 1} />
            );
          })}
          {Object.entries(N).map(([k, n]) => {
            const p = px(k);
            return (
              <g key={k} onMouseEnter={() => setHover(k)} onMouseLeave={() => setHover(null)} style={{ cursor: "pointer" }}>
                <motion.circle cx={p.x} cy={p.y} r={n.r + 6} fill={n.color} opacity={0.14}
                  initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.1, type: "spring", stiffness: 200 }} />
                <circle cx={p.x} cy={p.y} r={n.r} fill={n.color}
                  style={{ filter: `drop-shadow(0 0 8px ${n.color}aa)` }} />
                <circle cx={p.x - n.r * 0.35} cy={p.y - n.r * 0.35} r={n.r * 0.18} fill="#fff" opacity="0.75" />
                <text x={p.x} y={p.y - n.r - 10} textAnchor="middle" fill={n.color}
                  className="mono" style={{ fontSize: 9, letterSpacing: "0.06em", fontWeight: 600 }}>{k}</text>
                <text x={p.x} y={p.y - n.r - 22} textAnchor="middle" fill="#93A0BC" style={{ fontSize: 9.5 }}>{n.label}</text>
              </g>
            );
          })}
        </svg>

        {/* legend */}
        <div className="glass-soft" style={{ position: "absolute", left: 24, bottom: 24, padding: 18, width: 300 }}>
          <Eyebrow>Node Types</Eyebrow>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 16px", marginTop: 12 }}>
            {graph.types.map((t) => (
              <div key={t.name} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: t.color, boxShadow: `0 0 8px ${t.color}` }} />
                <span style={{ fontSize: 11.5, color: "var(--color-ink-200)" }}>{t.name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* zoom controls */}
        <div style={{ position: "absolute", right: 24, bottom: 24, display: "flex", flexDirection: "column", gap: 10 }}>
          {["+", "−"].map((s) => (
            <div key={s} className="glass-soft" style={{ width: 42, height: 38, display: "flex", alignItems: "center",
              justifyContent: "center", cursor: "pointer", color: "var(--color-ink-300)", fontSize: 18 }}>{s}</div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
