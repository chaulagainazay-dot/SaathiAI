"use client";
import { AnimatePresence, motion } from "framer-motion";
import { color } from "@/lib/departments";
import { Eyebrow } from "@/components/ui";

const QUICK_ACTIONS = [
  { label: "Record Revenue", icon: "💰", dept: "CAFETERIA" },
  { label: "Add Expense", icon: "🧾", dept: "FINANCE" },
  { label: "Approve Trade", icon: "✅", dept: "FINANCE" },
  { label: "Publish Video", icon: "🎬", dept: "AI STUDIO" },
  { label: "Cafeteria Sales", icon: "🍚", dept: "CAFETERIA" },
  { label: "Capture Idea", icon: "💡", dept: "KNOWLEDGE" },
  { label: "Scan Receipt", icon: "📸", dept: "BUSINESS" },
  { label: "Voice Note", icon: "🎤", dept: "MEMORY" },
];

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
              {QUICK_ACTIONS.map((a) => (
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
