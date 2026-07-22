"use client";
import { motion } from "framer-motion";
import { DEPARTMENTS, color } from "@/lib/departments";
import { useLive } from "./live/LiveProvider";

// Visual layout: department positions on 3 orbital rings (not data — pure geometry)
const UNIVERSE = [
  { dept: "EXECUTIVE", ring: 1, angle: 90 },
  { dept: "FINANCE", ring: 1, angle: 210 },
  { dept: "MISSION", ring: 1, angle: 330 },
  { dept: "AI STUDIO", ring: 2, angle: 40 },
  { dept: "KNOWLEDGE", ring: 2, angle: 130 },
  { dept: "LEARNING", ring: 2, angle: 220 },
  { dept: "DISCOVERY", ring: 2, angle: 315 },
  { dept: "CRYPTO", ring: 3, angle: 15 },
  { dept: "TRAVEL", ring: 3, angle: 100 },
  { dept: "CAFETERIA", ring: 3, angle: 200 },
  { dept: "OPPORTUNITY", ring: 3, angle: 270 },
  { dept: "BUSINESS", ring: 3, angle: 335 },
];

const FLOWS = [
  { from: "LEARNING", to: "AI STUDIO", color: "#B78CFF" },
  { from: "AI STUDIO", to: "FINANCE", color: "#FFB25A" },
  { from: "KNOWLEDGE", to: "EXECUTIVE", color: "#6E9BFF" },
];

const SIZE = 720;
const CX = SIZE / 2, CY = SIZE / 2;
const RADII = { 1: 150, 2: 245, 3: 330 };

function pos(ring, angle) {
  const a = (angle * Math.PI) / 180;
  return { x: CX + RADII[ring] * Math.cos(a), y: CY - RADII[ring] * Math.sin(a) };
}
const P = Object.fromEntries(UNIVERSE.map((n) => [n.dept, pos(n.ring, n.angle)]));

export default function Universe() {
  const { isActive } = useLive();
  return (
    <div style={{ position: "relative", width: SIZE, height: SIZE, margin: "0 auto" }}>
      <svg width={SIZE} height={SIZE} style={{ position: "absolute", inset: 0 }}>
        {[1, 2, 3].map((r) => (
          <circle key={r} cx={CX} cy={CY} r={RADII[r]} fill="none" stroke="rgba(110,125,154,0.22)" strokeWidth="1" />
        ))}
        {/* filaments */}
        {UNIVERSE.map((n) => (
          <line key={n.dept} x1={CX} y1={CY} x2={P[n.dept].x} y2={P[n.dept].y}
            stroke={color(n.dept)} strokeOpacity="0.16" strokeWidth="1" />
        ))}
        {/* living flows */}
        {FLOWS.map((f, i) => {
          const a = P[f.from], b = P[f.to];
          return (
            <g key={i}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={f.color} strokeOpacity="0.28" strokeWidth="6" />
              <line className="flow" x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={f.color} strokeOpacity="0.9" strokeWidth="2" />
            </g>
          );
        })}
      </svg>

      {/* nodes */}
      {UNIVERSE.map((n, i) => {
        const p = P[n.dept], c = color(n.dept);
        const cosd = Math.cos((n.angle * Math.PI) / 180);
        const right = cosd > 0.25, left = cosd < -0.25;
        const live = isActive(n.dept);
        return (
          <motion.div key={n.dept}
            initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: live ? 1.18 : 1 }}
            transition={{ delay: 0.2 + i * 0.04, type: "spring", stiffness: 260, damping: 18 }}
            style={{ position: "absolute", left: p.x, top: p.y, transform: "translate(-50%,-50%)" }}>
            {live && (
              <motion.div initial={{ scale: 0.6, opacity: 0.9 }} animate={{ scale: 2.6, opacity: 0 }}
                transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
                style={{ position: "absolute", inset: -12, borderRadius: "50%", border: `1.5px solid ${c}` }} />
            )}
            <motion.div className="pulse" style={{ position: "absolute", inset: live ? -22 : -14, borderRadius: "50%",
              background: `radial-gradient(circle, ${c}${live ? "aa" : "66"}, transparent 70%)` }} />
            <div style={{ width: 24, height: 24, borderRadius: "50%",
              background: `radial-gradient(circle at 35% 35%, ${c}, ${c}66)`,
              border: `1.4px solid ${c}`, boxShadow: `0 0 ${live ? 32 : 18}px ${c}${live ? "" : "aa"}` }} />
            <div className="mono" style={{ position: "absolute", top: "50%", fontSize: 9.5, letterSpacing: "0.12em",
              color: c, whiteSpace: "nowrap", transform: "translateY(-50%)",
              ...(right ? { left: 28 } : left ? { right: 28 } : { left: "50%", top: 30, transform: "translateX(-50%)" }) }}>
              {DEPARTMENTS[n.dept]?.name.toUpperCase()}
            </div>
          </motion.div>
        );
      })}

      {/* sovereign center */}
      <div style={{ position: "absolute", left: CX, top: CY, transform: "translate(-50%,-50%)" }}>
        <div className="pulse" style={{ position: "absolute", inset: -60, borderRadius: "50%",
          background: "radial-gradient(circle, rgba(143,180,255,0.35), transparent 70%)" }} />
        <div style={{ width: 54, height: 54, borderRadius: "50%",
          background: "radial-gradient(circle at 38% 35%, #ffffff, #9fc0ff)",
          border: "1.6px solid #ffffff", boxShadow: "0 0 40px rgba(200,225,255,0.7)",
          display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span className="display" style={{ fontSize: 14, color: "#0A1120", letterSpacing: "0.18em" }}>AJAY</span>
        </div>
      </div>
    </div>
  );
}
