"use client";
import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useLive } from "./LiveProvider";
import { DEPARTMENTS, color } from "@/lib/departments";

const TONE = { up: "#4FD07A", warn: "#E8B84B", critical: "#FF5A5A", info: "#8FB4FF" };

function Toast({ n, onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 6500);   // auto-dismiss
    return () => clearTimeout(t);
  }, [onClose]);
  const c = color(n.dept);
  const accent = TONE[n.tone] || c;
  return (
    <motion.div layout
      initial={{ opacity: 0, x: 40, scale: 0.96 }} animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 40, scale: 0.96 }} transition={{ type: "spring", stiffness: 360, damping: 30 }}
      className="glass" style={{ padding: 14, marginBottom: 12, borderLeft: `3px solid ${c}` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: accent, boxShadow: `0 0 10px ${accent}` }} />
        <span className="eyebrow" style={{ color: c }}>{DEPARTMENTS[n.dept]?.name || n.dept}</span>
        <button onClick={onClose} style={{ marginLeft: "auto", background: "none", border: "none",
          color: "var(--color-ink-500)", cursor: "pointer", fontSize: 15, lineHeight: 1 }}>×</button>
      </div>
      <div style={{ fontSize: 13.5, color: "var(--color-ink-100)", margin: "8px 0 12px" }}>{n.title}</div>
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={onClose} style={{ padding: "7px 16px", borderRadius: 999, fontSize: 11, cursor: "pointer",
          color: accent, background: `${accent}22`, border: `1px solid ${accent}55` }}>{n.action}</button>
        <button onClick={onClose} style={{ padding: "7px 14px", borderRadius: 999, fontSize: 11, cursor: "pointer",
          color: "var(--color-ink-400)", background: "transparent", border: "1px solid rgba(255,255,255,0.12)" }}>Dismiss</button>
      </div>
    </motion.div>
  );
}

export default function LiveToasts() {
  const { notifications, dismiss } = useLive();
  const shown = notifications.slice(0, 3);
  return (
    <div className="live-toasts">
      <AnimatePresence initial={false}>
        {shown.map((n) => <Toast key={n.id} n={n} onClose={() => dismiss(n.id)} />)}
      </AnimatePresence>
    </div>
  );
}
