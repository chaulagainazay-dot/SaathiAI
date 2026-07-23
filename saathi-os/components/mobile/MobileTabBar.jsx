"use client";
import { useRouter, usePathname } from "next/navigation";
import { MOBILE_TABS } from "@/lib/navigation";

export default function MobileTabBar({ onAdd, onCopilot }) {
  const router = useRouter();
  const path = usePathname();

  return (
    <nav className="m-tabs" aria-label="Mobile companion">
      {MOBILE_TABS.map((t) => {
        if (t.action === "copilot") {
          return (
            <button
              key={t.id}
              type="button"
              className="m-fab"
              onClick={() => {
                if (onCopilot) onCopilot();
                else onAdd?.();
              }}
              aria-label="Ask Saathi"
            >
              +
            </button>
          );
        }
        const active =
          t.href === "/"
            ? path === "/"
            : path === t.href || (t.href && path?.startsWith(t.href + "/"));
        return (
          <button
            key={t.id}
            type="button"
            className="m-tab"
            data-active={active ? "true" : "false"}
            aria-current={active ? "page" : undefined}
            onClick={() => t.href && router.push(t.href)}
          >
            <span style={{ fontSize: 18, lineHeight: 1 }} aria-hidden="true">
              {t.icon}
            </span>
            <span>{t.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
