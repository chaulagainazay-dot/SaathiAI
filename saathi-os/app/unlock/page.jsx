"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Panel, Eyebrow } from "@/components/ui";
import { login } from "@/lib/api";
import { passkeySupported, passkeyStatus, registerPasskey, unlockPasskey } from "@/lib/passkey";

const ACCENT = "#9B6BFF", TEAL = "#00BFA5", RED = "#FF5A5A";

export default function Unlock() {
  const router = useRouter();
  const [pw, setPw] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [hasPasskey, setHasPasskey] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const supported = passkeySupported();

  useEffect(() => { passkeyStatus().then((s) => setHasPasskey(!!s.has_passkey)).catch(() => {}); }, []);

  const doPassword = async () => {
    if (!pw) return;
    setBusy(true); setMsg("");
    try {
      const r = await login(pw);
      if (r.ok) { setSignedIn(true); setMsg("✓ Signed in — voice no longer needs verifying."); setPw(""); }
      else setMsg(r.error || "Wrong password");
    } catch (e) { setMsg(String(e)); } finally { setBusy(false); }
  };
  const doUnlock = async () => {
    setBusy(true); setMsg("");
    try {
      const r = await unlockPasskey();
      if (r.ok) { setSignedIn(true); setMsg("✓ Unlocked with biometrics."); setTimeout(() => router.push("/os"), 800); }
      else setMsg(r.error || "Unlock failed");
    } catch (e) { setMsg(`Biometric unlock failed: ${e}`); } finally { setBusy(false); }
  };
  const doRegister = async () => {
    setBusy(true); setMsg("");
    try {
      const r = await registerPasskey();
      if (r.ok) { setHasPasskey(true); setMsg("✓ Fingerprint/Face ID set up. Use it to unlock next time."); }
      else setMsg(r.error || "Setup failed");
    } catch (e) { setMsg(`Setup failed: ${e}`); } finally { setBusy(false); }
  };

  const inp = { width: "100%", padding: "12px 14px", borderRadius: 10, fontSize: 14,
    border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)", color: "inherit" };
  const btn = (bg) => ({ padding: "12px 18px", borderRadius: 11, border: "none", cursor: "pointer",
    fontWeight: 600, color: "#fff", background: bg, width: "100%", opacity: busy ? 0.6 : 1 });

  return (
    <div className="page" style={{ maxWidth: 420, margin: "60px auto", paddingBottom: 60 }}>
      <Eyebrow style={{ color: ACCENT }}>SaathiOS · Unlock</Eyebrow>
      <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 6px" }}>Sign in</div>
      <div style={{ fontSize: 13, opacity: 0.55, marginBottom: 18 }}>
        Sign in once — then Saathi trusts you and stops verifying your voice each time.
      </div>

      {/* biometric unlock (if a passkey exists) */}
      {supported && hasPasskey && (
        <button onClick={doUnlock} disabled={busy} style={{ ...btn(TEAL), marginBottom: 14 }}>
          🔓 Unlock with Touch ID / Face ID
        </button>
      )}

      {/* password */}
      <Panel style={{ padding: 18 }}>
        <div style={{ fontSize: 11, opacity: 0.5, marginBottom: 8 }}>PASSWORD</div>
        <input type="password" value={pw} onChange={(e) => setPw(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && doPassword()} placeholder="Your password" style={inp} />
        <button onClick={doPassword} disabled={busy} style={{ ...btn(ACCENT), marginTop: 12 }}>Sign in</button>
      </Panel>

      {/* set up fingerprint (after sign-in) */}
      {supported && (
        <Panel style={{ padding: 18, marginTop: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Fingerprint / Face ID</div>
          <div style={{ fontSize: 12, opacity: 0.55, margin: "6px 0 10px" }}>
            {hasPasskey ? "A passkey is set up for this device." : "Sign in first, then register this device’s biometrics."}
          </div>
          <button onClick={doRegister} disabled={busy || (!signedIn && !hasPasskey)}
            style={{ ...btn(hasPasskey ? "#5b6478" : ACCENT), opacity: (!signedIn && !hasPasskey) ? 0.4 : 1 }}>
            {hasPasskey ? "＋ Add another device" : "🔐 Set up fingerprint on this device"}
          </button>
        </Panel>
      )}
      {!supported && <div style={{ fontSize: 12, opacity: 0.5, marginTop: 12 }}>
        This browser doesn’t support passkeys — use the password.</div>}

      {msg && <div style={{ fontSize: 12.5, marginTop: 14, color: msg.startsWith("✓") ? TEAL : RED }}>{msg}</div>}
    </div>
  );
}
