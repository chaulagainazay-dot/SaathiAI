# M58 — Security Review

M58 is a presentation-layer milestone. No backend files changed; no new capability was
exposed.

## Boundaries preserved (verified visible + truthful)
- PlatformAgentRuntime remains canonical; ExecutionGateway remains the sole
  registered-tool authority (shown on the Topology node).
- Connector mutations DRY_RUN_ONLY; financial execution DISABLED; trading DISABLED;
  Trading Guardian UNENGAGED_ADVISORY_ONLY; production NOT AUTHORIZED — all rendered on
  the readiness panel, ops Security node, and status strips.
- No `0.0.0.0` bind; no public tunnels; localhost-only (Localhost node states this).
- Multi-host mode disabled.

## No new attack surface
- All calls go to existing `/api/v1/platform/*` endpoints; no new endpoints, no
  connector mutation, no financial/trading actions.
- Approval controls remain server-authorized; browser state never implies authority
  (Approvals panel is read/summarise + link only).
- Destructive binding actions retain `window.confirm` gating.
- `no_unsafe_actions` cert gate confirms no button matches the unsafe-action lexicon.

## Data exposure
- No secrets, raw DB details, or filesystem paths surfaced. Config panel prints the
  same `/config` payload as before (no new fields).
- Credential scan on all changed files: clean. The only password literal is the
  cert-only fixture `CertOwnerPassw0rd!` in `m58_browser_cert.mjs` (isolated cert DB),
  matching the existing M54/M57 harness pattern.

## Certification
Anonymous access still denied server-side (unchanged). `git diff --check` clean.
Backend unchanged → existing backend security posture intact (4964-test suite from
M57.1 remains valid; not re-run because no backend code changed).
