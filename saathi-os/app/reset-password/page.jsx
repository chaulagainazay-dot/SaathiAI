"use client";
import Link from "next/link";
import { Eyebrow, Panel } from "@/components/ui";

const ACCENT = "#9B6BFF";

// D14: this page used to redeem an emailed reset token. That flow was one of the
// two unauthenticated plaintext credential writers -- /api/v1/auth/forgot minted
// a token for any address a caller typed, and /api/v1/auth/reset spent it by
// setting the owner password and writing it in cleartext into the server's .env,
// with no session anywhere in the sequence. Both routes are retired and answer
// 410, so the form is gone rather than left to fail on submit. Recovering access
// to an installation is an operator task performed on the machine itself.
export default function ResetPasswordRetired() {
  return (
    <div style={{ minHeight: "100dvh", display: "flex", alignItems: "flex-start", justifyContent: "center",
      padding: "max(env(safe-area-inset-top), 32px) max(env(safe-area-inset-right), 18px) max(env(safe-area-inset-bottom), 32px) max(env(safe-area-inset-left), 18px)" }}>
      <div style={{ width: "100%", maxWidth: 420 }}>
        <Eyebrow style={{ color: ACCENT }}>SaathiOS · Security</Eyebrow>
        <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 6px" }}>Password reset is retired</div>
        <Panel style={{ padding: 18, marginTop: 14 }}>
          <div style={{ fontSize: 13, lineHeight: 1.6, opacity: 0.75 }}>
            Reset links are no longer issued or accepted. Change your password from
            Security settings while signed in. If you have lost access to this
            installation, recovery is performed by an operator on the machine
            running it.
          </div>
          <Link href="/unlock" style={{ display: "inline-block", marginTop: 14, color: ACCENT, fontSize: 14 }}>
            ← Back to sign in
          </Link>
        </Panel>
      </div>
    </div>
  );
}
