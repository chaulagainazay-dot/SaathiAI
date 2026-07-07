"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Panel, Eyebrow } from "@/components/ui";
import { login, setPassword } from "@/lib/api";
import { passkeySupported, passkeyStatus, registerPasskey, unlockPasskey } from "@/lib/passkey";

const ACCENT = "#9B6BFF", TEAL = "#00BFA5", RED = "#FF5A5A";

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

  const wrap = async (fn) => { setBusy(true); setMsg(""); try { await fn(); } catch (e) { setMsg(String(e)); } finally { setBusy(false); } };

  const doSetPassword = () => wrap(async () => {
    if (np.length < 4) return setMsg("Password must be at least 4 characters");
    if (np !== np2) return setMsg("Passwords don't match");
    const r = await setPassword(pw, np);
    if (r.ok) { setMsg(status.has_password ? "✓ Password changed." : "✓ Password set — you're signed in.");
      setPw(""); setNp(""); setNp2(""); refresh(); }
    else setMsg(r.error || "Failed");
  });
  const doLogin = () => wrap(async () => {
    const r = await login(pw);
    if (r.ok) { setMsg("✓ Signed in — voice no longer needs verifying."); setPw(""); refresh(); }
    else setMsg(r.error || "Wrong password");
  });
  const doUnlock = () => wrap(async () => {
    const r = await unlockPasskey();
    if (r.ok) { setMsg("✓ Unlocked."); setTimeout(() => router.push("/os"), 700); }
    else setMsg(r.error || "Unlock failed");
  });
  const doRegister = () => wrap(async () => {
    const r = await registerPasskey();
    if (r.ok) { setMsg("✓ Fingerprint / Face ID set up."); refresh(); }
    else setMsg(r.error || "Setup failed");
  });

  const inp = { width: "100%", padding: "11px 13px", borderRadius: 10, fontSize: 14, marginTop: 8,
    border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)", color: "inherit" };
  const btn = (bg, dis) => ({ padding: "11px 16px", borderRadius: 11, border: "none", cursor: "pointer",
    fontWeight: 600, color: "#fff", background: bg, width: "100%", marginTop: 12, opacity: (busy || dis) ? 0.5 : 1 });

  return (
    <div className="page" style={{ maxWidth: 420, margin: "50px auto", paddingBottom: 60 }}>
      <Eyebrow style={{ color: ACCENT }}>SaathiOS · Security</Eyebrow>
      <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 6px" }}>
        {status.has_password ? "Sign in" : "Set up sign-in"}</div>
      <div style={{ fontSize: 13, opacity: 0.55, marginBottom: 18 }}>
        Set a password and fingerprint once — then Saathi trusts you and stops verifying your voice.
      </div>

      {/* biometric unlock if a passkey exists */}
      {supported && status.has_passkey && (
        <button onClick={doUnlock} style={btn(TEAL)}>🔓 Unlock with Touch ID / Face ID</button>
      )}

      {/* SET password (first time) OR SIGN IN (has password) */}
      <Panel style={{ padding: 18, marginTop: 14 }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>
          {status.has_password ? "Password" : "Set a password"}</div>
        {status.has_password && !status.signed_in && (
          <>
            <input type="password" value={pw} onChange={(e) => setPw(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && doLogin()} placeholder="Password" style={inp} />
            <button onClick={doLogin} style={btn(ACCENT)}>Sign in</button>
          </>
        )}
        {(!status.has_password || status.signed_in) && (
          <>
            {status.has_password && (
              <input type="password" value={pw} onChange={(e) => setPw(e.target.value)}
                placeholder="Current password" style={inp} />
            )}
            <input type="password" value={np} onChange={(e) => setNp(e.target.value)}
              placeholder={status.has_password ? "New password" : "Choose a password"} style={inp} />
            <input type="password" value={np2} onChange={(e) => setNp2(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && doSetPassword()} placeholder="Confirm password" style={inp} />
            <button onClick={doSetPassword} style={btn(ACCENT)}>
              {status.has_password ? "Change password" : "Set password"}</button>
          </>
        )}
      </Panel>

      {/* fingerprint setup */}
      {supported && (
        <Panel style={{ padding: 18, marginTop: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Fingerprint / Face ID</div>
          <div style={{ fontSize: 12, opacity: 0.55, margin: "6px 0 4px" }}>
            {status.has_passkey ? "A passkey is set up on this device."
              : status.signed_in ? "Register this device's biometrics."
              : "Set a password (or sign in) first, then register biometrics."}
          </div>
          <button onClick={doRegister} disabled={!status.signed_in}
            style={btn(status.has_passkey ? "#5b6478" : ACCENT, !status.signed_in)}>
            {status.has_passkey ? "＋ Add another device" : "🔐 Set up fingerprint on this device"}</button>
        </Panel>
      )}

      {msg && <div style={{ fontSize: 12.5, marginTop: 14, color: msg.startsWith("✓") ? TEAL : RED }}>{msg}</div>}
    </div>
  );
}
