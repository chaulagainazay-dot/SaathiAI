"use client";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { DEPARTMENTS } from "@/lib/departments";

// pages with a bespoke eyebrow/title; everything else derives from the route
const TITLES = {
  "/": ["EXECUTIVE · CEO HOME", "Good morning, Ajay."],
  "/mission": ["SYSTEM · ALL DEPARTMENTS NOMINAL", "Mission Control"],
};

// route → friendly name, so no page shows a generic "Workspace"
const ROUTE_NAME = Object.fromEntries(
  Object.values(DEPARTMENTS).map((d) => [d.route, d.name])
);

function deriveTitle(path) {
  if (TITLES[path]) return TITLES[path];
  if (ROUTE_NAME[path]) return [`SAATHIOS · ${ROUTE_NAME[path].toUpperCase()}`, ROUTE_NAME[path]];
  const seg = path.split("/").filter(Boolean);
  if (seg.length) {
    const name = seg[seg.length - 1].replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    return [`SAATHIOS · ${seg[0].toUpperCase()}`, name];
  }
  return ["SAATHIOS", "SaathiOS"];
}

export default function TopBar({ onSearch }) {
  const path = usePathname();
  const [eyebrow, title] = deriveTitle(path);
  const [clock, setClock] = useState("");
  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString("en-GB",
      { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kathmandu" }));
    tick();
    const id = setInterval(tick, 1000 * 30);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between",
      padding: "34px 56px 0" }}>
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1 className="display" style={{ fontSize: 30, marginTop: 6, color: "var(--color-ink-100)" }}>{title}</h1>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 6 }}>
        <span className="mono" style={{ fontSize: 11, letterSpacing: "0.14em", color: "var(--color-ink-400)" }}>
          {clock}&nbsp;&nbsp;KATHMANDU
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
