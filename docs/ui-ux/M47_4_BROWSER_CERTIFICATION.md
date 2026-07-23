# M47.4 — Browser Certification

**Date:** 2026-07-23  
**Harness:** `saathi-os/scripts/m47_4_browser_cert.mjs`  
**Machine evidence:** `docs/ui-ux/m47_4_evidence/browser_cert_result.json`  
**Starting HEAD:** `28afe1165f177f63eea8f058476a6a47f3588453`

## Lifecycle

1. Ensure production build (`.next`)
2. Start `next start` on free port `3110` (managed child process)
3. Wait until `GET /` healthy
4. Launch Chromium via Playwright (headless)
5. Run page / keyboard / theme / density / responsive / legacy load suites
6. Capture console + page errors + network failures
7. Write JSON + screenshots under `docs/ui-ux/m47_4_evidence/`
8. SIGTERM server child

Command:

```bash
cd saathi-os && npm run build && npm run test:browser-cert
```

## Gates (final run)

| Gate | Result |
|---|---|
| pagesOk (10 canonical) | ✅ |
| keyboardOk (⌘K, Esc, g-h/c/p/m/a) | ✅ |
| keyboardCopilot (`]`) | ✅ |
| themeOk (dark/light/system) | ✅ |
| densityOk (compact/standard/comfortable) | ✅ |
| responsiveOk (phone/tablet/laptop/desktop/wide) | ✅ |
| noFatalPageErrors | ✅ |
| noFatalConsole (after backend-noise filter) | ✅ |
| tradingAdvisory | ✅ |

**Verdict:** `M47_4_COMPLETE_WITH_LIMITATIONS`

## Canonical pages

All HTTP 200-class, non-blank, shell main present, no React error boundary, no Next error overlay:

`/` `/command` `/missions` `/projects` `/approvals` `/monitoring` `/business` `/agents` `/trading` `/settings`

Trading body includes advisory-only / execution disabled / NO_TRADING language.

## Keyboard

| Shortcut | Result |
|---|---|
| Meta+K | Opens command palette |
| Escape | Closes palette |
| `]` | Opens Ask Saathi panel |
| Escape | Closes panel |
| `g h` → `/` | ✅ |
| `g c` → `/command` | ✅ |
| `g p` → `/projects` | ✅ |
| `g m` → `/missions` | ✅ |
| `g a` → `/approvals` | ✅ |

## Themes & density

Settings controls applied; Home readable under dark/light/system; Approvals no horizontal overflow under compact/standard/comfortable.

## Responsive

| Viewport | Layout expectation | Result |
|---|---|---|
| phone 390 | mobile tabs visible, sidebar hidden | ✅ (after CSS cascade fix) |
| tablet 834 | desktop sidebar | ✅ |
| laptop/desktop/wide | desktop sidebar, no H-scroll | ✅ |

## Runtime console

- **Page errors:** none  
- **Fatal app console:** none after filtering  
- **Expected noise:** CORS / failed fetches to `localhost:8765` when BFF is offline or not CORS-aligned with UI origin `127.0.0.1:3110` (documented limitation; not treated as shell failure)

## Bug found & fixed during certification

**Mobile tab bar never appeared on phone.** Source CSS set `.m-tabs { display: grid }` inside an early `@media (max-width: 699px)` block, then later defined `.m-tabs { display: none; ... }` which always won the cascade.  
**Fix:** phone display overrides for `.m-top` / `.m-tabs` moved **after** the base rules in `app/globals.css`. Rebuilt and re-certified.

## Limitations

1. Backend not co-origin → CORS/SSE noise  
2. Screenshots are local evidence; large PNG set may be gitignored or partially committed  
3. Full WCAG automated audit not run  
4. No redirects implemented (by design)

## Hydration

No React hydration failure strings in page errors. No blank root after load.
