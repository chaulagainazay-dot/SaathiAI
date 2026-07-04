"use client";
import { motion, useMotionValue, useTransform, animate } from "framer-motion";
import { useEffect } from "react";

export function Panel({ className = "", children, delay = 0, soft = false, style }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
      className={`${soft ? "glass-soft" : "glass"} ${className}`}
      style={style}
    >
      {children}
    </motion.div>
  );
}

export function Eyebrow({ children, style, className = "" }) {
  return <div className={`eyebrow ${className}`} style={style}>{children}</div>;
}

export function Pill({ color = "#8FA0C4", children, filled = 0.14, onClick, className = "" }) {
  return (
    <button
      onClick={onClick}
      className={`mono ${className}`}
      style={{
        padding: "6px 14px", borderRadius: 999, fontSize: 10, letterSpacing: "0.12em",
        color, background: `${color}${toHex(filled)}`, border: `1px solid ${color}66`,
        textTransform: "uppercase", cursor: onClick ? "pointer" : "default",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </button>
  );
}

export function Dot({ color, size = 8, ring = true }) {
  return (
    <span style={{ position: "relative", display: "inline-flex", width: size, height: size }}>
      <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: color,
        boxShadow: `0 0 10px ${color}88` }} />
      {ring && <span style={{ position: "absolute", inset: -3, borderRadius: "50%",
        border: `1px solid ${color}66` }} />}
    </span>
  );
}

export function Bar({ frac, color, label, value }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span className="mono" style={{ fontSize: 10.5, color: "var(--color-ink-400)" }}>{label}</span>
        <span className="mono" style={{ fontSize: 10.5, color: "var(--color-ink-200)" }}>{value}</span>
      </div>
      <div style={{ height: 5, borderRadius: 3, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
        <motion.div
          initial={{ width: 0 }} animate={{ width: `${Math.max(2, frac * 100)}%` }}
          transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
          style={{ height: "100%", borderRadius: 3, background: color, boxShadow: `0 0 12px ${color}66` }}
        />
      </div>
    </div>
  );
}

// animated counting number
export function Counter({ to, format = (v) => Math.round(v).toString(), className = "", style }) {
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => format(v));
  useEffect(() => {
    const controls = animate(mv, to, { duration: 1.1, ease: [0.22, 1, 0.36, 1] });
    return controls.stop;
  }, [to, mv]);
  return <motion.span className={className} style={style}>{text}</motion.span>;
}

// SVG progress ring
export function Ring({ value, color, size = 200, stroke = 12, label, sub }) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke="rgba(255,255,255,0.10)" strokeWidth={stroke} />
        <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: circ * (1 - value) }}
          transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
          style={{ filter: `drop-shadow(0 0 10px ${color}66)` }} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center" }}>
        {label != null && <Counter to={label} className="display"
          style={{ fontSize: size * 0.24, color: "var(--color-ink-100)", lineHeight: 1 }} />}
        {sub && <div className="eyebrow" style={{ marginTop: 8 }}>{sub}</div>}
      </div>
    </div>
  );
}

function toHex(a) {
  const v = Math.round(Math.max(0, Math.min(1, a)) * 255).toString(16).padStart(2, "0");
  return v;
}
