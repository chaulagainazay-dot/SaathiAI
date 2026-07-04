"use client";
import { usePathname } from "next/navigation";

const TITLES = {
  "/": ["MONDAY · 3 JULY 2026", "Good morning, Ajay."],
  "/mission": ["SYSTEM · ALL DEPARTMENTS NOMINAL", "Mission Control"],
  "/finance": ["DEPARTMENT · FINANCE INTELLIGENCE", "Finance"],
  "/knowledge": ["EXPLORE · KNOWLEDGE GRAPH", "Knowledge"],
};

export default function TopBar({ onSearch }) {
  const path = usePathname();
  const [eyebrow, title] = TITLES[path] || ["DEPARTMENT", "Workspace"];
  return (
    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between",
      padding: "34px 56px 0" }}>
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1 className="display" style={{ fontSize: 30, marginTop: 6, color: "var(--color-ink-100)" }}>{title}</h1>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 6 }}>
        <span className="mono" style={{ fontSize: 11, letterSpacing: "0.14em", color: "var(--color-ink-400)" }}>
          07:42&nbsp;&nbsp;KATHMANDU
        </span>
        <button onClick={onSearch} className="mono"
          style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 14px",
            borderRadius: 999, fontSize: 10, letterSpacing: "0.1em", color: "#C4CFE6",
            background: "rgba(143,160,196,0.10)", border: "1px solid rgba(143,160,196,0.35)", cursor: "pointer" }}>
          ⌘K · SEARCH
        </button>
        <div style={{ width: 30, height: 30, borderRadius: "50%", background: "#DCE6FA",
          display: "flex", alignItems: "center", justifyContent: "center", color: "#0A1120",
          fontWeight: 700, fontSize: 13, boxShadow: "0 0 18px rgba(143,180,255,0.5)" }}>A</div>
      </div>
    </div>
  );
}
