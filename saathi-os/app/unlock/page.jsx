"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Panel, Eyebrow } from "@/components/ui";
import { login, setPassword, forgotPassword } from "@/lib/api";
import { passkeySupported, passkeyPlatformName, passkeyUnsupportedReason, passkeyStatus, registerPasskey, unlockPasskey } from "@/lib/passkey";

const ACCENT = "var(--accent)", TEAL = "#00BFA5", RED = "#FF5A5A", AMBER = "#FFB800";

function friendly(e) {
  const s = String(e && e.message ? e.message : e);
  if (/NotAllowedError|not allowed|timed out/i.test(s)) return "Cancelled or timed out — try again.";
  if (/Failed to fetch|NetworkError|load failed/i.test(s)) return "Can't reach Saathi. Check your connection and try again.";
  if (/SecurityError/i.test(s)) return "Biometrics need a secure (https) page on this device.";
  if (/InvalidStateError/i.test(s)) return "This device is already registered.";
  if (/401|403|unauth/i.test(s)) return "Session expired — sign in again.";
  return s.replace(/^Error:\s*/, "") || "Something went wrong — try again.";
}

function strengthLabel(score) {
  return ["Very weak", "Weak", "Fair", "Good", "Strong"][Math.max(0, Math.min(4, score))];
}
function strengthColor(score) {
  return [RED, RED, AMBER, TEAL, "#4ade80"][Math.max(0, Math.min(4, score))];
}

