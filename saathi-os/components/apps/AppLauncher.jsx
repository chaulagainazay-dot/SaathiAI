"use client";

import { useCallback, useEffect, useState } from "react";
import { appActions, appStateTone, safeToken } from "@/lib/apps";

const toneColor = {
  ok: "#10C98A",
  warn: "#E8B84B",
  bad: "#FF5A5A",
  muted: "#8B98B4",
};

export default function AppLauncher() {
  const [token, setToken] = useState("");
  const [health, setHealth] = useState(null);
  const [launcher, setLauncher] = useState(null);
  const [discovered, setDiscovered] = useState([]);
  const [active, setActive] = useState(null);
  const [launched, setLaunched] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [lastBackup, setLastBackup] = useState("");

  useEffect(() => {
    setToken(safeToken());
  }, []);

  const refresh = useCallback(async () => {
    const t = safeToken() || token;
    if (!t) return;
    try {
      const [h, l] = await Promise.all([
        appActions.health(t),
        appActions.launcher(t),
      ]);
      setHealth(h.health || null);
      setLauncher(l);
    } catch (e) {
      setError(e.message || "Load failed");
    }
  }, [token]);

  useEffect(() => {
    if (token) refresh();
  }, [token, refresh]);

  async function doDiscover() {
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      const d = await appActions.discover(token);
      setDiscovered(d.discovered || []);
    } catch (e) {
      setError(e.message || "Discover failed");
    } finally {
      setBusy(false);
    }
  }

  async function doRegister(packageId) {
    if (!token) return;
    setBusy(true);
    try {
      await appActions.register(token, packageId);
      await refresh();
    } catch (e) {
      setError(e.message || "Register failed");
    } finally {
      setBusy(false);
    }
  }

  async function openApp(appId) {
    if (!token) return;
    setBusy(true);
    try {
      setActive(await appActions.get(token, appId));
    } catch (e) {
      setError(e.message || "Open failed");
    } finally {
      setBusy(false);
    }
  }

  async function act(action, appId) {
    if (!token || !appId) return;
    setBusy(true);
    setError("");
    try {
      if (action === "enable") await appActions.enable(token, appId);
      else if (action === "disable") await appActions.disable(token, appId);
      else if (action === "launch") {
        const data = await appActions.launch(token, appId);
        setLaunched(data);
        if (appId === "saathi.hcg_pos" && typeof window !== "undefined") {
          window.location.href = "/apps/hcg";
          return;
        }
        if (appId === "saathi.ielts_alert" && typeof window !== "undefined") {
          window.location.href = "/apps/ielts";
          return;
        }
      } else if (action === "favorite") await appActions.favorite(token, appId, true);
      else if (action === "backup") {
        const b = await appActions.backup(token, appId);
        setLastBackup(b.backup?.backup_id || "");
      } else if (action === "restore" && lastBackup) {
        await appActions.restore(token, appId, lastBackup);
      } else if (action === "workflow") {
        await appActions.workflow(token, appId, {
          workflow_id: active?.app?.manifest?.workflows?.[0]?.id || "",
          approval_reference:
            appId === "saathi.platform_demo" ? "ui-appr" : "",
          arguments: { text: "launcher" },
        });
      }
      await refresh();
      await openApp(appId);
    } catch (e) {
      setError(e.message || "Action failed");
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <div style={styles.wrap} data-apps-panel="signed-out">
        <h1 style={styles.h1}>Applications</h1>
        <p style={styles.meta}>Sign in to open the application launcher.</p>
        <p style={styles.meta}>Local apps only · No marketplace · Production not authorized</p>
      </div>
    );
  }

  const search = (launcher?.search_index || []).filter((a) => {
    if (!q) return true;
    const hay = `${a.app_id} ${a.display_name} ${a.app_type}`.toLowerCase();
    return hay.includes(q.toLowerCase());
  });

  return (
    <div style={styles.wrap} data-apps-panel="active" aria-label="Application launcher">
      <header style={styles.header}>
        <div>
          <h1 style={styles.h1}>Application Launcher</h1>
          <p style={styles.meta} data-app-marketplace="false">
            Extends ModuleRegistry · Local packages · No remote marketplace
          </p>
        </div>
        <div style={styles.actions}>
          <button type="button" style={styles.btn} onClick={refresh} disabled={busy} data-action="refresh">
            Refresh
          </button>
          <button
            type="button"
            style={styles.btnPrimary}
            onClick={doDiscover}
            disabled={busy}
            data-action="discover"
          >
            Discover apps
          </button>
        </div>
      </header>

      {error ? (
        <div role="alert" style={styles.error} data-app-error="true">
          {error}
        </div>
      ) : null}

      <section style={styles.grid} data-app-overview="true">
        <div style={styles.card}>
          <h2 style={styles.h2}>Platform</h2>
          {health ? (
            <ul style={styles.list} data-app-health="true">
              <li>Installed: {health.installed_apps}</li>
              <li data-marketplace={String(health.marketplace_authorized)}>
                Marketplace: {String(health.marketplace_authorized)}
              </li>
              <li data-remote={String(health.remote_install_authorized)}>
                Remote install: {String(health.remote_install_authorized)}
              </li>
              <li data-production={String(health.production_authorized)}>
                Production: {String(health.production_authorized)}
              </li>
              <li data-bypass={String(health.apps_may_bypass_gateway)}>
                Bypass gateway: {String(health.apps_may_bypass_gateway)}
              </li>
            </ul>
          ) : (
            <p style={styles.meta}>Loading…</p>
          )}
          <input
            aria-label="Search apps"
            data-app-search="true"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search apps…"
            style={styles.input}
          />
        </div>

        <div style={styles.card}>
          <h2 style={styles.h2}>Discovered</h2>
          <ul style={styles.list} data-discovered-apps="true">
            {discovered.map((d) => (
              <li key={d.package_id} data-package-id={d.package_id} data-valid={String(d.valid)}>
                <strong>{d.display_name || d.package_id}</strong> · {d.app_id} ·{" "}
                {d.valid ? "VALID" : "INVALID"}
                {d.valid ? (
                  <button
                    type="button"
                    style={{ ...styles.btn, marginLeft: 8 }}
                    data-action="register"
                    onClick={() => doRegister(d.package_id)}
                  >
                    Install
                  </button>
                ) : null}
              </li>
            ))}
            {!discovered.length ? (
              <li style={styles.meta}>Discover local application packages.</li>
            ) : null}
          </ul>
        </div>

        <div style={styles.card}>
          <h2 style={styles.h2}>Installed / Favorites / Recent</h2>
          <ul style={styles.list} data-installed-apps="true">
            {(launcher?.installed || []).map((a) => (
              <li key={`${a.app_id}@${a.version}`}>
                <button
                  type="button"
                  style={styles.linkBtn}
                  data-app-id={a.app_id}
                  data-state={a.lifecycle_state}
                  onClick={() => openApp(a.app_id)}
                >
                  {(a.manifest && a.manifest.display_name) || a.app_id}
                </button>
                <span
                  style={{
                    ...styles.badge,
                    color: toneColor[appStateTone(a.lifecycle_state)],
                  }}
                >
                  {a.lifecycle_state}
                </span>
              </li>
            ))}
          </ul>
          <h3 style={styles.h3}>Search results</h3>
          <ul style={styles.list} data-search-results="true">
            {search.map((a) => (
              <li key={a.app_id}>
                {a.display_name} · {a.state}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section style={styles.card} data-app-detail="true">
        <h2 style={styles.h2}>Application detail</h2>
        {active?.app ? (
          <>
            <p data-active-app={active.app.app_id}>
              <strong>{active.app.manifest?.display_name || active.app.app_id}</strong> @
              {active.app.version}
            </p>
            <ul style={styles.list}>
              <li>State: {active.app.lifecycle_state}</li>
              <li>Trust: {active.app.trust_state}</li>
              <li>Health: {active.app.health_state}</li>
              <li data-workspace-isolated="true">
                Workspace isolated: {String(active.workspace?.isolated)}
              </li>
              <li>
                Nav items: {(active.navigation?.items || []).map((n) => n.label).join(", ") || "—"}
              </li>
              <li>
                Skills: {(active.app.manifest?.skills || []).join(", ") || "—"}
              </li>
              <li>
                Knowledge: {(active.app.manifest?.knowledge_sources || []).join(", ") || "—"}
              </li>
              <li data-gateway-required="true">
                Gateway: {active.integrations?.execution_gateway}
              </li>
            </ul>
            <div style={styles.actions}>
              <button type="button" style={styles.btn} data-action="enable" onClick={() => act("enable", active.app.app_id)}>
                Enable
              </button>
              <button type="button" style={styles.btn} data-action="launch" onClick={() => act("launch", active.app.app_id)}>
                Launch
              </button>
              <button type="button" style={styles.btn} data-action="favorite" onClick={() => act("favorite", active.app.app_id)}>
                Favorite
              </button>
              <button type="button" style={styles.btn} data-action="workflow" onClick={() => act("workflow", active.app.app_id)}>
                Run workflow
              </button>
              <button type="button" style={styles.btn} data-action="backup" onClick={() => act("backup", active.app.app_id)}>
                Backup
              </button>
              <button type="button" style={styles.btn} data-action="restore" onClick={() => act("restore", active.app.app_id)}>
                Restore
              </button>
              <button type="button" style={styles.btn} data-action="disable" onClick={() => act("disable", active.app.app_id)}>
                Disable
              </button>
            </div>
            {lastBackup ? (
              <p style={styles.meta} data-last-backup={lastBackup}>
                Last backup: {lastBackup}
              </p>
            ) : null}
          </>
        ) : (
          <p style={styles.meta}>Select an installed application.</p>
        )}
      </section>

      {launched ? (
        <section style={styles.card} data-app-running="true" aria-label="Running app">
          <h2 style={styles.h2}>Running workspace</h2>
          <p data-running-app={launched.app?.app_id}>
            {launched.app?.app_id} · {launched.app?.lifecycle_state}
          </p>
          <ul style={styles.list} data-running-nav="true">
            {(launched.navigation?.items || []).map((n) => (
              <li key={n.id}>
                {n.label} → {n.href}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

const styles = {
  wrap: {
    maxWidth: 1100,
    margin: "0 auto",
    padding: "24px 16px 48px",
    color: "var(--text, #E8ECF4)",
    fontFamily: "var(--font-sans, system-ui, sans-serif)",
  },
  header: {
    display: "flex",
    flexWrap: "wrap",
    gap: 12,
    justifyContent: "space-between",
    marginBottom: 16,
  },
  h1: { fontSize: 22, margin: "0 0 4px", fontWeight: 650 },
  h2: { fontSize: 15, margin: "0 0 10px", fontWeight: 600 },
  h3: { fontSize: 13, margin: "12px 0 6px", fontWeight: 600 },
  meta: { fontSize: 12, color: "var(--text-muted, #8B98B4)", margin: 0 },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
    gap: 12,
    marginBottom: 12,
  },
  card: {
    background: "var(--surface, rgba(255,255,255,0.04))",
    border: "1px solid var(--border, rgba(255,255,255,0.08))",
    borderRadius: 12,
    padding: 14,
    marginBottom: 12,
  },
  list: { margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.5 },
  actions: { display: "flex", flexWrap: "wrap", gap: 8 },
  btn: {
    border: "1px solid var(--border, rgba(255,255,255,0.12))",
    background: "transparent",
    color: "inherit",
    borderRadius: 8,
    padding: "6px 10px",
    fontSize: 12,
    cursor: "pointer",
  },
  btnPrimary: {
    border: "1px solid #3E7BFF",
    background: "rgba(62,123,255,0.15)",
    color: "inherit",
    borderRadius: 8,
    padding: "6px 10px",
    fontSize: 12,
    cursor: "pointer",
  },
  linkBtn: {
    border: "none",
    background: "none",
    color: "#7CB8FF",
    cursor: "pointer",
    padding: 0,
    fontSize: 13,
  },
  badge: { marginLeft: 8, fontSize: 11, fontWeight: 600 },
  input: {
    width: "100%",
    marginTop: 10,
    padding: "8px 10px",
    borderRadius: 8,
    border: "1px solid rgba(255,255,255,0.12)",
    background: "transparent",
    color: "inherit",
    fontSize: 13,
  },
  error: {
    background: "rgba(255,90,90,0.12)",
    border: "1px solid rgba(255,90,90,0.35)",
    borderRadius: 8,
    padding: "8px 12px",
    marginBottom: 12,
    fontSize: 13,
  },
};
