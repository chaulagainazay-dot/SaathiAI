# M57 Browser Certification

Harness: `saathi-os/scripts/m57_browser_cert.mjs` (`npm run cert:m57`).
Evidence: `docs/platform/m57_evidence/m57_browser_cert.json` + `screenshots/`.

## Lifecycle
clean ports → isolated `SAATHI_PLATFORM_DB` → start BFF (`saathi.server:app` with
the M57 single-host heartbeat, CORS scoped to the managed UI origin) → seed owner
+ binding + governed execution → start the Next.js frontend → drive the
authenticated `/platform/ops` operator console in headless Chromium → screenshots
+ evidence JSON → teardown.

Exit 0 only when every hard gate passes. Never fabricates network success, never
marks a PR ready, never enables connectors/financial/trading.

## M57 gates (in addition to the M54–M56 gates)
- **node_local_healthy** — the running BFF heartbeats `node-local`; `/cluster/
  node-health` reports `healthy: true` with a small heartbeat age.
- **cold_load_recovery** — after the first cold navigation the operator console's
  cluster cards populate (≥5 cards) with no fatal "Console error" banner (a
  retryable "Console notice" is allowed).
- **launcher_contract** — `bin/saathi-local` opens `http://localhost:3000`, sets
  `NEXT_PUBLIC_SAATHI_API=http://127.0.0.1:8765`, never binds `0.0.0.0`; the macOS
  shortcut script calls `saathi-local open`.

## macOS global keystroke
The harness does **not** simulate a system-wide `⌥⌘B` keypress (unsafe/unreliable
in a headless environment). It certifies the shortcut **definition and target**:
the script exists, points at the stable launcher, and the launcher opens the
correct URL. Global key assignment remains operator-verified — see
`M57_MACOS_SHORTCUT.md`.

## Stop → stale / restart → healthy
Heartbeat expiry (stop → stale) and refresh (restart → healthy) are certified at
the unit level (`tests/test_m57_local.py::test_heartbeat_expiry_makes_node_local_stale`,
`::test_heartbeat_refresh_makes_node_local_healthy`).

## Result
The recorded verdict and per-gate results are in
`docs/platform/m57_evidence/m57_browser_cert.json`.
