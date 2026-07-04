"use client";
import { useRouter, usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { DOCK, DEPARTMENTS } from "@/lib/departments";

export default function Dock() {
  const router = useRouter();
  const path = usePathname();
  return (
    <div style={{ position: "fixed", bottom: 22, left: 0, right: 0, display: "flex",
      justifyContent: "center", zIndex: 40, pointerEvents: "none" }}>
      <motion.div
        initial={{ y: 40, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.3, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="glass"
        style={{ display: "flex", gap: 10, padding: "10px 18px", borderRadius: 30, pointerEvents: "auto" }}>
        {DOCK.map((key) => {
          const d = DEPARTMENTS[key];
          const active = path === d.route;
          return (
            <button key={key} title={d.name} onClick={() => router.push(d.route)}
              style={{ position: "relative", width: 34, height: 34, borderRadius: "50%",
                display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer",
                background: "transparent", border: "none" }}>
              <motion.span whileHover={{ scale: 1.25 }} transition={{ type: "spring", stiffness: 400, damping: 20 }}
                style={{ width: active ? 20 : 18, height: active ? 20 : 18, borderRadius: "50%",
                  background: active ? d.color : `${d.color}28`,
                  border: `1.4px solid ${d.color}${active ? "" : "99"}`,
                  boxShadow: active ? `0 0 16px ${d.color}aa` : "none" }} />
              {active && <span style={{ position: "absolute", bottom: -6, width: 4, height: 4,
                borderRadius: "50%", background: d.color, boxShadow: `0 0 8px ${d.color}` }} />}
            </button>
          );
        })}
        <div style={{ width: 1, background: "rgba(255,255,255,0.1)", margin: "4px 4px" }} />
        <button title="Settings" style={{ width: 34, height: 34, borderRadius: "50%",
          border: "1px solid rgba(128,144,174,0.5)", background: "transparent", cursor: "pointer" }} />
      </motion.div>
    </div>
  );
}
