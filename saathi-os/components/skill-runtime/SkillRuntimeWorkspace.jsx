"use client";

import { useCallback, useEffect, useState } from "react";
import { safeToken, skillRuntimeActions, skillStateTone } from "@/lib/skill-runtime";

const toneColor = {
  ok: "#10C98A",
  warn: "#E8B84B",
  bad: "#FF5A5A",
  muted: "#8B98B4",
};

export default function SkillRuntimeWorkspace() {
  const [token, setToken] = useState("");
  const [health, setHealth] = useState(null);
  const [skills, setSkills] = useState([]);
  const [discovered, setDiscovered] = useState([]);
  const [active, setActive] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mobile, setMobile] = useState(false);

  useEffect(() => {
    setToken(safeToken());
    const mq = window.matchMedia("(max-width: 720px)");
    const apply = () => setMobile(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  const refresh = useCallback(async () => {
    const t = safeToken() || token;
    if (!t) return;
    setError("");
    try {
      const [h, list] = await Promise.all([
        skillRuntimeActions.health(t),
        skillRuntimeActions.list(t),
      ]);
      setHealth(h.health || null);
      setSkills(list.skills || []);
    } catch (e) {
      setError(e.message || "Failed to load skills");
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
      const d = await skillRuntimeActions.discover(token);
      setDiscovered(d.discovered || []);
      await refresh();
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
      await skillRuntimeActions.register(token, packageId);
      await refresh();
    } catch (e) {
      setError(e.message || "Register failed");
    } finally {
      setBusy(false);
    }
  }

  async function doValidate(packageId) {
    if (!token) return;
    setBusy(true);
    try {
      const v = await skillRuntimeActions.validate(token, packageId);
      if (!v.ok) setError(`Validation failed: ${(v.errors || []).join("; ")}`);
      else setError("");
      return v;
    } catch (e) {
      setError(e.message || "Validate failed");
    } finally {
      setBusy(false);
    }
  }

  async function openSkill(id) {
    if (!token) return;
    setBusy(true);
    try {
      const data = await skillRuntimeActions.get(token, id);
      setActive(data);
    } catch (e) {
      setError(e.message || "Load failed");
    } finally {
      setBusy(false);
    }
  }

  async function act(action, skillId) {
    if (!token || !skillId) return;
    if (["quarantine", "revoke"].includes(action)) {
      if (!window.confirm(`${action} ${skillId}?`)) return;
    }
    setBusy(true);
    setError("");
    try {
      if (action === "enable") await skillRuntimeActions.enable(token, skillId);
      else if (action === "disable") await skillRuntimeActions.disable(token, skillId);
      else if (action === "execute")
        await skillRuntimeActions.execute(token, skillId, {
          capability: active?.skill?.manifest?.declared_capabilities?.[0] || "",
          arguments: { text: "operator-run" },
          approval_reference:
            skillId === "saathi.mutation_safe" ? "ui-appr-1" : "",
        });
      else if (action === "upgrade")
        await skillRuntimeActions.upgrade(token, skillId, {
          to_version: "1.1.0",
          package_id: "repo_audit_v1_1",
        });
      else if (action === "rollback") await skillRuntimeActions.rollback(token, skillId);
      else if (action === "quarantine")
        await skillRuntimeActions.quarantine(token, skillId, "operator");
      await refresh();
      await openSkill(skillId);
    } catch (e) {
      setError(e.message || "Action failed");
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <div style={styles.wrap} data-skill-runtime-panel="signed-out">
        <h1 style={styles.h1}>Skill Runtime</h1>
        <p style={styles.meta}>Sign in to manage the local skill ecosystem.</p>
        <p style={styles.meta}>
          No marketplace · No remote install · Production not authorized
        </p>
      </div>
    );
  }

  return (
    <div
      style={{ ...styles.wrap, ...(mobile ? { padding: "16px 12px 40px" } : {}) }}
      data-skill-runtime-panel="active"
      aria-label="Skill runtime"
    >
      <header style={styles.header}>
        <div>
          <h1 style={styles.h1}>Skill Runtime</h1>
          <p style={styles.meta} data-skill-marketplace="false">
            Extends ModuleRegistry + ToolRegistry · Local packages only · No public
            marketplace
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
            Discover local skills
          </button>
        </div>
      </header>

      {error ? (
        <div role="alert" style={styles.error} data-skill-error="true">
          {error}
        </div>
      ) : null}

      <section style={styles.grid} data-skill-overview="true">
        <div style={styles.card}>
          <h2 style={styles.h2}>Overview</h2>
          {health ? (
            <ul style={styles.list} data-skill-health="true">
              <li>Registered: {health.registered_skills}</li>
              <li data-marketplace={String(health.marketplace_authorized)}>
                Marketplace: {String(health.marketplace_authorized)}
              </li>
              <li data-remote-install={String(health.remote_install_authorized)}>
                Remote install: {String(health.remote_install_authorized)}
              </li>
              <li data-production={String(health.production_authorized)}>
                Production: {String(health.production_authorized)}
              </li>
              <li>Direct tools: {String(health.direct_skill_tool_execution)}</li>
              <li>Authority: {health.execution_authority}</li>
            </ul>
          ) : (
            <p style={styles.meta}>Loading…</p>
          )}
        </div>

        <div style={styles.card}>
          <h2 style={styles.h2}>Discovered packages</h2>
          <ul style={styles.list} data-discovered-list="true">
            {discovered.map((d) => (
              <li key={d.package_id} data-package-id={d.package_id} data-valid={String(d.valid)}>
                <strong>{d.package_id}</strong> · {d.skill_id}@{d.version} ·{" "}
                {d.valid ? "VALID" : "INVALID"}
                <div style={styles.actions}>
                  <button
                    type="button"
                    style={styles.btn}
                    data-action="validate"
                    onClick={() => doValidate(d.package_id)}
                  >
                    Validate
                  </button>
                  {d.valid ? (
                    <button
                      type="button"
                      style={styles.btn}
                      data-action="register"
                      onClick={() => doRegister(d.package_id)}
                    >
                      Register
                    </button>
                  ) : null}
                </div>
                {!d.valid && d.errors?.length ? (
                  <div style={styles.meta}>{d.errors.slice(0, 3).join("; ")}</div>
                ) : null}
              </li>
            ))}
            {!discovered.length ? (
              <li style={styles.meta}>Run Discover to list local packages.</li>
            ) : null}
          </ul>
        </div>

        <div style={styles.card}>
          <h2 style={styles.h2}>Installed skills</h2>
          <ul style={styles.list} data-skill-list="true">
            {skills.map((s) => (
              <li key={`${s.skill_id}@${s.version}`}>
                <button
                  type="button"
                  style={styles.linkBtn}
                  data-skill-id={s.skill_id}
                  data-state={s.lifecycle_state}
                  onClick={() => openSkill(s.skill_id)}
                >
                  {s.skill_id}@{s.version}
                </button>
                <span
                  style={{
                    ...styles.badge,
                    color: toneColor[skillStateTone(s.lifecycle_state)],
                  }}
                >
                  {s.lifecycle_state}
                </span>
                {s.effective ? <span style={styles.badge}>effective</span> : null}
              </li>
            ))}
            {!skills.length ? <li style={styles.meta}>No registered skills yet.</li> : null}
          </ul>
        </div>
      </section>

      <section style={styles.card} data-skill-detail="true" aria-label="Skill detail">
        <h2 style={styles.h2}>Skill detail</h2>
        {active?.skill ? (
          <>
            <p data-active-skill={active.skill.skill_id}>
              <strong>{active.skill.skill_id}</strong> @{active.skill.version}
            </p>
            <ul style={styles.list}>
              <li>State: {active.skill.lifecycle_state}</li>
              <li>Trust: {active.skill.trust_state}</li>
              <li>Health: {active.skill.health_state}</li>
              <li>Package hash: {(active.skill.package_hash || "").slice(0, 16)}…</li>
              <li data-manifest-view="true">
                Caps: {(active.skill.manifest?.declared_capabilities || []).join(", ")}
              </li>
              <li>Tools: {(active.skill.manifest?.declared_tools || []).join(", ")}</li>
              <li>
                Approvals:{" "}
                {(active.skill.manifest?.approval_requirements || []).join(", ") || "—"}
              </li>
              <li>
                Deps:{" "}
                {(active.dependencies?.resolved || [])
                  .map((d) => d.skill_id)
                  .join(", ") || "none"}
              </li>
              <li>
                Workers eligible: {active.worker_eligibility?.count ?? 0}
              </li>
            </ul>
            <div style={styles.actions}>
              <button type="button" style={styles.btn} data-action="enable" onClick={() => act("enable", active.skill.skill_id)}>
                Enable
              </button>
              <button type="button" style={styles.btn} data-action="disable" onClick={() => act("disable", active.skill.skill_id)}>
                Disable
              </button>
              <button type="button" style={styles.btn} data-action="execute" onClick={() => act("execute", active.skill.skill_id)}>
                Execute
              </button>
              {active.skill.skill_id === "saathi.repo_audit" ? (
                <>
                  <button type="button" style={styles.btn} data-action="upgrade" onClick={() => act("upgrade", active.skill.skill_id)}>
                    Upgrade
                  </button>
                  <button type="button" style={styles.btn} data-action="rollback" onClick={() => act("rollback", active.skill.skill_id)}>
                    Rollback
                  </button>
                </>
              ) : null}
              <button type="button" style={styles.btn} data-action="quarantine" onClick={() => act("quarantine", active.skill.skill_id)}>
                Quarantine
              </button>
            </div>
            <h3 style={styles.h3}>Versions</h3>
            <ul style={styles.list} data-version-list="true">
              {(active.versions || []).map((v) => (
                <li key={v.install_id}>
                  {v.version} · {v.lifecycle_state}
                  {v.effective ? " · effective" : ""}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p style={styles.meta}>Select a skill.</p>
        )}
      </section>
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
  h3: { fontSize: 13, margin: "14px 0 6px", fontWeight: 600 },
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
  actions: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 },
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
  error: {
    background: "rgba(255,90,90,0.12)",
    border: "1px solid rgba(255,90,90,0.35)",
    borderRadius: 8,
    padding: "8px 12px",
    marginBottom: 12,
    fontSize: 13,
  },
};
