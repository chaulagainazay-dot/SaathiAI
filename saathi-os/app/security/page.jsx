"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Eyebrow, Panel } from "@/components/ui";
import {
  fetchSessions, revokeSession, revokeAllSessions, renameSession,
  fetchPasskeys, deletePasskey, renamePasskey,
  fetchAuthAudit, setPassword, logout,
} from "@/lib/api";

const ACCENT = "#9B6BFF", TEAL = "#00BFA5", RED = "#FF5A5A", AMBER = "#FFB800";

function friendly(e) {
  const s = String(e && e.message ? e.message : e);
  return s.replace(/^Error:\s*/, "") || "Something went wrong.";
}

function formatDate(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatExpires(ts) {
  if (!ts) return "";
  const now = Date.now() / 1000;
  const diff = ts - now;
  if (diff <= 0) return "Expired";
  const hours = Math.floor(diff / 3600);
  const days = Math.floor(diff / 86400);
  if (days >= 1) return `Expires in ${days} day${days > 1 ? "s" : ""}`;
  return `Expires in ${hours} hour${hours > 1 ? "s" : ""}`;
}

function SessionIcon({ browser, os }) {
  const icon = (browser === "Safari" ? "🧭" : browser === "Chrome" ? "🌐" : browser === "Firefox" ? "🦊" : "💻");
  return <span title={`${browser} on ${os}`}>{icon}</span>;
}

function computeSecurityScore(sessions, passkeys, audit) {
  let score = 0;
  const hasPassword = sessions.some(s => s.kind === "password") || audit.some(e => e.event === "password_changed");
  if (hasPassword) score += 20;
  if (passkeys.length > 0) score += 30;
  const passwordChanges = audit.filter(e => e.event === "password_changed").sort((a, b) => b.ts - a.ts);
  if (passwordChanges.length > 0) {
    const daysSince = (Date.now() / 1000 - passwordChanges[0].ts) / 86400;
    if (daysSince < 30) score += 20;
  }
  if (sessions.length > 1) score -= 10;
  return Math.max(0, Math.min(100, score));
}

function SecurityScore({ score }) {
  const color = score >= 80 ? "#4ade80" : score >= 50 ? AMBER : RED;
  const label = score >= 80 ? "Strong" : score >= 50 ? "Fair" : "At risk";
  return (
    <div style={{ marginBottom: 18, padding: "14px 16px", borderRadius: 12, background: "rgba(255,255,255,0.04)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 600 }}>Security Score</span>
        <span style={{ fontSize: 14, fontWeight: 700, color }}>{score}/100 — {label}</span>
      </div>
      <div style={{ height: 8, borderRadius: 4, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
        <div style={{ width: `${score}%`, height: "100%", background: color, borderRadius: 4, transition: "width 0.4s ease" }} />
      </div>
      <div style={{ fontSize: 11, opacity: 0.5, marginTop: 6, lineHeight: 1.5 }}>
        +20 password &nbsp; +30 passkey &nbsp; +20 recent change &nbsp; −10 multiple sessions
      </div>
    </div>
  );
}

export default function SecurityPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState([]);
  const [passkeys, setPasskeys] = useState([]);
  const [audit, setAudit] = useState([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [pw, setPw] = useState("");
  const [np, setNp] = useState("");
  const [np2, setNp2] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [showNp, setShowNp] = useState(false);
  const [renameId, setRenameId] = useState("");
  const [renameLabel, setRenameLabel] = useState("");
  const [tab, setTab] = useState("sessions"); // sessions | passkeys | password | audit

  const wrap = async (fn) => { setBusy(true); setMsg(""); try { const r = await fn(); return r; } catch (e) { setMsg(friendly(e)); return null; } finally { setBusy(false); } };

  const load = async () => {
    const s = await wrap(() => fetchSessions());
    if (s) setSessions(s.sessions || []);
    const p = await wrap(() => fetchPasskeys());
    if (p) setPasskeys(p.passkeys || []);
    const a = await wrap(() => fetchAuthAudit(40));
    if (a) setAudit(a.events || []);
  };

  useEffect(() => { load(); }, []);

  const doChangePassword = () => wrap(async () => {
    if (np.length < 8) return setMsg("Password must be at least 8 characters.");
    if (np !== np2) return setMsg("Passwords don't match.");
    const r = await setPassword(pw, np);
    if (r.ok) { setMsg("✓ Password changed. All other sessions were signed out."); setPw(""); setNp(""); setNp2(""); load(); }
    else setMsg(friendly(r.error || "Failed"));
  });

  const doRevokeSession = (sid) => wrap(async () => {
    const r = await revokeSession(sid);
    if (r && r.ok) { setMsg("✓ Session revoked."); load(); }
  });

  const doRevokeAll = () => wrap(async () => {
    if (!confirm("Sign out all devices? You'll need to sign in again on this device.")) return;
    const r = await revokeAllSessions();
    if (r && r.ok) { setMsg("✓ Signed out everywhere."); router.push("/unlock"); }
  });

  const doDeletePasskey = (pid) => wrap(async () => {
    if (!confirm("Remove this passkey? You won't be able to use biometric login with it.")) return;
    const r = await deletePasskey(pid);
    if (r && r.ok) { setMsg("✓ Passkey removed."); load(); }
  });

  const doRenamePasskey = (pid) => wrap(async () => {
    const r = await renamePasskey(pid, renameLabel);
    if (r && r.ok) { setMsg("✓ Passkey renamed."); setRenameId(""); setRenameLabel(""); load(); }
  });

  const doRenameSession = (sid) => wrap(async () => {
    const r = await renameSession(sid, renameLabel);
    if (r && r.ok) { setMsg("✓ Session renamed."); setRenameId(""); setRenameLabel(""); load(); }
  });

  const doLogout = () => wrap(async () => {
    await logout();
    router.push("/unlock");
  });

  const inp = { width: "100%", padding: "13px 14px", borderRadius: 11, fontSize: 16, marginTop: 8,
    minHeight: 46, border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)",
    color: "inherit", WebkitAppearance: "none" };
  const btn = (bg, dis) => ({ padding: "13px 16px", borderRadius: 12, border: "none", cursor: "pointer",
    fontWeight: 600, fontSize: 15, minHeight: 46, color: "#fff", background: bg, width: "100%",
    marginTop: 12, opacity: (busy || dis) ? 0.5 : 1, touchAction: "manipulation" });
  const tabBtn = (t) => ({ padding: "8px 14px", borderRadius: 10, border: "none", cursor: "pointer",
    fontWeight: 600, fontSize: 13, background: tab === t ? ACCENT : "rgba(255,255,255,0.06)", color: "#fff" });

  const score = computeSecurityScore(sessions, passkeys, audit);

  return (
    <div className="security-page" style={{ minHeight: "100dvh", padding: "max(env(safe-area-inset-top), 32px) max(env(safe-area-inset-right), 18px) max(env(safe-area-inset-bottom), 32px) max(env(safe-area-inset-left), 18px)" }}>
      <style>{`
        .security-page button:focus-visible,
        .security-page input:focus-visible,
        .security-page a:focus-visible {
          outline: 2px solid ${ACCENT};
          outline-offset: 2px;
        }
      `}</style>
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <Eyebrow style={{ color: ACCENT }}>SaathiOS · Account Security</Eyebrow>
        <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 6px" }}>Security</div>
        <div style={{ fontSize: 13, opacity: 0.55, marginBottom: 18 }}>
          Manage your sessions, passkeys, and password.
        </div>

        <SecurityScore score={score} />

        {msg && <div role={msg.startsWith("✓") ? "status" : "alert"} aria-live={msg.startsWith("✓") ? "polite" : "assertive"}
          style={{ fontSize: 13, marginBottom: 14, padding: "10px 14px", borderRadius: 10,
            background: msg.startsWith("✓") ? "rgba(0,191,165,0.12)" : "rgba(255,90,90,0.12)",
            color: msg.startsWith("✓") ? TEAL : RED }}>{msg}</div>}

        <div style={{ display: "flex", gap: 8, marginBottom: 18, flexWrap: "wrap" }}>
          <button onClick={() => setTab("sessions")} style={tabBtn("sessions")}>Sessions</button>
          <button onClick={() => setTab("passkeys")} style={tabBtn("passkeys")}>Passkeys</button>
          <button onClick={() => setTab("password")} style={tabBtn("password")}>Password</button>
          <button onClick={() => setTab("audit")} style={tabBtn("audit")}>History</button>
        </div>

        {/* ── Sessions tab ── */}
        {tab === "sessions" && (
          <Panel style={{ padding: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div style={{ fontSize: 15, fontWeight: 600 }}>Active Sessions</div>
              <button onClick={doRevokeAll} disabled={busy} style={{ background: "none", border: "none", color: RED, fontSize: 13, cursor: "pointer" }}>
                Sign out everywhere
              </button>
            </div>
            {sessions.length === 0 && <div style={{ fontSize: 13, opacity: 0.5 }}>No active sessions.</div>}
            {sessions.map((s) => (
              <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 0", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                <div style={{ fontSize: 22 }}><SessionIcon browser={s.browser} os={s.os} /></div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {s.label || `${s.browser} on ${s.os}`} {s.current && <span style={{ color: TEAL, fontSize: 11, marginLeft: 6 }}>● Current</span>}
                  </div>
                  <div style={{ fontSize: 12, opacity: 0.5, marginTop: 2 }}>
                    {s.kind} · {formatDate(s.last_seen)} · {s.ip}
                    {s.remember_me !== undefined && ` · ${s.remember_me ? "📌 Remembered" : "🕐 24h session"}`}
                    {s.expires && ` · ${formatExpires(s.expires)}`}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                  {!s.current && (
                    <button onClick={() => doRevokeSession(s.id)} disabled={busy}
                      style={{ background: "rgba(255,90,90,0.15)", color: RED, border: "none", borderRadius: 8, padding: "6px 10px", fontSize: 12, cursor: "pointer" }}>
                      Revoke
                    </button>
                  )}
                  <button onClick={() => { setRenameId(s.id); setRenameLabel(s.label || ""); }}
                    style={{ background: "rgba(255,255,255,0.06)", color: "inherit", border: "none", borderRadius: 8, padding: "6px 10px", fontSize: 12, cursor: "pointer" }}>
                    Rename
                  </button>
                </div>
              </div>
            ))}
            {renameId && (
              <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                <input value={renameLabel} onChange={(e) => setRenameLabel(e.target.value)} placeholder="Label this session" style={{ ...inp, marginTop: 0, flex: 1 }} />
                <button onClick={() => doRenameSession(renameId)} style={{ background: ACCENT, color: "#fff", border: "none", borderRadius: 10, padding: "0 16px", fontSize: 13, cursor: "pointer" }}>Save</button>
                <button onClick={() => setRenameId("")} style={{ background: "rgba(255,255,255,0.06)", color: "inherit", border: "none", borderRadius: 10, padding: "0 16px", fontSize: 13, cursor: "pointer" }}>Cancel</button>
              </div>
            )}
          </Panel>
        )}

        {/* ── Passkeys tab ── */}
        {tab === "passkeys" && (
          <Panel style={{ padding: 18 }}>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 14 }}>Passkeys</div>
            {passkeys.length === 0 && (
              <div style={{ fontSize: 13, opacity: 0.5 }}>
                No passkeys registered. Go to <a href="/unlock" style={{ color: ACCENT }}>Unlock</a> to set up Face ID / Touch ID.
              </div>
            )}
            {passkeys.map((p) => (
              <div key={p.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 0", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                <div style={{ fontSize: 22 }}>🔐</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{p.label || `Passkey on ${p.rp_id}`}</div>
                  <div style={{ fontSize: 12, opacity: 0.5, marginTop: 2 }}>
                    {p.browser && p.device_name ? `${p.browser} · ${p.device_name}` : `ID: ${p.id.slice(0, 16)}…`}
                    {p.created && ` · Created ${formatDate(p.created)}`}
                    {p.last_used && ` · Last used ${formatDate(p.last_used)}`}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                  <button onClick={() => { setRenameId(p.id); setRenameLabel(p.label || ""); }}
                    style={{ background: "rgba(255,255,255,0.06)", color: "inherit", border: "none", borderRadius: 8, padding: "6px 10px", fontSize: 12, cursor: "pointer" }}>
                    Rename
                  </button>
                  <button onClick={() => doDeletePasskey(p.id)} disabled={busy}
                    style={{ background: "rgba(255,90,90,0.15)", color: RED, border: "none", borderRadius: 8, padding: "6px 10px", fontSize: 12, cursor: "pointer" }}>
                    Delete
                  </button>
                </div>
              </div>
            ))}
            {renameId && passkeys.some(p => p.id === renameId) && (
              <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                <input value={renameLabel} onChange={(e) => setRenameLabel(e.target.value)} placeholder="Label this passkey" style={{ ...inp, marginTop: 0, flex: 1 }} />
                <button onClick={() => doRenamePasskey(renameId)} style={{ background: ACCENT, color: "#fff", border: "none", borderRadius: 10, padding: "0 16px", fontSize: 13, cursor: "pointer" }}>Save</button>
                <button onClick={() => setRenameId("")} style={{ background: "rgba(255,255,255,0.06)", color: "inherit", border: "none", borderRadius: 10, padding: "0 16px", fontSize: 13, cursor: "pointer" }}>Cancel</button>
              </div>
            )}
          </Panel>
        )}

        {/* ── Password tab ── */}
        {tab === "password" && (
          <Panel style={{ padding: 18 }}>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 14 }}>Change Password</div>
            <div style={{ position: "relative" }}>
              <input type={showPw ? "text" : "password"} value={pw} onChange={(e) => setPw(e.target.value)}
                autoComplete="current-password" placeholder="Current password" style={inp}
                aria-label="Current password" />
              <button onClick={() => setShowPw(!showPw)} tabIndex={-1}
                aria-label={showPw ? "Hide password" : "Show password"}
                style={{ position: "absolute", right: 10, top: 18, background: "none", border: "none", color: "rgba(255,255,255,0.4)", cursor: "pointer", fontSize: 13 }}>
                {showPw ? "🙈" : "👁️"}
              </button>
            </div>
            <div style={{ position: "relative" }}>
              <input type={showNp ? "text" : "password"} value={np} onChange={(e) => setNp(e.target.value)}
                autoComplete="new-password" placeholder="New password" style={inp}
                aria-label="New password" />
              <button onClick={() => setShowNp(!showNp)} tabIndex={-1}
                aria-label={showNp ? "Hide password" : "Show password"}
                style={{ position: "absolute", right: 10, top: 18, background: "none", border: "none", color: "rgba(255,255,255,0.4)", cursor: "pointer", fontSize: 13 }}>
                {showNp ? "🙈" : "👁️"}
              </button>
            </div>
            <input type={showNp ? "text" : "password"} value={np2} onChange={(e) => setNp2(e.target.value)}
              autoComplete="new-password" placeholder="Confirm new password" style={inp}
              aria-label="Confirm new password"
              onKeyDown={(e) => e.key === "Enter" && doChangePassword()} />
            <button onClick={doChangePassword} disabled={busy} style={btn(ACCENT)}>
              {busy ? "Changing…" : "Change password"}
            </button>
          </Panel>
        )}

        {/* ── Audit tab ── */}
        {tab === "audit" && (
          <Panel style={{ padding: 18 }}>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 14 }}>Recent Activity</div>
            {audit.length === 0 && <div style={{ fontSize: 13, opacity: 0.5 }}>No recent events.</div>}
            {audit.map((e, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                <div style={{ fontSize: 18 }}>{e.ok ? "✓" : "✗"}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{e.event}</div>
                  <div style={{ fontSize: 11, opacity: 0.5, marginTop: 2 }}>{formatDate(e.ts)} · {e.ip} · {e.ua}</div>
                </div>
              </div>
            ))}
          </Panel>
        )}

        <button onClick={doLogout} disabled={busy} style={{ ...btn("transparent"), marginTop: 20 }}>
          <span style={{ opacity: 0.7 }}>🚪 Sign out</span>
        </button>
      </div>
    </div>
  );
}
