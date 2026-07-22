"use client";
import { useRouter, usePathname } from "next/navigation";
import { NAV_GROUPS, GLOBAL_NAV, matchNavItem } from "@/lib/navigation";
import { useShellChrome } from "./ShellChromeContext";
import { IconButton } from "@/components/ui";

function NavLink({ item, expanded, active, onNavigate }) {
  const accent = item.accent || "var(--accent)";
  return (
    <button
      type="button"
      onClick={() => onNavigate(item.href)}
      aria-current={active ? "page" : undefined}
      aria-label={item.label}
      title={item.label}
      className="shell-nav-item"
      data-active={active ? "true" : "false"}
      data-risk={item.riskFlag ? "true" : "false"}
      style={{
        "--item-accent": accent,
      }}
    >
      <span className="shell-nav-icon" aria-hidden="true">{item.icon}</span>
      {expanded && (
        <span className="shell-nav-label">
          {item.label}
          {item.riskFlag && (
            <span className="shell-nav-risk" title="Risk-flagged surface">
              risk
            </span>
          )}
        </span>
      )}
      {active && <span className="shell-nav-active-bar" aria-hidden="true" />}
    </button>
  );
}

export default function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const { sidebarExpanded, toggleSidebar } = useShellChrome();
  const active = matchNavItem(pathname);

  const go = (href) => {
    if (href) router.push(href);
  };

  return (
    <aside
      className="shell-sidebar"
      data-expanded={sidebarExpanded ? "true" : "false"}
      aria-label="Primary"
    >
      <div className="shell-sidebar-head">
        <button
          type="button"
          className="shell-mark"
          onClick={() => go("/")}
          aria-label="SaathiOS Home"
          title="SaathiOS"
        >
          <span aria-hidden="true">S</span>
          {sidebarExpanded && <span className="shell-mark-text">SaathiOS</span>}
        </button>
        <IconButton
          label={sidebarExpanded ? "Collapse sidebar" : "Expand sidebar"}
          size={32}
          onClick={toggleSidebar}
          className="shell-sidebar-toggle"
        >
          {sidebarExpanded ? "«" : "»"}
        </IconButton>
      </div>

      <nav className="shell-sidebar-nav" aria-label="Product areas">
        {NAV_GROUPS.map((group) => (
          <div key={group.id} className="shell-nav-group">
            {sidebarExpanded && (
              <div className="shell-nav-group-label" id={`nav-g-${group.id}`}>
                {group.label}
              </div>
            )}
            <div role="group" aria-labelledby={sidebarExpanded ? `nav-g-${group.id}` : undefined}>
              {group.items.map((item) => (
                <NavLink
                  key={item.id}
                  item={item}
                  expanded={sidebarExpanded}
                  active={active?.id === item.id}
                  onNavigate={go}
                />
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="shell-sidebar-foot">
        {sidebarExpanded && <div className="shell-nav-group-label">Global</div>}
        {GLOBAL_NAV.filter((g) => g.id !== "evidence").map((item) => (
          <NavLink
            key={item.id}
            item={item}
            expanded={sidebarExpanded}
            active={active?.id === item.id}
            onNavigate={go}
          />
        ))}
        <NavLink
          item={GLOBAL_NAV.find((g) => g.id === "evidence")}
          expanded={sidebarExpanded}
          active={active?.id === "evidence"}
          onNavigate={go}
        />
      </div>
    </aside>
  );
}
