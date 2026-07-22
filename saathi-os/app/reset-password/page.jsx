"use client";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Eyebrow, Panel } from "@/components/ui";
import { resetPassword } from "@/lib/api";
import { Suspense } from "react";

const ACCENT = "#9B6BFF", TEAL = "#00BFA5", RED = "#FF5A5A", AMBER = "#FFB800";

function friendly(e) {
  const s = String(e && e.message ? e.message : e);
  return s.replace(/^Error:\s*/, "") || "Something went wrong.";
}

function strengthLabel(score) {
  return ["Very weak", "Weak", "Fair", "Good", "Strong"][Math.max(0, Math.min(4, score))];
}
function strengthColor(score) {
  return [RED, RED, AMBER, TEAL, "#4ade80"][Math.max(0, Math.min(4, score))];
}

function ResetPasswordForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") || "";
  const [np, setNp] = useState("");
  const [np2, setNp2] = useState("");
  const [showNp, setShowNp] = useState(false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

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
  const strength = scorePassword(np);

  const doReset = async () => {
    if (!token) return setMsg("Invalid or missing reset link.");
    if (np.length < 8) return setMsg("Password must be at least 8 characters.");
    if (np !== np2) return setMsg("Passwords don't match.");
    setBusy(true); setMsg("");
    try {
      const r = await resetPassword(token, np);
      if (r.ok) { setDone(true); setMsg("✓ Password reset. Sign in with your new password."); }
      else setMsg(friendly(r.error || "Reset failed"));
    } catch (e) { setMsg(friendly(e)); }
    finally { setBusy(false); }
  };

  const inp = { width: "100%", padding: "13px 14px", borderRadius: 11, fontSize: 16, marginTop: 8,
    minHeight: 46, border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)",
    color: "inherit", WebkitAppearance: "none" };
  const btn = (bg, dis) => ({ padding: "13px 16px", borderRadius: 12, border: "none", cursor: "pointer",
    fontWeight: 600, fontSize: 15, minHeight: 46, color: "#fff", background: bg, width: "100%",
    marginTop: 12, opacity: (busy || dis) ? 0.5 : 1, touchAction: "manipulation" });

  return (
    <div style={{ minHeight: "100dvh", display: "flex", alignItems: "flex-start", justifyContent: "center",
      padding: "max(env(safe-area-inset-top), 32px) max(env(safe-area-inset-right), 18px) max(env(safe-area-inset-bottom), 32px) max(env(safe-area-inset-left), 18px)" }}>
      <div style={{ width: "100%", maxWidth: 420 }}>
        <Eyebrow style={{ color: ACCENT }}>SaathiOS · Security</Eyebrow>
        <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 6px" }}>Reset password</div>
        <div style={{ fontSize: 13, opacity: 0.55, marginBottom: 18 }}>
          Enter a new password for your account.
        </div>

        {msg && <div role="status" aria-live="polite"
          style={{ fontSize: 13, marginBottom: 14, padding: "10px 14px", borderRadius: 10,
            background: msg.startsWith("✓") ? "rgba(0,191,165,0.12)" : "rgba(255,90,90,0.12)",
            color: msg.startsWith("✓") ? TEAL : RED }}>{msg}</div>}

        {!done && (
          <Panel style={{ padding: 18 }}>
            <div style={{ position: "relative" }}>
              <input type={showNp ? "text" : "password"} value={np} onChange={(e) => setNp(e.target.value)}
                autoComplete="new-password" autoCapitalize="off" autoCorrect="off" spellCheck={false}
                placeholder="New password" style={inp} />
              <button onClick={() => setShowNp(!showNp)} tabIndex={-1}
                style={{ position: "absolute", right: 10, top: 18, background: "none", border: "none", color: "rgba(255,255,255,0.4)", cursor: "pointer", fontSize: 13 }}>
                {showNp ? "🙈" : "👁️"}
              </button>
            </div>
            {np.length > 0 && (
              <div style={{ marginTop: 10 }}>
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
              autoComplete="new-password" placeholder="Confirm password" style={inp} />
            <button onClick={doReset} disabled={busy} style={btn(ACCENT)}>Reset password</button>
          </Panel>
        )}

        {done && (
          <button onClick={() => router.push("/unlock")} style={btn(TEAL)}>
            Go to sign in →
          </button>
        )}
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div style={{ minHeight: "100dvh", display: "flex", alignItems: "center", justifyContent: "center" }}><div>Loading…</div></div>}>
      <ResetPasswordForm />
    </Suspense>
  );
}