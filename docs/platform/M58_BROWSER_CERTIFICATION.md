# M58 — Browser Certification

## Harness
`saathi-os/scripts/m58_browser_cert.mjs` (reuses the M54–M57 scaffold): isolated
SQLite BFF (`SAATHI_PLATFORM_DB`, CORS scoped to the UI port), seeded owner + binding +
governed read-only execution, real Chromium via Playwright, UI wired to the cert BFF
via `NEXT_PUBLIC_SAATHI_API`. Run: `npm run cert:m58` (dev) / `cert:m58:build` (prod
build) / `cert:m58:soft` (allow soft-gate limitations). Evidence:
`docs/platform/m58_evidence/`.

## Result: M58_BROWSER_CERTIFIED — all hard gates pass
| Gate | Result |
|---|---|
| spatial_core_rendered | PASS — `SAATHI READY` (not blocked) |
| module_ring_rendered | PASS — 12 nodes |
| connections_rendered | PASS — 16 paths |
| safety_visible | PASS — DRY_RUN_ONLY + DISABLED + LOCAL_OR_TEST |
| production_unauthorized_visible | PASS |
| module_navigation | PASS — aria-current + panel |
| no_unsafe_actions | PASS — none offered |
| ops_constellation | PASS — 15 paths, NON-PRODUCTION, Runtime ok |
| ops_detail_drawer | PASS — glass drawer opens on select |
| responsive_mobile | PASS — 12 nodes at 390×844 |
| reduced_motion | PASS — core + nodes render statically |
| no_page_errors | PASS — 0 |
| no_new_hydration_errors | PASS — shell baseline 0, spatial 0 |

## Baseline attribution
A non-M58 control page (`/agents`) is loaded first to attribute any hydration warning
to the shared shell vs. M58 pages. Baseline was 0 and spatial pages added 0 — the
spatial surfaces are hydration-clean.

## Regression (no existing certification broken)
- M54 `/platform` → **M54_BROWSER_CERTIFIED**
- M55 ops → **M55_BROWSER_CERTIFIED**
- M56 distributed runtime → **M56_BROWSER_CERTIFIED**
- M57 localhost hardening → **M57_BROWSER_CERTIFIED**

All original `data-testid`s on `/platform` and `/platform/ops` were preserved and kept
populated on load; certified values render inline on the constellation node cards (the
detail drawer intentionally carries no testids to keep values unique).
