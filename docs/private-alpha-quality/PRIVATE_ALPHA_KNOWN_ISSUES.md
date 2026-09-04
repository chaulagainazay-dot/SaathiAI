# SaathiOS Private Alpha — Known Issues

**Build:** `6b55013` · **Updated:** 2026-08-02
**Status:** no open P0, no open P1. Release is not blocked by a known defect.

Read this before a tester session. Reporting something already listed here is still useful —
it tells us how much it actually hurts.

---

## Open

### P2 — A rebuild under a running server breaks the app while it reports healthy
`PA-D-002`. Rebuilding `.next` while `next start` is running leaves the server serving chunk names
that no longer exist. You get "SaathiOS failed to load" with a `ChunkLoadError`, even though the
URL returns HTTP 200. **Workaround:** always restart the server after a build. Hit twice so far.

### P2 — First-run and returning-user states are contradictory
`PA-D-003`. `/unlock` can show "Set up sign-in" and ask you to choose a password, even though your
platform account already has one. Two independent auth systems disagree about whether you are set
up. **It does not mean your data was lost.**

### P2 — Expired-session recovery lands on "Bootstrap + login"
`PA-D-004`. After a session expires you are correctly returned to a sign-in form, but the only
button reads "Bootstrap + login", which sounds like first-time installation. It is the sign-in
control. Wording fix pending.

### P2 — No skip-navigation link
`PA-D-005` / `A11Y-001`. Keyboard and screen-reader users traverse the full sidebar before reaching
main content on every route. 43 focusable controls, 4 nav landmarks, no skip link.

### P2 — `ollama` listens on all network interfaces
`PA-D-006`. Every SaathiOS listener is correctly loopback-only (3000, 8765, 8766). The third-party
`ollama` model server binds `*:11434`. On an untrusted network that endpoint is reachable from other
machines. **Recommendation:** set `OLLAMA_HOST=127.0.0.1`. Outside the SaathiOS repository.

### P2 — Touch targets below 44 px
`A11Y-002`. 32 of 49 interactive controls measured under 44×44 px. Real phone impact unconfirmed —
see the limitation below.

### P3 — Breadcrumb truncates
`PA-D-007`. Shows `Pla...` instead of `Platform` at narrower widths.

---

## Environment limitations (not defects)

### No Nepali voice exists on this machine
The browser exposes **180 voices across 49 languages and zero `ne-*` voices**; macOS `say -v '?'`
lists 184 with no Nepali. Nepali text cannot be spoken by a native Nepali voice here. What matters
is whether the fallback is honest — **silence with no explanation is a defect, so report it.**

### "Provider: Unavailable" in the voice panel when signed out
Expected. Voice endpoints return `401 ANONYMOUS_PROHIBITED` to anonymous callers — correct security
behaviour, not an outage. It should clear once you sign in.

### Google Chrome is not installed
Only Brave Browser 150 is present. All browser evidence was collected in headed Brave.

---

## Deliberately unavailable

Not bugs. Do not report these:

- provider login, OAuth, broker connectivity
- live trading, order execution, financial account access
- public registration or self-signup
- public deployment

All 54 Trading Guardian routes are advisory and non-executable:
`TRADING_GUARDIAN_UNENGAGED_ADVISORY_ONLY`, `CONNECTOR_MUTATIONS_DRY_RUN_ONLY`,
`PRODUCTION_NOT_AUTHORIZED`, `AUTHORITY_FAIL_CLOSED`, `permits_live_execution = False`.

---

## Not yet validated by anyone

**No real tester session has run.** Automation could not sign in (all accounts are password
protected, and bootstrapping one would create a user and organization). So these were never
exercised by a human or a machine:

workspace switching · project create/edit/archive · full mission lifecycle · approvals
· assistant chat and streaming · voice playback, Stop, interruption and cleanup · authenticated
diagnostics and operations · 143 of 145 routes · the individual non-live labelling of all 54
trading pages.

Unknown P0 and P1 defects may exist in any of the above. Absence of evidence is not evidence of
absence — that is precisely why real-user validation is the gate.
