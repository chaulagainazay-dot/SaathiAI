# M54 Limitations

- **Single-host SQLite.** All readiness, retention, and recovery guarantees are
  single-host; no distributed consensus, multi-host consistency, or exactly-once
  execution is claimed.
- **Local browser certification only.** The M54 browser certification runs
  against a managed local BFF+UI with an isolated database; it is not run against
  a deployed or hardened environment.
- **Retention purge is dry-run only.** Eligible records are classified but never
  deleted; real deletion is deferred to a later milestone behind explicit owner
  confirmation and backup rehearsal.
- **Snapshot metrics.** Diagnostics are bounded snapshots over recent persisted
  executions, not distributed telemetry.
- **Manual uncertain-dispatch resolution.** A recorded-but-uncertain dispatch
  always requires manual operator resolution and is never resumed/replayed.
- **Compatibility wrappers remain** from M49–M53.
- **CI browser certification** — see `M54_BROWSER_CERTIFICATION.md` for whether
  the browser job runs in CI or remains local with a lightweight contract test.
- **No deployment, production OAuth/email, live connector mutation, financial
  execution, trading execution, or production authority.** Trading Guardian is
  unengaged and advisory-only.
