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

function SessionIcon({ browser, os }) {
  const icon = (browser === "Safari" ? "🧭" : browser === "Chrome" ? "🌐" : browser === "Firefox" ? "🦊" : "💻");
  return <span title={`${browser} on ${os}`}>{icon}</span>;
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
    const a = await wrap(() => fetchAuthAudit(20));
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

  return (
    <div style={{ minHeight: "100dvh", padding: "max(env(safe-area-inset-top), 32px) max(env(safe-area-inset-right), 18px) max(env(safe-area-inset-bottom), 32px) max(env(safe-area-inset-left), 18px)" }}>
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <Eyebrow style={{ color: ACCENT }}>SaathiOS · Account Security</Eyebrow>
        <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 6px" }}>Security</div>
        <div style={{ fontSize: 13, opacity: 0.55, marginBottom: 18 }}>
          Manage your sessions, passkeys, and password.
        </div>

        {msg && <div role="status" aria-live="polite"
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
                  <div style={{ fontSize: 12, opacity: 0.5, marginTop: 2 }}>ID: {p.id.slice(0, 16)}…</div>
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
                autoComplete="current-password" placeholder="Current password" style={inp} />
              <button onClick={() => setShowPw(!showPw)} tabIndex={-1}
                style={{ position: "absolute", right: 10, top: 18, background: "none", border: "none", color: "rgba(255,255,255,0.4)", cursor: "pointer", fontSize: 13 }}>
                {showPw ? "🙈" : "👁️"}
              </button>
            </div>
            <div style={{ position: "relative" }}>
              <input type={showNp ? "text" : "password"} value={np} onChange={(e) => setNp(e.target.value)}
                autoComplete="new-password" placeholder="New password" style={inp} />
              <button onClick={() => setShowNp(!showNp)} tabIndex={-1}
                style={{ position: "absolute", right: 10, top: 18, background: "none", border: "none", color: "rgba(255,255,255,0.4)", cursor: "pointer", fontSize: 13 }}>
                {showNp ? "🙈" : "👁️"}
              </button>
            </div>
            <input type={showNp ? "text" : "password"} value={np2} onChange={(e) => setNp2(e.target.value)}
              autoComplete="new-password" placeholder="Confirm new password" style={inp} />
            <button onClick={doChangePassword} disabled={busy} style={btn(ACCENT)}>Change password</button>

            <div style={{ marginTop: 24, paddingTop: 18, borderTop: "1px solid rgba(255,255,255,0.06)" }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>Two-Factor Authentication</div>
              <div style={{ fontSize: 13, opacity: 0.5, lineHeight: 1.5 }}>
                2FA is not yet enabled. This will be available in a future update (TOTP-based).
              </div>
            </div>

            <div style={{ marginTop: 24, paddingTop: 18, borderTop: "1px solid rgba(255,255,255,0.06)" }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>Recovery Email</div>
              <div style={{ fontSize: 13, opacity: 0.5, lineHeight: 1.5 }}>
                Recovery email is not configured. Set it in your environment variables to receive password reset links.
              </div>
            </div>
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