export default function Unlock() {
  const router = useRouter();
  const [status, setStatus] = useState({ has_password: false, has_passkey: false, signed_in: false });
  const [pw, setPw] = useState("");
  const [np, setNp] = useState("");
  const [np2, setNp2] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [showNp, setShowNp] = useState(false);
  const [capsOn, setCapsOn] = useState(false);
  const [strength, setStrength] = useState({ score: 0, checks: {} });
  const [mode, setMode] = useState("unlock"); // unlock | forgot | reset
  const [forgotEmail, setForgotEmail] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [online, setOnline] = useState(true);
  const supported = passkeySupported();
  const platformName = passkeyPlatformName();
  const pwRef = useRef(null);

  const refresh = () => passkeyStatus().then(setStatus).catch(() => {});
  useEffect(() => { refresh(); }, []);

  // Offline detection
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    setOnline(navigator.onLine);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);

  // Escape key dismisses messages and resets mode
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") {
        setMsg("");
        if (mode !== "unlock") setMode("unlock");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mode]);

  const wrap = async (fn) => { setBusy(true); setMsg(""); try { await fn(); } catch (e) { setMsg(friendly(e)); } finally { setBusy(false); } };

  const doSetPassword = () => wrap(async () => {
    if (np.length < 8) return setMsg("Password must be at least 8 characters");
    if (np !== np2) return setMsg("Passwords don't match");
    const r = await setPassword(pw, np);
    if (r.ok) { setMsg(status.has_password ? "✓ Password changed." : "✓ Password set — you're signed in.");
      setPw(""); setNp(""); setNp2(""); refresh(); }
    else setMsg(friendly(r.error || "Failed"));
  });

  const doLogin = () => wrap(async () => {
    const r = await login(pw, rememberMe);
    if (r.ok) {
      setMsg("✓ Signed in."); setPw(""); refresh(); setTimeout(() => router.push("/os"), 600);
    } else setMsg(friendly(r.error || "Wrong password"));
  });

  const doUnlock = () => wrap(async () => {
    const r = await unlockPasskey(rememberMe);
    if (r.ok) { setMsg("✓ Unlocked."); setTimeout(() => router.push("/os"), 600); }
    else setMsg(friendly(r.error || "Unlock failed"));
  });

  const doRegister = () => wrap(async () => {
    const r = await registerPasskey();
    if (r.ok) { setMsg("✓ Passkey set up."); refresh(); }
    else setMsg(friendly(r.error || "Setup failed"));
  });

  const doForgot = () => wrap(async () => {
    if (!forgotEmail.includes("@")) return setMsg("Enter a valid email address.");
    const r = await forgotPassword(forgotEmail);
    if (r.ok) setMsg("✓ If that email is registered, a reset link was sent.");
    else setMsg(friendly(r.error || "Failed to send reset email"));
  });

  const onNpChange = (v) => {
    setNp(v);
    const s = scorePassword(v);
    setStrength(s);
  };

  const scorePassword = (v) => {
    const checks = {
      length: v.length >= 8,
      lower: /[a-z]/.test(v),
      upper: /[A-Z]/.test(v),
      digit: /\d/.test(v),
      symbol: /[^a-zA-Z0-9]/.test(v),
    };
    const score = [checks.length, checks.lower || checks.upper, checks.digit, checks.symbol].filter(Boolean).length;
    return { score, checks };
  };

  const handlePwKeyDown = useCallback((e) => {
    setCapsOn(e.getModifierState("CapsLock"));
    if (e.key === "Enter") {
      e.preventDefault();
      doLogin();
    }
  }, [doLogin]);

  const inp = { width: "100%", padding: "13px 14px", borderRadius: 11, fontSize: 16, marginTop: 8,
    minHeight: 46, border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)",
    color: "inherit", WebkitAppearance: "none" };
  const btn = (bg, dis) => ({ padding: "13px 16px", borderRadius: 12, border: "none", cursor: "pointer",
    fontWeight: 600, fontSize: 15, minHeight: 46, color: "#fff", background: bg, width: "100%",
    marginTop: 12, opacity: (busy || dis) ? 0.5 : 1, touchAction: "manipulation" });

  const unsupportedMsg = passkeyUnsupportedReason();

  return (
    <div className="unlock-page" style={{ minHeight: "100dvh", display: "flex", alignItems: "flex-start", justifyContent: "center",
      padding: "max(env(safe-area-inset-top), 32px) max(env(safe-area-inset-right), 18px) " +
               "max(env(safe-area-inset-bottom), 32px) max(env(safe-area-inset-left), 18px)" }}>
      <style>{`
        .unlock-page button:focus-visible,
        .unlock-page input:focus-visible {
          outline: 2px solid ${ACCENT};
          outline-offset: 2px;
        }
      `}</style>
      <div style={{ width: "100%", maxWidth: 420 }}>
        {!online && (
          <div role="alert" style={{ background: "rgba(255,184,0,0.12)", color: AMBER, padding: "10px 14px", borderRadius: 10, fontSize: 13, marginBottom: 14, display: "flex", alignItems: "center", gap: 8 }}>
            <span aria-hidden="true">⚠️</span> You're offline. Sign-in requires a connection.
          </div>
        )}

        <Eyebrow style={{ color: ACCENT }}>SaathiOS · Security</Eyebrow>
        <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 6px" }}>
          {mode === "forgot" ? "Reset password" : status.has_password ? (status.signed_in ? "You're signed in" : "Sign in") : "Set up sign-in"}
        </div>
        <div style={{ fontSize: 13, opacity: 0.55, marginBottom: 18 }}>
          {mode === "forgot" ? "Enter your email and we'll send a reset link." : "Set a password and fingerprint once — then Saathi trusts you on this device."}
        </div>

        <input type="text" name="username" autoComplete="username" value="Ajay" readOnly
          aria-hidden="true" tabIndex={-1}
          style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }} />

        {/* ── Passkey unlock button ── */}
        {mode === "unlock" && supported && status.has_passkey && (
          <button onClick={doUnlock} disabled={busy || !online} style={btn(TEAL)}
            aria-label={`Unlock with ${platformName}`}>
            {busy ? "Unlocking…" : `🔓 Unlock with ${platformName}`}
          </button>
        )}
        {mode === "unlock" && !supported && (
          <div role="alert" style={{ background: "rgba(255,255,255,0.04)", padding: 14, borderRadius: 11, fontSize: 13, color: "var(--color-ink-400)", marginTop: 14 }}>
            <strong>Passkeys not supported</strong><br />
            {unsupportedMsg}
          </div>
        )}

        {/* ── Forgot Password form ── */}
        {mode === "forgot" && (
          <Panel style={{ padding: 18, marginTop: 14 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }} id="forgot-email-label">Email address</div>
            <input type="email" value={forgotEmail} onChange={(e) => setForgotEmail(e.target.value)}
              autoComplete="email" autoCapitalize="off" autoCorrect="off" spellCheck={false}
              enterKeyHint="send" onKeyDown={(e) => e.key === "Enter" && doForgot()}
              placeholder="you@example.com" style={inp}
              aria-label="Email address" aria-describedby="forgot-email-label" />
            <button onClick={doForgot} disabled={busy || !online} style={btn(ACCENT)}>
              {busy ? "Sending…" : "Send reset link"}
            </button>
            <button onClick={() => { setMode("unlock"); setMsg(""); }} disabled={busy} style={btn("transparent")}>
              <span style={{ opacity: 0.7 }}>← Back to sign in</span>
            </button>
          </Panel>
        )}

        {/* ── Password form (login or set/change) ── */}
        {mode === "unlock" && (
          <>
            <Panel style={{ padding: 18, marginTop: 14 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>
                {status.has_password ? "Password" : "Set a password"}
              </div>

              {status.has_password && !status.signed_in && (
                <>
                  <div style={{ position: "relative" }}>
                    <input type={showPw ? "text" : "password"} value={pw} onChange={(e) => setPw(e.target.value)}
                      ref={pwRef} onKeyDown={handlePwKeyDown}
                      autoComplete="current-password" autoCapitalize="off" autoCorrect="off"
                      spellCheck={false} enterKeyHint="go"
                      placeholder="Password" style={inp}
                      aria-label="Password"
                      aria-describedby={capsOn ? "caps-warning" : undefined} />
                    <button onClick={() => setShowPw(!showPw)} tabIndex={-1}
                      aria-label={showPw ? "Hide password" : "Show password"}
                      style={{ position: "absolute", right: 10, top: 18, background: "none", border: "none", color: "rgba(255,255,255,0.4)", cursor: "pointer", fontSize: 13 }}>
                      {showPw ? "🙈" : "👁️"}
                    </button>
                  </div>
                  {capsOn && (
                    <div id="caps-warning" role="alert" style={{ fontSize: 12, color: AMBER, marginTop: 6 }}>⚠️ Caps Lock is on</div>
                  )}
                  <button onClick={doLogin} disabled={busy || !online} style={btn(ACCENT)}>
                    {busy ? "Signing in…" : "Sign in"}
                  </button>

                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 10, flexWrap: "wrap", gap: 8 }}>
                    <label style={{ fontSize: 13, opacity: 0.7, display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                      <input type="checkbox" checked={rememberMe} onChange={(e) => setRememberMe(e.target.checked)} style={{ accentColor: ACCENT, width: 18, height: 18 }} />
                      Keep me signed in
                    </label>
                    <button onClick={() => { setMode("forgot"); setMsg(""); }}
                      style={{ background: "none", border: "none", color: ACCENT, fontSize: 13, cursor: "pointer", padding: 0, minHeight: 44 }}>
                      Forgot password?
                    </button>
                  </div>
                </>
              )}

              {(!status.has_password || status.signed_in) && (
                <>
                  {status.has_password && (
                    <div style={{ position: "relative" }}>
                      <input type={showPw ? "text" : "password"} value={pw} onChange={(e) => setPw(e.target.value)}
                        autoComplete="current-password" autoCapitalize="off" autoCorrect="off" spellCheck={false}
                        placeholder="Current password" style={inp}
                        aria-label="Current password" />
                      <button onClick={() => setShowPw(!showPw)} tabIndex={-1}
                        aria-label={showPw ? "Hide password" : "Show password"}
                        style={{ position: "absolute", right: 10, top: 18, background: "none", border: "none", color: "rgba(255,255,255,0.4)", cursor: "pointer", fontSize: 13 }}>
                        {showPw ? "🙈" : "👁️"}
                      </button>
                    </div>
                  )}
                  <div style={{ position: "relative" }}>
                    <input type={showNp ? "text" : "password"} value={np} onChange={(e) => onNpChange(e.target.value)}
                      autoComplete="new-password" autoCapitalize="off" autoCorrect="off" spellCheck={false}
                      placeholder={status.has_password ? "New password" : "Choose a password"} style={inp}
                      aria-label={status.has_password ? "New password" : "Choose a password"}
                      aria-describedby="strength-meter" />
                    <button onClick={() => setShowNp(!showNp)} tabIndex={-1}
                      aria-label={showNp ? "Hide password" : "Show password"}
                      style={{ position: "absolute", right: 10, top: 18, background: "none", border: "none", color: "rgba(255,255,255,0.4)", cursor: "pointer", fontSize: 13 }}>
                      {showNp ? "🙈" : "👁️"}
                    </button>
                  </div>

                  {/* Strength meter */}
                  {np.length > 0 && (
                    <div id="strength-meter" style={{ marginTop: 10 }}>
                      <div style={{ display: "flex", gap: 4, height: 4, marginBottom: 6 }}>
                        {[0,1,2,3].map(i => (
                          <div key={i} style={{ flex: 1, borderRadius: 2, background: i < strength.score ? strengthColor(strength.score) : "rgba(255,255,255,0.1)" }} />
                        ))}
                      </div>
                      <div style={{ fontSize: 12, color: strengthColor(strength.score), fontWeight: 600 }}>
                        {strengthLabel(strength.score)}
                      </div>
                      <div style={{ fontSize: 11, opacity: 0.5, marginTop: 4, lineHeight: 1.5 }}>
                        {strength.checks.length ? "✓" : "○"} 8+ chars &nbsp;
                        {strength.checks.upper ? "✓" : "○"} Uppercase &nbsp;
                        {strength.checks.lower ? "✓" : "○"} Lowercase &nbsp;
                        {strength.checks.digit ? "✓" : "○"} Number &nbsp;
                        {strength.checks.symbol ? "✓" : "○"} Symbol
                      </div>
                    </div>
                  )}

                  <input type={showNp ? "text" : "password"} value={np2} onChange={(e) => setNp2(e.target.value)}
                    autoComplete="new-password" autoCapitalize="off" autoCorrect="off" spellCheck={false}
                    enterKeyHint="done"
                    onKeyDown={(e) => e.key === "Enter" && doSetPassword()} placeholder="Confirm password" style={inp}
                    aria-label="Confirm password" />
                  <button onClick={doSetPassword} disabled={busy} style={btn(ACCENT)}>
                    {busy ? "Saving…" : (status.has_password ? "Change password" : "Set password")}
                  </button>
                </>
              )}
            </Panel>

            {/* ── Passkey panel ── */}
            {supported && (
              <Panel style={{ padding: 18, marginTop: 14 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>Fingerprint / Face ID</div>
                <div style={{ fontSize: 12, opacity: 0.55, margin: "6px 0 4px" }}>
                  {status.has_passkey ? "A passkey is set up on this device."
                    : status.signed_in ? "Register this device's biometrics."
                    : "Set a password (or sign in) first, then register biometrics."}
                </div>
                <button onClick={doRegister} disabled={busy || !status.signed_in}
                  style={btn(status.has_passkey ? "#5b6478" : ACCENT, !status.signed_in)}
                  aria-label={status.has_passkey ? "Add another passkey" : `Set up ${platformName} on this device`}>
                  {busy ? "Setting up…" : (status.has_passkey ? "＋ Add another device" : `🔐 Set up ${platformName} on this device`)}
                </button>
              </Panel>
            )}

            {status.signed_in && (
              <button onClick={() => router.push("/os")} style={btn("transparent")}>
                <span style={{ opacity: 0.7 }}>Continue to SaathiOS →</span>
              </button>
            )}
          </>
        )}

        {msg && <div role={msg.startsWith("✓") ? "status" : "alert"} aria-live={msg.startsWith("✓") ? "polite" : "assertive"}
          style={{ fontSize: 12.5, marginTop: 14, color: msg.startsWith("✓") ? TEAL : RED }}>{msg}</div>}
      </div>
    </div>
  );
}
