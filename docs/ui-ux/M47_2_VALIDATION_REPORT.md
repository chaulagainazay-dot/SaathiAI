# M47.2 — Validation Report

**Date:** 2026-07-22  
**Branch:** `milestone/saathios-ui-ux`  
**Baseline:** `dc177c8f3925cd6d5da34babdd5c31ce54fc3fb1`

## Commands

| Check | Command | Result |
|---|---|---|
| Unit tests | `cd saathi-os && npm test` | ✅ 24/24 pass |
| Production build | `cd saathi-os && npm run build` | ✅ exit 0 — 43 routes incl. new canonical |
| Lint | `npm run lint` | ⚠️ pre-existing unconfigured `next lint` interactive setup (not introduced by M47.2) |
| Diff whitespace | `git diff --check` | ✅ clean |
| Secret scan (heuristic) | rg private keys / hard-coded api keys in new shell paths | ✅ no matches |

## Unit tests covered

- 4 groups / 12 primary areas / no duplicate ids or hrefs
- CONTROL department key no longer double-defined as two competing studio/control entries without studio key
- Mobile tab model
- Trading advisory flags in nav
- Trading page source safety (no execute handlers)
- Approvals honesty (unavailable ≠ zero; no decide call)
- Command palette no approve→finance
- TopBar unavailable wording
- Settings experience ≠ authority
- Shell Esc / `]` / MOBILE_TABS

## HTTP smoke (dev server `:3100`)

All **200**:

`/` `/command` `/missions` `/projects` `/studio` `/monitoring` `/approvals` `/trading` `/settings` `/agents` `/business`

HTML/RSC includes: `shell-sidebar`, `shell-topbar`, `shell-statusbar`, `Ask Saathi`, Trading `Advisory only` / `NO_TRADING` / `Execution disabled`, Settings `Theme` / `Experience mode`.

CSS chunk contains `shell-sidebar` (22 matches).

## Browser notes

- Port 3000 was already occupied by a prior process; verification used **:3100** against this working tree.
- Full interactive Playwright screenshot suite not committed (repo does not require large screenshots).
- Backend offline yields honest unavailable/error states on command/approvals/monitoring (verified by page design + prior empty/error components).

## Inline styles

| Metric | Count |
|---|---|
| Baseline (pre-M47.2) | 1611 |
| After M47.2 | 1635 |
| Delta | +24 |

Increase is limited to new route/shell files; no mass migration of legacy pages. Net preferred zero increase not fully met — documented limitation.

## Safety confirmations

- Trading Guardian: no order buttons, no broker connect, advisory badges, BlockedState
- Approvals: no `platformDecideApproval` from inbox shell
- TopBar: does not execute privileged actions
- Experience mode: copy density only
- No deploy, no production, no credentials, no M42–M46 changes

## Verdict

**Validation pass with known limitations** (lint unconfigured; +24 inline styles; no forced legacy redirects; interactive a11y not formally WCAG-certified).
