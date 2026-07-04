"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import { saathiExamples } from "@/lib/data";
import { Eyebrow } from "@/components/ui";

export default function MobileSaathi() {
  const [listening, setListening] = useState(false);
  const [said, setSaid] = useState(null);

  return (
    <div className="m-page" style={{ minHeight: "70vh", justifyContent: "space-between" }}>
      <div>
        <div className="m-card">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="pulse" style={{ width: 9, height: 9, borderRadius: "50%", background: "#8FB4FF", boxShadow: "0 0 12px #8FB4FF" }} />
            <Eyebrow>Saathi</Eyebrow>
          </div>
          <p style={{ fontSize: 15, color: "var(--color-ink-200)", marginTop: 12, lineHeight: 1.5 }}>
            {said ? <>You said: <span style={{ color: "#DCE6FA" }}>“{said}”</span><br /><span style={{ color: "var(--color-ink-400)", fontSize: 13 }}>Working on it…</span></>
              : "Good morning, Ajay. Tap the mic and speak — record revenue, approve a trade, or ask how today is going."}
          </p>
        </div>

        <div style={{ marginTop: 20 }}>
          <Eyebrow style={{ padding: "0 4px 10px" }}>Try saying</Eyebrow>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {saathiExamples.map((ex) => (
              <button key={ex} onClick={() => setSaid(ex)}
                style={{ textAlign: "left", padding: "14px 16px", borderRadius: 16, cursor: "pointer",
                  background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)",
                  color: "var(--color-ink-200)", fontSize: 14 }}>
                “{ex}”
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* mic */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14, padding: "24px 0 8px" }}>
        <motion.button onPointerDown={() => setListening(true)} onPointerUp={() => setListening(false)}
          animate={listening ? { scale: 1.08 } : { scale: 1 }} transition={{ type: "spring", stiffness: 300 }}
          style={{ width: 88, height: 88, borderRadius: "50%", border: "none", cursor: "pointer", fontSize: 34,
            background: "radial-gradient(circle at 38% 35%, #ffffff, #9fc0ff)", color: "#0A1120",
            boxShadow: listening ? "0 0 50px rgba(143,180,255,0.9)" : "0 0 30px rgba(143,180,255,0.55)" }}>
          🎤
        </motion.button>
        <span className="mono" style={{ fontSize: 11, color: "var(--color-ink-400)" }}>
          {listening ? "Listening…" : "Hold to speak"}
        </span>
      </div>
    </div>
  );
}
