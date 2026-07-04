"use client";
import { AnimatePresence, motion } from "framer-motion";
import { quickActions } from "@/lib/data";
import { color } from "@/lib/departments";
import { Eyebrow } from "@/components/ui";

export default function QuickSheet({ open, onClose }) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="m-sheet-back" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            exit={{ opacity: 0 }} onClick={onClose} />
          <motion.div className="m-sheet" initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 34 }}>
            <div style={{ width: 40, height: 4, borderRadius: 4, background: "rgba(255,255,255,0.18)",
              margin: "0 auto 18px" }} />
            <Eyebrow>Quick Actions</Eyebrow>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 14, marginTop: 16 }}>
              {quickActions.map((a) => (
                <button key={a.label} onClick={onClose}
                  style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8,
                    background: "none", border: "none", cursor: "pointer" }}>
                  <span style={{ width: 54, height: 54, borderRadius: 18, display: "flex", alignItems: "center",
                    justifyContent: "center", fontSize: 24, background: `${color(a.dept)}1c`,
                    border: `1px solid ${color(a.dept)}44` }}>{a.icon}</span>
                  <span style={{ fontSize: 10.5, color: "var(--color-ink-300)", textAlign: "center", lineHeight: 1.2 }}>{a.label}</span>
                </button>
              ))}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
