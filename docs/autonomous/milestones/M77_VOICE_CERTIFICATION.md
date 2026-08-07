# M77 — Voice Browser, Resource, Security, and Regression Certification

Date: 2026-07-28

Verdict: `M77_COMPLETE_WITH_LIMITATIONS`

## Outcome

The Voice Output Foundation passed its backend, native-provider, frontend-unit,
full-regression, build, lint, dependency-consistency, production-dependency,
secret, and localhost lifecycle checks. The dedicated production browser journey
did not pass within the browser skill's bounded retry budget, so end-to-end browser
speech playback is not certified and no PASS evidence is inferred.

This is a certification limitation, not a concealed provider failure. A separate
temporary API diagnostic repeated the browser request (`provider=voxcpm`,
VoxCPM disabled, macOS fallback enabled) against the real `/usr/bin/say` provider.
It completed through `macos_system`, set `fallback_used=true`, produced a local
113,700-byte artifact, and exposed no private path.

## Browser evidence

The managed M77 harness:

- built the production Next.js application;
- bound Uvicorn and Next.js only to `127.0.0.1:8765` and
  `127.0.0.1:3000`;
- created a temporary database and artifact directory and removed both;
- passed backend/frontend startup, owner bootstrap, sign-in, IELTS fixture,
  agent-browser content/snapshot/overlay, chat HTTP, isolated chat fixtures,
  assistant Speak-action, and visible-focus gates;
- ran the retained M64 authenticated shell regression successfully:
  21 hard, 12 state, 6 responsive, and 3 accessibility gates, with zero page,
  unexpected-console, or framework-overlay errors;
- accepted one real speech request before the final attempt timed out waiting for
  the browser dock to reach `completed`.

Across the initial run and two focused retry cycles, two failures were brittle text
locators caused by nested icon/metadata text. Those were diagnosed and fixed. The
final run reached synthesis but did not expose the completed client state within
30 seconds. The browser skill's retry ceiling was then exhausted. The persisted
certificate therefore remains `FAIL`; IELTS browser read-aloud, unavailable-state,
browser playback/stop, responsive voice views, browser context invalidation, and
browser logout cleanup remain un-certified by M77.

## Regression and quality gates

- Voice backend: 15 passed.
- Full backend: 5,272 passed, 1 skipped, 0 failed, 341 warnings in 875.34 seconds.
- Frontend: 189 passed.
- ESLint: passed.
- Optimized production build: passed during every managed M77 browser attempt;
  82 static routes.
- Typecheck: no configured typecheck script.
- Python dependency consistency: `pip check` passed.
- Python CVE audit: `pip-audit` is not installed; no dependency was installed to
  add it.
- Production npm audit: zero vulnerabilities.
- Full development npm audit: nine high advisories confined to the existing
  ESLint/minimatch/brace-expansion toolchain; registry remediation requires a
  breaking ESLint major upgrade.
- Changed production-code secret scan: 19 files, zero findings.
- `git diff --check`: passed before final documentation.

## Resource and runtime posture

- Machine: Apple M2, arm64, 8 GiB unified memory.
- Final free disk: 75,868,772 KiB (about 72.4 GiB).
- Native English AIFF benchmark retained from M74: cold artifact-ready
  4,539.20 ms, warm 1,663.31 ms, 48,332,800-byte provider max RSS,
  149,684-byte artifact, and 46.04 ms process cancellation.
- The cold result misses the suggested 2-second target; the warm result meets it.
- Queue depth is 8; default heavy-provider concurrency is 1.
- No model weights, GGUF files, VoxCPM package, large dependency, cache, generated
  private audio, database, log, or PID file was retained.
- No process listened on ports 3000 or 8765 after harness cleanup.

## Security posture

The speech layer retains safe argument arrays, bounded subprocess execution,
resolved artifact confinement, authenticated tenant/workspace/owner access, safe
404 behavior, private no-store audio responses, range bounds, cloning disabled
below the provider boundary, loopback-only optional service configuration, explicit
model paths, no startup download, no raw stack/path response, and finite timeouts,
queueing, concurrency, retention, and restart reconciliation.

## Certification boundary

The platform can synthesize English speech now through the authenticated backend and
the native macOS provider. The shell and IELTS controls are implemented and
deterministic-tested, but their production browser playback journey is not certified
by M77. VoxCPM remains implemented as an optional adapter only: not installed, not
configured, no model present, inference not verified, quality not reviewed, and not
certified. Nepali remains unsupported-not-verified. Cloning remains
`CAPABILITY_DISABLED`. No production use is authorized.
