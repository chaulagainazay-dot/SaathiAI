"use client";
import { usePathname } from "next/navigation";

const TITLES = {
  "/": { eyebrow: "MONDAY · 3 JULY", title: "Good morning, Ajay 👋" },
  "/mission": { eyebrow: "SYSTEM", title: "Mission Control" },
  "/finance": { eyebrow: "DEPARTMENT", title: "Finance" },
  "/saathi": { eyebrow: "COMPANION", title: "Saathi" },
  "/me": { eyebrow: "ACCOUNT", title: "You" },
  "/knowledge": { eyebrow: "EXPLORE", title: "Knowledge" },
  "/cafeteria": { eyebrow: "OPERATIONS", title: "Cafeteria" },
  "/studio": { eyebrow: "PRODUCTION", title: "AI Studio" },
};

export default function MobileTopBar() {
  const path = usePathname();
  const t = TITLES[path] || { eyebrow: "WORKSPACE", title: "SaathiAI" };
  return (
    <div className="m-top">
      <div className="eyebrow">{t.eyebrow}</div>
      <h1 className="display" style={{ fontSize: 25, marginTop: 4, color: "var(--color-ink-100)" }}>{t.title}</h1>
    </div>
  );
}
