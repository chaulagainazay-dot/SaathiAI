# M60 — Browser Certification

Harness: `saathi-os/scripts/m60_browser_cert.mjs`
(`npm run cert:m60:build` production; `npm run cert:m60` dev regression).

Isolated 127.0.0.1 BFF, real seeded fixtures (owner, binding, execution, project,
active mission, pending approval), `next build` + `next start`, headless Chromium.

Fixtures exercise the LIVE paths: mission creation via UI (`POST /missions`),
approval preparation (`POST /approvals`), governed read-only execution
(`POST /execute`). Verdict and per-gate results: see `m60_evidence/m60_browser_cert.json`.
