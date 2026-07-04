"use client";
import { useState, useMemo, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { DEPARTMENTS } from "@/lib/departments";

const COMMANDS = [
  { label: "Open CEO Home", dept: "EXECUTIVE", route: "/" },
  { label: "Open Mission Control", dept: "MISSION", route: "/mission" },
  { label: "Open Finance", dept: "FINANCE", route: "/finance" },
  { label: "Open Knowledge Graph", dept: "KNOWLEDGE", route: "/knowledge" },
  { label: "Approve recommendation", dept: "FINANCE", route: "/finance" },
  { label: "Review Trade Journal", dept: "FINANCE", route: "/finance" },
  { label: "Run AI Studio", dept: "AI STUDIO", route: "/studio" },
  { label: "Publish video", dept: "AI STUDIO", route: "/studio" },
  { label: "Record revenue", dept: "CAFETERIA", route: "/cafeteria" },
  { label: "Review Opportunity #218", dept: "OPPORTUNITY", route: "/finance" },
];

export default function CommandPalette({ open, onClose }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef(null);

  const results = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? COMMANDS.filter((c) => c.label.toLowerCase().includes(s)) : COMMANDS;
  }, [q]);

  useEffect(() => { if (open) { setQ(""); setSel(0); setTimeout(() => inputRef.current?.focus(), 40); } }, [open]);
  useEffect(() => { setSel(0); }, [q]);

  const go = (c) => { if (!c) return; onClose(); router.push(c.route); };

  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(results.length - 1, s + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(0, s - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); go(results[sel]); }
    else if (e.key === "Escape") { onClose(); }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          onClick={onClose}
          style={{ position: "fixed", inset: 0, zIndex: 80, background: "rgba(4,6,13,0.6)",
            backdropFilter: "blur(6px)", display: "flex", alignItems: "flex-start", justifyContent: "center",
            paddingTop: "16vh" }}>
          <motion.div initial={{ y: -18, opacity: 0, scale: 0.98 }} animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: -12, opacity: 0 }} transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            onClick={(e) => e.stopPropagation()} className="glass"
            style={{ width: 620, maxWidth: "90vw", padding: 8, borderRadius: 22 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px" }}>
              <span className="mono" style={{ color: "var(--color-ink-500)", fontSize: 12 }}>⌘K</span>
              <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
                placeholder="Search commands, departments, actions…"
                style={{ flex: 1, background: "transparent", border: "none", outline: "none",
                  color: "var(--color-ink-100)", fontSize: 16, fontFamily: "var(--font-ui)" }} />
            </div>
            <div style={{ height: 1, background: "var(--color-line)" }} />
            <div style={{ maxHeight: 320, overflowY: "auto", padding: 6 }}>
              {results.map((c, i) => {
                const color = DEPARTMENTS[c.dept]?.color;
                return (
                  <div key={c.label} onMouseEnter={() => setSel(i)} onClick={() => go(c)}
                    style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 14px",
                      borderRadius: 12, cursor: "pointer",
                      background: i === sel ? "rgba(255,255,255,0.06)" : "transparent" }}>
                    <span style={{ width: 7, height: 7, borderRadius: "50%", background: color,
                      boxShadow: `0 0 10px ${color}` }} />
                    <span style={{ color: "var(--color-ink-200)", fontSize: 14 }}>{c.label}</span>
                    <span className="eyebrow" style={{ marginLeft: "auto", color }}>{DEPARTMENTS[c.dept]?.short}</span>
                  </div>
                );
              })}
              {results.length === 0 && (
                <div style={{ padding: 24, textAlign: "center", color: "var(--color-ink-500)" }}>No matches.</div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
