# M55 Limitations

- **Single-host SQLite.** All health, metrics, backup, recovery, and readiness
  guarantees are single-host; no distributed consensus, multi-host consistency,
  or exactly-once execution is claimed.
- **Release readiness is advisory.** The release validator and gate report
  whether a deployment WOULD be ready; they enable nothing and are not a
  deployment authorization. Expected verdict is `READY_WITH_LIMITATIONS` because
  production, connectors, and cloud providers are intentionally disabled.
- **Backup restore is simulation only.** No destructive restore is performed;
  real restore and retention purge remain deferred behind explicit owner
  confirmation and a backup rehearsal.
- **Metrics are snapshots.** Bounded counters over recent persisted data, not
  distributed telemetry. `restart_count` is `UNKNOWN` on a single host.
- **Local browser certification only.** The operator-console certification runs
  against a managed local BFF+UI+Chromium with an isolated database; it is not
  run against a deployed environment, and the full run is kept local (backend
  contract tests are the CI-side guarantee).
- **Recovery scenarios** cover restart/dispatch/binding invariants on a single
  host; database- and worker-interruption are covered by those invariants, not by
  multi-host coordination.
- **No deployment, production mode, OAuth, production credentials, live email,
  live connector mutation, financial execution, or trading execution.** Trading
  Guardian is unengaged and advisory-only.
