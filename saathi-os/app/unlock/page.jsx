"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Panel, Eyebrow } from "@/components/ui";
import { login, setPassword } from "@/lib/api";
import { passkeySupported, passkeyStatus, registerPasskey, unlockPasskey } from "@/lib/passkey";

const ACCENT = "#9B6BFF", TEAL = "#00BFA5", RED = "#FF5A5A";

// Turn raw errors / thrown WebAuthn exceptions into calm, human sentences.
function friendly(e) {
  const s = String(e && e.message ? e.message : e);
  if (/NotAllowedError|not allowed|timed out/i.test(s)) return "Cancelled or timed out — try again.";
  if (/Failed to fetch|NetworkError|load failed/i.test(s)) return "Can't reach Saathi. Check your connection and try again.";
  if (/SecurityError/i.test(s)) return "Biometrics need a secure (https) page on this device.";
  if (/InvalidStateError/i.test(s)) return "This device is already registered.";
  if (/401|403|unauth/i.test(s)) return "Session expired — sign in again.";
  return s.replace(/^Error:\s*/, "") || "Something went wrong — try again.";
}

export default function Unlock() {
  const router = useRouter();
  const [status, setStatus] = useState({ has_password: false, has_passkey: false, signed_in: false });
  const [pw, setPw] = useState("");
  const [np, setNp] = useState("");
  const [np2, setNp2] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const supported = passkeySupported();

  const refresh = () => passkeyStatus().then(setStatus).catch(() => {});
  useEffect(() => { refresh(); }, []);

  const wrap = async (fn) => { setBusy(true); setMsg(""); try { await fn(); } catch (e) { setMsg(friendly(e)); } finally { setBusy(false); } };

  const doSetPassword = () => wrap(async () => {
    if (np.length < 4) return setMsg("Password must be at least 4 characters");
    if (np !== np2) return setMsg("Passwords don't match");
    const r = await setPassword(pw, np);
    if (r.ok) { setMsg(status.has_password ? "✓ Password changed." : "✓ Password set — you're signed in.");
      setPw(""); setNp(""); setNp2(""); refresh(); }
    else setMsg(friendly(r.error || "Failed"));
  });
  const doLogin = () => wrap(async () => {
    const r = await login(pw);
    if (r.ok) { setMsg("✓ Signed in."); setPw(""); refresh(); setTimeout(() => router.push("/os"), 600); }
    else setMsg(friendly(r.error || "Wrong password"));
  });
  const doUnlock = () => wrap(async () => {
    const r = await unlockPasskey();
    if (r.ok) { setMsg("✓ Unlocked."); setTimeout(() => router.push("/os"), 600); }
    else setMsg(friendly(r.error || "Unlock failed"));
  });
  const doRegister = () => wrap(async () => {
    const r = await registerPasskey();
    if (r.ok) { setMsg("✓ Fingerprint / Face ID set up."); refresh(); }
    else setMsg(friendly(r.error || "Setup failed"));
  });

  // ≥44px touch targets; 16px font stops iOS Safari zoom-on-focus.
  const inp = { width: "100%", padding: "13px 14px", borderRadius: 11, fontSize: 16, marginTop: 8,
    minHeight: 46, border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)",
    color: "inherit", WebkitAppearance: "none" };
  const btn = (bg, dis) => ({ padding: "13px 16px", borderRadius: 12, border: "none", cursor: "pointer",
    fontWeight: 600, fontSize: 15, minHeight: 46, color: "#fff", background: bg, width: "100%",
    marginTop: 12, opacity: (busy || dis) ? 0.5 : 1, touchAction: "manipulation" });

  return (
    <div style={{ minHeight: "100dvh", display: "flex", alignItems: "flex-start", justifyContent: "center",
      padding: "max(env(safe-area-inset-top), 32px) max(env(safe-area-inset-right), 18px) " +
               "max(env(safe-area-inset-bottom), 32px) max(env(safe-area-inset-left), 18px)" }}>
      <div style={{ width: "100%", maxWidth: 420 }}>
        <Eyebrow style={{ color: ACCENT }}>SaathiOS · Security</Eyebrow>
        <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 6px" }}>
          {status.has_password ? (status.signed_in ? "You're signed in" : "Sign in") : "Set up sign-in"}</div>
        <div style={{ fontSize: 13, opacity: 0.55, marginBottom: 18 }}>
          Set a password and fingerprint once — then Saathi trusts you on this device.
        </div>

        {/* hidden username helps password managers / Apple Keychain associate the credential */}
        <input type="text" name="username" autoComplete="username" value="Ajay" readOnly
          aria-hidden="true" tabIndex={-1}
          style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }} />

        {supported && status.has_passkey && (
          <button onClick={doUnlock} disabled={busy} style={btn(TEAL)}>🔓 Unlock with Touch ID / Face ID</button>
        )}

        <Panel style={{ padding: 18, marginTop: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            {status.has_password ? "Password" : "Set a password"}</div>
          {status.has_password && !status.signed_in && (
            <>
              <input type="password" value={pw} onChange={(e) => setPw(e.target.value)}
                autoComplete="current-password" autoCapitalize="off" autoCorrect="off"
                spellCheck={false} enterKeyHint="go"
                onKeyDown={(e) => e.key === "Enter" && doLogin()} placeholder="Password" style={inp} />
              <button onClick={doLogin} disabled={busy} style={btn(ACCENT)}>Sign in</button>
            </>
          )}
          {(!status.has_password || status.signed_in) && (
            <>
              {status.has_password && (
                <input type="password" value={pw} onChange={(e) => setPw(e.target.value)}
                  autoComplete="current-password" autoCapitalize="off" autoCorrect="off" spellCheck={false}
                  placeholder="Current password" style={inp} />
              )}
              <input type="password" value={np} onChange={(e) => setNp(e.target.value)}
                autoComplete="new-password" autoCapitalize="off" autoCorrect="off" spellCheck={false}
                placeholder={status.has_password ? "New password" : "Choose a password"} style={inp} />
              <input type="password" value={np2} onChange={(e) => setNp2(e.target.value)}
                autoComplete="new-password" autoCapitalize="off" autoCorrect="off" spellCheck={false}
                enterKeyHint="done"
                onKeyDown={(e) => e.key === "Enter" && doSetPassword()} placeholder="Confirm password" style={inp} />
              <button onClick={doSetPassword} disabled={busy} style={btn(ACCENT)}>
                {status.has_password ? "Change password" : "Set password"}</button>
            </>
          )}
        </Panel>

        {supported && (
          <Panel style={{ padding: 18, marginTop: 14 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Fingerprint / Face ID</div>
            <div style={{ fontSize: 12, opacity: 0.55, margin: "6px 0 4px" }}>
              {status.has_passkey ? "A passkey is set up on this device."
                : status.signed_in ? "Register this device's biometrics."
                : "Set a password (or sign in) first, then register biometrics."}
            </div>
            <button onClick={doRegister} disabled={busy || !status.signed_in}
              style={btn(status.has_passkey ? "#5b6478" : ACCENT, !status.signed_in)}>
              {status.has_passkey ? "＋ Add another device" : "🔐 Set up fingerprint on this device"}</button>
          </Panel>
        )}

        {status.signed_in && (
          <button onClick={() => router.push("/os")} style={btn("transparent")}>
            <span style={{ opacity: 0.7 }}>Continue to SaathiOS →</span></button>
        )}

        {msg && <div role="status" aria-live="polite"
          style={{ fontSize: 12.5, marginTop: 14, color: msg.startsWith("✓") ? TEAL : RED }}>{msg}</div>}
      </div>
    </div>
  );
}
