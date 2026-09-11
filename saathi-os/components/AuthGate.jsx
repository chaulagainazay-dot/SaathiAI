"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { AuthState, subscribeAuth, bootstrapAuth, signIn } from "@/lib/authState";

// Public/auth pages render their own flow — never cover them with the overlay.
const PUBLIC = ["/project/create/", "/unlock", "/reset-password"];

export default function AuthGate() {
  const pathname = usePathname();
  const [snap, setSnap] = useState({ state: AuthState.UNKNOWN, error: "" });
  const [pw, setPw] = useState("");
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const unsub = subscribeAuth(setSnap);
    bootstrapAuth();               // validate token once on load
    return unsub;
  }, []);

  const isPublic = PUBLIC.some((p) => pathname?.startsWith(p));
  const needsLogin = snap.state === AuthState.AUTH_REQUIRED || snap.state === AuthState.AUTH_ERROR;
  if (isPublic || !needsLogin) return null;

  const submit = async (e) => {
    e.preventDefault();
    if (!pw || busy) return;
    setBusy(true);
    await signIn(pw, remember);
    setBusy(false);
    setPw("");
  };

  return (
    <div role="dialog" aria-modal="true" aria-label="Session expired — sign in"
      style={{ position: "fixed", inset: 0, zIndex: 200, display: "flex",
        alignItems: "center", justifyContent: "center",
        background: "var(--dialog-scrim, rgba(3,5,11,0.72))", backdropFilter: "blur(8px)" }}>
      <form onSubmit={submit} className="glass"
        style={{ width: 360, maxWidth: "calc(100vw - 32px)", padding: 28,
          display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="eyebrow">SESSION · REAUTHENTICATION REQUIRED</div>
        <h2 className="display" style={{ fontSize: 22, margin: 0, color: "var(--text-primary, #eef3fc)" }}>
          Your session ended
        </h2>
        <p style={{ margin: 0, fontSize: 13, color: "var(--text-muted, #8b98b4)" }}>
          Sign in again to continue. In-progress actions were not sent and are not replayed automatically.
        </p>
        <input
          type="password" value={pw} onChange={(e) => setPw(e.target.value)}
          placeholder="Password" autoFocus aria-label="Password"
          style={{ height: 40, padding: "0 12px", borderRadius: 10,
            background: "var(--input-bg, #080e1a)", color: "var(--input-fg, #eef3fc)",
            border: "1px solid var(--input-border, rgba(255,255,255,0.09))", outline: "none" }} />
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12,
          color: "var(--text-muted, #8b98b4)" }}>
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          Keep me signed in on this device
        </label>
        {snap.error ? (
          <div role="alert" style={{ fontSize: 12, color: "var(--status-danger, #f0555a)" }}>{snap.error}</div>
        ) : null}
        <button type="submit" disabled={busy || !pw}
          style={{ height: 40, borderRadius: 10, border: "none", cursor: busy ? "wait" : "pointer",
            fontWeight: 600, color: "var(--accent-foreground, #04060d)",
            background: "var(--accent, #5f8fff)", opacity: busy || !pw ? 0.6 : 1 }}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
