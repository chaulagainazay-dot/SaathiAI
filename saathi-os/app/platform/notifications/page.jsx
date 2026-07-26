"use client";
// M61 — Notification Center: now SERVER_PERSISTED + SERVER_AUDITED (was M60
// DERIVED). Derived events are synced into durable, deduped server records
// (operator+), then rendered from server truth with server read/archive flags.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { StatusPulse } from "@/components/spatial/frame";
import { usePlatformData } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { deriveNotifications, actionPermission } from "@/lib/operator";
import { fmtTime } from "@/lib/workspace";
import { listNotifications, createNotification, flagNotification } from "@/lib/workflow-api";
import { lsGet, lsSet, LS_KEYS } from "@/lib/local-store";

const SEV_SIGNAL = { danger: "danger", attention: "attention", success: "active", info: "idle" };

export default function NotificationsPage() {
  const d = usePlatformData();
  const router = useRouter();
  const [server, setServer] = useState([]);
  const [prefs, setPrefs] = useState({ density: "comfortable", mutedInfo: false });
  const [busy, setBusy] = useState(false);

  useEffect(() => { setPrefs(lsGet(LS_KEYS.notifPrefs, { density: "comfortable", mutedInfo: false })); }, []);

  const canWrite = actionPermission(d.me?.context?.role, "request_approval") === "permitted";

  // Sync derived events → durable server records (deduped), then load server truth.
  const sync = useCallback(async () => {
    if (!d.token) return;
    const derived = deriveNotifications({ approvals: d.approvals, executions: d.executions, attention: d.attention, health: d.health });
    if (canWrite) {
      for (const n of derived.slice(0, 40)) {
        try {
          await createNotification({
            type: n.type, title: n.title, summary: n.type, severity: n.severity === "info" ? "info" : n.severity,
            related_object: (n.route || "").split("/").pop() || "", related_type: n.source, dedupe_key: n.id,
          }, d.token);
        } catch { /* dedupe / permission — ignore */ }
      }
    }
    try { setServer(await listNotifications(d.token)); } catch { /* */ }
  }, [d.token, d.approvals, d.executions, d.attention, d.health, canWrite]);

  useEffect(() => { if (d.token && d.ready) sync(); }, [d.token, d.ready, sync]);

  const notifs = useMemo(() => (prefs.mutedInfo ? server.filter((n) => n.severity !== "info") : server), [server, prefs.mutedInfo]);
  const savePrefs = (patch) => { const next = { ...prefs, ...patch }; setPrefs(next); lsSet(LS_KEYS.notifPrefs, next); };
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";

  const flag = async (id, flags) => { setBusy(true); try { const u = await flagNotification(id, flags, d.token); setServer((s) => s.map((n) => (n.notification_id === id ? u : n)).filter((n) => !n.archived)); } catch { /* */ } finally { setBusy(false); } };

  return (
    <SpatialWorkspaceShell
      title="Notification Center"
      subtitle="Durable, server-persisted notifications derived from authorized platform events. Read/archive state is stored and audited server-side."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Notifications" }]}
      signal={cSignal} health={d.health} loading={d.loading || busy} error={d.error} paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <div className="glass-frame" style={{ padding: "var(--space-3) var(--space-4)", marginBottom: "var(--space-4)", display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
          <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--signal-active)" }}>SERVER_PERSISTED</span>
          <label style={{ display: "flex", gap: 6, alignItems: "center", color: "var(--text-secondary)", fontSize: "var(--fs-2xs)" }}>
            <input type="checkbox" checked={prefs.mutedInfo} onChange={(e) => savePrefs({ mutedInfo: e.target.checked })} /> Mute informational
          </label>
          <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginLeft: "auto" }}>{notifs.filter((n) => !n.read).length} unread</span>
        </div>

        {!d.loading && notifs.length === 0 && <div className="glass-frame" style={{ padding: "var(--space-5)" }}><p style={{ color: "var(--text-muted)" }}>No notifications.{!canWrite && " (Operator role required to persist derived events.)"}</p></div>}

        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
          {notifs.map((n) => {
            const unread = !n.read;
            const route = n.related_object ? `/platform/attention/${n.related_object}` : "/platform/notifications";
            return (
              <li key={n.notification_id} className="glass-frame" style={{ padding: prefs.density === "compact" ? "8px 12px" : "12px 14px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", opacity: unread ? 1 : 0.7 }}>
                <StatusPulse signal={SEV_SIGNAL[n.severity] || "idle"} size={8} />
                <span style={{ color: "var(--text-primary)", fontSize: "var(--fs-sm)", fontWeight: unread ? 500 : 400 }}>{n.title}</span>
                <span className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>{n.type} · {fmtTime(n.created_at, "—")}</span>
                <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                  {n.related_object && <button className="ws-chip" onClick={() => { flag(n.notification_id, { read: true }); router.push(route); }}>Open →</button>}
                  {unread && <button className="ws-chip" onClick={() => flag(n.notification_id, { read: true })}>Mark read</button>}
                  <button className="ws-chip" onClick={() => flag(n.notification_id, { archived: true })}>Archive</button>
                </span>
              </li>
            );
          })}
        </ul>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}
