"use client";
// M59 — session gate. Auth (bootstrap/login) lives on /platform; deep workspace
// routes require an existing platform token. When absent, we prompt the operator
// to sign in at Home rather than duplicating the login surface everywhere.
import { useRouter } from "next/navigation";

export function RequireSession({ token, ready, children }) {
  const router = useRouter();
  if (!ready) return null;
  if (!token) {
    return (
      <div className="glass-frame" style={{ padding: "var(--space-5)", maxWidth: 560, margin: "var(--space-5) auto" }} role="region" aria-label="Authentication required">
        <div className="eyebrow" style={{ color: "var(--signal-attention)" }}>Authentication required</div>
        <p style={{ color: "var(--text-secondary)", marginTop: 8 }}>
          This spatial workspace requires an active platform session. Sign in from Home to bring the
          runtime online. Execution stays governed by PlatformAgentRuntime and ExecutionGateway;
          connectors remain dry-run and production is disabled.
        </p>
        <button
          onClick={() => router.push("/platform")}
          style={{ marginTop: 14, background: "color-mix(in srgb, var(--signal-active) 18%, transparent)", border: "1px solid color-mix(in srgb, var(--signal-active) 50%, transparent)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 16px", cursor: "pointer" }}
        >
          Go to Home to sign in →
        </button>
      </div>
    );
  }
  return children;
}
