"use client";
import { AnimatePresence, motion } from "framer-motion";
import { home } from "@/lib/data";
import { DEPARTMENTS } from "@/lib/departments";
import { Pill } from "./ui";

// Press Space → everything disappears. One decision. Like JARVIS.
export default function CeoMode({ open, onClose }) {
  const a = home.actions[0];
  const color = DEPARTMENTS[a.dept]?.color;
  return (
    <AnimatePresence>
      {open && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          onClick={onClose}
          style={{ position: "fixed", inset: 0, zIndex: 90, background: "rgba(3,5,11,0.86)",
            backdropFilter: "blur(14px)", display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center" }}>
          <motion.div initial={{ scale: 0.94, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.96, opacity: 0 }} transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            onClick={(e) => e.stopPropagation()} style={{ textAlign: "center", maxWidth: 640 }}>
            <div className="eyebrow" style={{ color }}>{DEPARTMENTS[a.dept]?.name} · Today's highest priority</div>
            <h2 className="display" style={{ fontSize: 42, margin: "18px 0 10px", color: "var(--color-ink-100)",
              lineHeight: 1.15 }}>{a.title}</h2>
            <p className="mono" style={{ color: "var(--color-ink-400)", fontSize: 13, letterSpacing: "0.06em" }}>{a.meta}</p>
            <div style={{ display: "flex", gap: 14, justifyContent: "center", marginTop: 36 }}>
              <Pill color="#4FD07A" filled={0.16} onClick={onClose}>Approve</Pill>
              <Pill color="#FF5A5A" filled={0.14} onClick={onClose}>Reject</Pill>
              <Pill color="#8FB4FF" filled={0.12} onClick={onClose}>Ask Saathi</Pill>
            </div>
            <div className="eyebrow" style={{ marginTop: 40, opacity: 0.5 }}>Press Space or Esc to exit</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
