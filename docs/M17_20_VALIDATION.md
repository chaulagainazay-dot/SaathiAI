# M17.20 — Validation & Completion Report

## Scope delivered

Multi-writer harness registry concurrency for local-first SaathiOS:

- process-safe exclusive `fcntl.flock` + in-process `threading.RLock`
- durable `revision` CAS (monotonic integer in registry envelope)
- mutation flow: validate → lock → reload durable state → re-check → apply →
  atomic persist → unlock
- `applied_ops` bounded list for mutation idempotency
- bounded lock timeout (default 5s) → `RegistryBusy` / `LOCK_TIMEOUT`
- crash-safe atomic write preserved from M17.19
- readers only observe atomically replaced `registry.json` (never `.tmp`)

**Not claimed:** multi-host distributed consensus, cross-machine locks, or
linearizability under NFS/shared mounts beyond POSIX flock behavior.

## Concurrency model

| Layer | Mechanism |
|-------|-----------|
| In-process | `threading.RLock` |
| Cross-process | `fcntl.LOCK_EX` on `registry.json.lock` |
| Stale recovery | Kernel releases flock on process death; next acquirer emits recovery evidence |
| Version token | `revision` integer (not timestamps) |
| Idempotency | `applied_ops` list (≤64) |

## Conflict policy

- Same identifier + incompatible body → `RegistryConflict`
- Stale revision on persist → `RegistryConflict` (reload; no overwrite)
- Trust broadening still rejected (M17.19)
- Built-in pilots not replaceable via import
- Independent new identifiers serialize under lock and both survive

## CLI exit codes (import)

| Code | Meaning |
|------|---------|
| 0 | success |
| 3 | validation failure |
| 4 | lock timeout |
| 5 | revision/mutation conflict |

## Files changed

- `saathi/application_harness/registry.py` — lock, revision, mutation path
- `saathi/application_harness/cli.py` — contention/conflict exit codes
- `tests/test_m17_20_registry_concurrency.py` — focused suite
- `saathi/repair/critical_checks.json` — 5 blocking checks
- Docs: this file + roadmap / loop state / technical debt / capability matrix

## Test results

- Focused M17.20: 33 passed
- M17.18 + M17.19: 53 passed (combined focused path 86)
- Related harness suite: 87 passed
- Full suite: 1940 passed, 1 skipped, 0 failed
- release-check: exit 0

## Remaining limitations

- Single-host / local filesystem flock only
- Multi-writer across network filesystems not guaranteed
- `persist()` of pure in-memory edits uses CAS against last loaded revision
  (prefer `register` / `import_records` for multi-writer safety)
