"use client";
import { useState, useMemo, useEffect, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { getAllNavItems, getPrimaryAreas, GLOBAL_NAV, NAV_GROUPS } from "@/lib/navigation";
import { applicationCommandsFromBackend } from "@/lib/modules/shell";

function buildCommands(pathname, moduleNavigation) {
  const cmds = [];

  for (const g of NAV_GROUPS) {
    for (const item of g.items) {
      cmds.push({
        id: `nav-${item.id}`,
        label: `Go to ${item.label}`,
        group: g.label,
        route: item.href,
        kind: "navigate",
      });
    }
  }
  cmds.push(...applicationCommandsFromBackend(moduleNavigation));
  for (const item of GLOBAL_NAV) {
    cmds.push({
      id: `nav-${item.id}`,
      label: `Go to ${item.label}`,
      group: "Global",
      route: item.href,
      kind: "navigate",
    });
  }

  // Safe action stubs — route to Command Center or Approvals; never execute
  cmds.push(
    {
      id: "act-approve-inbox",
      label: "Review pending approvals",
      group: "Actions",
      route: "/approvals",
      kind: "safe-action",
    },
    {
      id: "act-command",
      label: "Open Command Center (plan / request approval)",
      group: "Actions",
      route: "/command",
      kind: "safe-action",
    },
    {
      id: "act-create-mission",
      label: "New mission (opens Missions)",
      group: "Actions",
      route: "/missions/new",
      kind: "safe-action",
    },
    {
      id: "act-monitoring",
      label: "Open Monitoring",
      group: "Actions",
      route: "/monitoring",
      kind: "navigate",
    },
    {
      id: "act-settings",
      label: "Open Settings",
      group: "Actions",
      route: "/settings",
      kind: "navigate",
    },
    // M148+ SaathiOS Core unification destinations
    {
      id: "core-home",
      label: "Operator Home (unified dashboard)",
      group: "Core",
      route: "/platform/home",
      kind: "navigate",
    },
    {
      id: "core-search",
      label: "Universal Search",
      group: "Core",
      route: "/platform/search",
      kind: "navigate",
    },
    {
      id: "core-hcg",
      label: "Launch HCG Operations",
      group: "Applications",
      route: "/apps/hcg",
      kind: "navigate",
    },
    {
      id: "core-ielts",
      label: "Launch IELTSAlert",
      group: "Applications",
      route: "/apps/ielts",
      kind: "navigate",
    },
    {
      id: "core-apps",
      label: "Application Launcher",
      group: "Applications",
      route: "/apps",
      kind: "navigate",
    },
    {
      id: "core-notifications",
      label: "Notification Center",
      group: "Core",
      route: "/platform/notifications",
      kind: "navigate",
    }
  );

  // Mission context extras
  const missionMatch = pathname?.match(/^\/missions\/([^/]+)/);
  if (missionMatch) {
    const id = missionMatch[1];
    for (const [label, sub] of [
      ["Mission overview", ""],
      ["Mission intake", "/intake"],
      ["Proposal", "/proposal"],
      ["Voice studio", "/voice"],
      ["Website intelligence", "/website"],
      ["Reference intelligence", "/reference"],
    ]) {
      cmds.unshift({
        id: `mission-${sub || "root"}`,
        label,
        group: "Mission",
        route: `/missions/${id}${sub}`,
        kind: "navigate",
      });
    }
  }

  // Legacy aliases as secondary navigations
  const legacy = [
    { label: "Legacy: CEO page", route: "/ceo" },
    { label: "Legacy: OS page", route: "/os" },
    { label: "Legacy: Control Center", route: "/control" },
    { label: "Legacy: Chat", route: "/chat" },
    { label: "Legacy: Workspace", route: "/workspace" },
    { label: "Legacy: Studio OS", route: "/studio-os" },
  ];
  for (const l of legacy) {
    cmds.push({ id: `legacy-${l.route}`, label: l.label, group: "Legacy", route: l.route, kind: "legacy" });
  }

  return cmds;
}

export default function CommandPalette({ open, onClose, moduleNavigation = null }) {
  const router = useRouter();
  const pathname = usePathname();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef(null);

  const commands = useMemo(
    () => buildCommands(pathname, moduleNavigation),
    [pathname, moduleNavigation]
  );

  const results = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return commands.filter((c) => c.kind !== "legacy").slice(0, 24);
    return commands.filter(
      (c) =>
        c.label.toLowerCase().includes(s) ||
        c.group?.toLowerCase().includes(s) ||
        c.route?.toLowerCase().includes(s)
    );
  }, [q, commands]);

  useEffect(() => {
    if (open) {
      setQ("");
      setSel(0);
      setTimeout(() => inputRef.current?.focus(), 40);
    }
  }, [open]);
  useEffect(() => {
    setSel(0);
  }, [q]);

  const go = (c) => {
    if (!c?.route) return;
    onClose();
    router.push(c.route);
  };

  const onKey = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSel((s) => Math.min(results.length - 1, s + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSel((s) => Math.max(0, s - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(results[sel]);
    } else if (e.key === "Escape") {
      onClose();
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 80,
            background: "rgba(4,6,13,0.6)",
            backdropFilter: "blur(6px)",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "center",
            paddingTop: "16vh",
          }}
        >
          <motion.div
            initial={{ y: -18, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: -12, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            onClick={(e) => e.stopPropagation()}
            className="surface-raised"
            role="dialog"
            aria-label="Command palette"
            style={{
              width: 620,
              maxWidth: "90vw",
              padding: 8,
              borderRadius: "var(--rad-lg)",
              border: "1px solid var(--palette-border)",
              background: "var(--palette-bg)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px" }}>
              <span className="mono" style={{ color: "var(--text-muted)", fontSize: 12 }}>
                ⌘K
              </span>
              <input
                ref={inputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={onKey}
                placeholder="Go to area, open Approvals, Command Center…"
                aria-label="Search commands"
                style={{
                  flex: 1,
                  background: "transparent",
                  border: "none",
                  outline: "none",
                  color: "var(--text-primary)",
                  fontSize: 16,
                  fontFamily: "var(--font-ui)",
                }}
              />
            </div>
            <div style={{ height: 1, background: "var(--border)" }} />
            <div style={{ maxHeight: 360, overflowY: "auto", padding: 6 }}>
              {results.map((c, i) => (
                <div
                  key={c.id}
                  onMouseEnter={() => setSel(i)}
                  onClick={() => go(c)}
                  role="option"
                  aria-selected={i === sel}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "11px 14px",
                    borderRadius: 12,
                    cursor: "pointer",
                    background: i === sel ? "var(--surface-hover)" : "transparent",
                  }}
                >
                  <span style={{ color: "var(--text-primary)", fontSize: 14, flex: 1 }}>{c.label}</span>
                  <span className="eyebrow" style={{ color: "var(--text-muted)" }}>
                    {c.group}
                  </span>
                </div>
              ))}
              {results.length === 0 && (
                <div style={{ padding: 24, textAlign: "center", color: "var(--text-muted)" }}>No matches.</div>
              )}
            </div>
            <div
              className="mono"
              style={{ padding: "8px 14px", fontSize: 10, color: "var(--text-disabled)", letterSpacing: "0.06em" }}
            >
              Navigation only · sensitive acts open Approvals or Command Center · no direct execution
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// Silence unused import warnings if tree-shaken elsewhere
void getAllNavItems;
void getPrimaryAreas;
