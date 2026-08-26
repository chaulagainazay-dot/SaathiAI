"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Panel, Eyebrow } from "@/components/ui";
import { login, setPassword, bootstrapStatus, bootstrapOwner } from "@/lib/api";
import { bootstrapPresentation, UNREACHABLE } from "@/lib/bootstrap-presentation";
import { passkeySupported, passkeyPlatformName, passkeyUnsupportedReason, passkeyStatus, registerPasskey, unlockPasskey } from "@/lib/passkey";

const ACCENT = "#9B6BFF", TEAL = "#00BFA5", RED = "#FF5A5A", AMBER = "#FFB800";

// D14: the bounded refusal codes the bootstrap route returns, mapped to what an
// operator standing at this machine can actually do about each one. The codes
// are deliberately the whole vocabulary — anything unrecognised falls back to a
// generic failure rather than rendering a server string, so no refusal detail
// can be reflected into the page.
const BOOTSTRAP_MESSAGES = {
  BOOTSTRAP_DISABLED: "Setup is not armed on this machine.",
  BOOTSTRAP_ALREADY_COMPLETE: "This installation already has an owner. Sign in instead.",
  BOOTSTRAP_CONTAMINATED_STATE: "Setup is blocked: this installation holds credentials it should not have yet. An operator must review it.",
  BOOTSTRAP_TOKEN_FILE_UNSET: "No setup token is configured on this machine.",
  BOOTSTRAP_TOKEN_FILE_MISSING: "The setup token file is missing.",
  BOOTSTRAP_TOKEN_FILE_NOT_ABSOLUTE: "The setup token file path is not absolute.",
  BOOTSTRAP_TOKEN_FILE_NOT_REGULAR: "The setup token file is not a regular file.",
  BOOTSTRAP_TOKEN_FILE_INSECURE_MODE: "The setup token file must be readable only by its owner (chmod 600).",
  BOOTSTRAP_TOKEN_FILE_WRONG_OWNER: "The setup token file belongs to another user.",
  BOOTSTRAP_TOKEN_FILE_UNREADABLE: "The setup token file could not be read.",
  BOOTSTRAP_TOKEN_EXPIRED: "The setup token has expired. Generate a new one.",
  BOOTSTRAP_TOKEN_MISSING: "Enter the one-time setup token.",
  BOOTSTRAP_TOKEN_INVALID: "That setup token is not correct.",
  BOOTSTRAP_TOKEN_TOO_WEAK: "The setup token is too short to be trusted.",
  BOOTSTRAP_TOKEN_MAX_AGE_INVALID: "The configured setup token lifetime is invalid.",
  BOOTSTRAP_PASSWORD_POLICY: "Choose a stronger owner password.",
  BOOTSTRAP_RATE_LIMITED: "Too many setup attempts. Wait, then try again.",
  BOOTSTRAP_NOT_LOOPBACK: "Setup must be performed on this machine.",
  BOOTSTRAP_PROXIED_REQUEST: "Setup cannot be performed through a proxy.",
  BOOTSTRAP_ORIGIN_REJECTED: "This page is not an allowed origin for setup.",
};

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
  // D14: initialisation state decides whether this screen offers bootstrap at
  // all. Until the backend reports ACTIVE there is no owner to sign in as.
  const [boot, setBoot] = useState(null);
  const [opToken, setOpToken] = useState("");
  // Last bounded refusal code from a bootstrap submission, so an expired token
  // reads as "expired" rather than as a still-armed installation.
  const [bootErr, setBootErr] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [online, setOnline] = useState(true);
  // WebAuthn capability can only be probed in the browser. Calling these during
  // render made the server ("not supported" / "Biometrics") and the client
  // ("supported" / "Touch ID") disagree, which broke hydration on /unlock with
  // React error #418. Start from the server-safe answer and refine after mount.
  const [capability, setCapability] = useState({
    ready: false,
    supported: false,
    platformName: "Biometrics",
    unsupportedMsg: "",
  });
  useEffect(() => {
    setCapability({
      ready: true,
      supported: passkeySupported(),
      platformName: passkeyPlatformName(),
      unsupportedMsg: passkeyUnsupportedReason(),
    });
  }, []);
  const { supported, platformName } = capability;
  const pwRef = useRef(null);

  const bootView = bootstrapPresentation(boot, bootErr);

  const refresh = () => passkeyStatus().then(setStatus).catch(() => {});
  useEffect(() => { refresh(); }, []);
  // A rejected status request means the backend did not answer. It is stored
  // as its own state, never as a status-shaped object: the previous
  // `{state: "UNKNOWN"}` was read by the panel as `bootstrap_enabled` falsy and
  // rendered "Setup is disabled", which is a claim about the operator's
  // configuration invented from a failed fetch.
  useEffect(() => { bootstrapStatus().then(setBoot).catch(() => setBoot(UNREACHABLE)); }, []);

  const doBootstrap = () => wrap(async () => {
    if (np.length < 8) return setMsg("Password must be at least 8 characters");
    if (np !== np2) return setMsg("Passwords don't match");
    if (!opToken.trim()) return setMsg("Enter the one-time setup token.");
    const r = await bootstrapOwner(opToken.trim(), np);
    // Clear the operator token from component state immediately, whatever the
    // outcome. It is single-use and must not sit in memory after the submit.
    setOpToken("");
    if (r.ok) {
      setMsg("✓ Owner created — you're signed in.");
      setNp(""); setNp2("");
      bootstrapStatus().then(setBoot).catch(() => setBoot(UNREACHABLE));
      refresh();
    } else {
      setBootErr(r.error || "");
      setMsg(BOOTSTRAP_MESSAGES[r.error] || "Setup failed.");
    }
  });

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

  const unsupportedMsg = capability.unsupportedMsg;

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
          {mode === "forgot" ? "Recovering access is an operator task on this machine." : "Set a password and fingerprint once — then Saathi trusts you on this device."}
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
        {mode === "unlock" && capability.ready && !supported && (
          <div role="alert" style={{ background: "rgba(255,255,255,0.04)", padding: 14, borderRadius: 11, fontSize: 13, color: "var(--color-ink-400)", marginTop: 14 }}>
            <strong>Passkeys not supported</strong><br />
            {unsupportedMsg}
          </div>
        )}

        {/* ── Password recovery — retired (D14) ──
            Emailing a reset link let an anonymous caller cause a credential to
            be minted on a machine it had never authenticated to. Recovery is an
            operator task performed on the box, not a form on the sign-in page. */}
        {mode === "forgot" && (
          <Panel style={{ padding: 18, marginTop: 14 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Password recovery</div>
            <div style={{ fontSize: 12, opacity: 0.6, margin: "6px 0 10px", lineHeight: 1.5 }}>
              Email password recovery has been removed. Recovering access to this
              installation is done by an operator on this machine.
            </div>
            <button onClick={() => { setMode("unlock"); setMsg(""); }} disabled={busy} style={btn("transparent")}>
              <span style={{ opacity: 0.7 }}>← Back to sign in</span>
            </button>
          </Panel>
        )}

        {/* ── Password form (login or set/change) ── */}
        {/* D14: an uninitialised system offers secure bootstrap, never a
            password form that would silently become the owner credential. */}
        {bootView.showPanel && (
          <Panel style={{ padding: 18, marginTop: 14 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>First-time setup</div>
            <div style={{ fontSize: 12, opacity: 0.6, margin: "6px 0 10px", lineHeight: 1.5 }}
              data-bootstrap-state={bootView.kind}>
              {bootView.copy}
            </div>
            {bootView.showForm && (
              <>
                <input type="password" value={opToken} onChange={(e) => setOpToken(e.target.value)}
                  autoComplete="off" autoCapitalize="off" autoCorrect="off" spellCheck={false}
                  placeholder="One-time setup token" style={inp} aria-label="One-time setup token" />
                <input type="password" value={np} onChange={(e) => setNp(e.target.value)}
                  autoComplete="new-password" placeholder="Owner password" style={inp}
                  aria-label="Owner password" />
                <input type="password" value={np2} onChange={(e) => setNp2(e.target.value)}
                  autoComplete="new-password" placeholder="Confirm password" style={inp}
                  onKeyDown={(e) => e.key === "Enter" && doBootstrap()}
                  aria-label="Confirm owner password" />
                <button onClick={doBootstrap} disabled={busy} style={btn(ACCENT)}>
                  {busy ? "Creating owner…" : "Create owner"}
                </button>
              </>
            )}
          </Panel>
        )}

        {bootView.kind === "active" && mode === "unlock" && (
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
                      Lost access?
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
