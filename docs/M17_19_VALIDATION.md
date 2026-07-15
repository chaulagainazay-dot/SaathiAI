# M17.19 — Validation & Completion Report

## Scope delivered

Harden harness registry persistence against untrusted JSON: versioned envelope,
bounded read, strict entry validation (shared by boot / register / import),
restrictive-only pilot overlays, atomic writes (tmp → fsync → replace), fail-closed
envelope rejection with built-in pilots preserved, bounded diagnostics.

**Policy:** invalid/oversized/unsupported **envelope** rejects the entire payload;
individually invalid **entries** are skipped (existing M17.18 isolation); duplicate
IDs reject the entire payload. Trust from disk may only apply **restrictive**
overlays to code-seeded pilots — never broaden or replace pilot definitions.

## Persistence schema

```json
{
  "schema_version": 1,
  "generated_at": "ISO-8601 UTC",
  "harnesses": [ /* HarnessDefinition fields only */ ]
}
```

- Load accepts legacy alias `entries` → persisted as `harnesses`.
- Unsupported `schema_version` (≠ 1 or future > 1) fails closed.
- Unknown top-level / entry fields: reject (security-sensitive and otherwise).

## Limits (centralized constants)

| Limit | Default |
|-------|---------|
| Max file size | 256 KiB |
| Max entries | 256 |
| Max id length | 80 |
| Max name | 120 |
| Max description | 2000 |
| Max nest depth | 8 |
| Max list/map size | 64 |
| Error detail | 40 chars |

## Atomic write

1. Write `registry.json.tmp` with mode 0600
2. `flush` + `fsync`
3. `os.replace` onto `registry.json`
4. Best-effort dir fsync; remove leftover tmp
5. On failure: previous file preserved; emit `atomic_write_failed`

## Files changed

- `saathi/application_harness/registry.py` — validation, limits, atomic write, events
- `saathi/application_harness/cli.py` — strict import; exit 3 on validation failure
- `tests/test_m17_19_registry_untrusted_persistence.py` — focused suite
- `saathi/repair/critical_checks.json` — 5 blocking `registry.*` checks
- Docs: this file + roadmap / loop state / technical debt / capability matrix

## Test results

- **Focused M17.19:** 38 passed
- **M17.18 regression:** 15 passed
- **Related harness/registry:** 140 passed
- **Registry critical targets (10 checks):** 29 passed
- **Full suite:** 1907 passed, 1 skipped, 0 failed
- **release-check:** exit 0 (storage/config/database/backup+restore/secret_scan green)
- Trading Guardian: unengaged (static ban scan green)

## Architecture reused

Single `registry.py` authority; same `STORE` path; no second registry, ledger,
mission engine, or trust framework. Event bus best-effort emit for diagnostics.

## Remaining / deferred

- Unlimited quarantine rotation beyond 3 sidecars (bounded helper present, optional)
- Multi-writer concurrent registry editors
- Production OS auto-scheduling / external alert transports (prior deferred)
