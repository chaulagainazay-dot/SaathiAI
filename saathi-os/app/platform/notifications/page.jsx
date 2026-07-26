"use client";
// M60 Workstream 8 — Notification Center (DERIVED_NOTIFICATION_VIEW). Derived
// from authorized platform events; no durable delivery is implied. Preferences
// are local-only; browser notification permission is never auto-requested.
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { StatusPulse } from "@/components/spatial/frame";
import { usePlatformData } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { deriveNotifications } from "@/lib/operator";
import { fmtTime } from "@/lib/workspace";
import { lsGet, lsSet, LS_KEYS } from "@/lib/local-store";

const SEV_SIGNAL = { danger: "danger", attention: "attention", success: "active", info: "idle" };

export default function NotificationsPage() {
  const d = usePlatformData();
  const router = useRouter();
  const [read, setRead] = useState([]);
  const [prefs, setPrefs] = useState({ density: "comfortable", mutedInfo: false, sound: false });

  useEffect(() => { setRead(lsGet(LS_KEYS.notifRead, [])); setPrefs(lsGet(LS_KEYS.notifPrefs, { density: "comfortable", mutedInfo: false, sound: false })); }, []);

  const notifs = useMemo(() => {
    let list = deriveNotifications({ approvals: d.approvals, executions: d.executions, attention: d.attention, health: d.health });
    if (prefs.mutedInfo) list = list.filter((n) => n.severity !== "info");
    return list;
  }, [d.approvals, d.executions, d.attention, d.health, prefs.mutedInfo]);

  const readSet = new Set(read);
  const markRead = (id) => { const next = Array.from(new Set([...read, id])); setRead(next); lsSet(LS_KEYS.notifRead, next); };
  const savePrefs = (patch) => { const next = { ...prefs, ...patch }; setPrefs(next); lsSet(LS_KEYS.notifPrefs, next); };
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";

  return (
    <SpatialWorkspaceShell
      title="Notification Center"
      subtitle="A derived view of authorized platform events. Informational only — it changes no server authority and implies no durable delivery."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Notifications" }]}
      signal={cSignal}
      health={d.health}
      loading={d.loading}
      error={d.error}
      paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <div className="glass-frame" style={{ padding: "var(--space-3) var(--space-4)", marginBottom: "var(--space-4)", display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
          <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--signal-attention)" }}>DERIVED_NOTIFICATION_VIEW</span>
          <label style={{ display: "flex", gap: 6, alignItems: "center", color: "var(--text-secondary)", fontSize: "var(--fs-2xs)" }}>
            <input type="checkbox" checked={prefs.mutedInfo} onChange={(e) => savePrefs({ mutedInfo: e.target.checked })} /> Mute informational
          </label>
          <label style={{ display: "flex", gap: 6, alignItems: "center", color: "var(--text-secondary)", fontSize: "var(--fs-2xs)" }}>
            Density
            <select value={prefs.density} onChange={(e) => savePrefs({ density: e.target.value })} style={{ background: "transparent", border: "1px solid var(--glass-frame-border)", borderRadius: 6, color: "var(--text-secondary)", padding: "2px 4px" }}>
              <option value="comfortable">comfortable</option><option value="compact">compact</option>
            </select>
          </label>
          <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginLeft: "auto" }}>{notifs.filter((n) => !readSet.has(n.id)).length} unread</span>
        </div>

        {!d.loading && notifs.length === 0 && <div className="glass-frame" style={{ padding: "var(--space-5)" }}><p style={{ color: "var(--text-muted)" }}>No notifications derived from current platform state.</p></div>}

        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
          {notifs.map((n) => {
            const unread = !readSet.has(n.id);
            return (
              <li key={n.id} className="glass-frame" style={{ padding: prefs.density === "compact" ? "8px 12px" : "12px 14px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", opacity: unread ? 1 : 0.7 }}>
                <StatusPulse signal={SEV_SIGNAL[n.severity] || "idle"} size={8} />
                <span style={{ color: "var(--text-primary)", fontSize: "var(--fs-sm)", fontWeight: unread ? 500 : 400 }}>{n.title}</span>
                <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{n.type} · {fmtTime(n.time, "—")}</span>
                <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                  {n.route && <button className="ws-chip" onClick={() => { markRead(n.id); router.push(n.route); }}>Open →</button>}
                  {unread && <button className="ws-chip" onClick={() => markRead(n.id)}>Mark read</button>}
                </span>
              </li>
            );
          })}
        </ul>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}
