"use client";
import { useRouter, usePathname } from "next/navigation";

const TABS = [
  { key: "home", label: "Home", route: "/", icon: "🏠" },
  { key: "mission", label: "Mission", route: "/mission", icon: "🧠" },
  { key: "add" },
  { key: "saathi", label: "Saathi", route: "/saathi", icon: "💬" },
  { key: "me", label: "Me", route: "/me", icon: "👤" },
];

export default function MobileTabBar({ onAdd }) {
  const router = useRouter();
  const path = usePathname();
  return (
    <nav className="m-tabs">
      {TABS.map((t) =>
        t.key === "add" ? (
          <button key="add" className="m-fab" onClick={onAdd} aria-label="Quick actions">+</button>
        ) : (
          <button key={t.key} className="m-tab" data-active={path === t.route}
            onClick={() => router.push(t.route)}>
            <span style={{ fontSize: 20, lineHeight: 1 }}>{t.icon}</span>
            <span>{t.label}</span>
          </button>
        )
      )}
    </nav>
  );
}
