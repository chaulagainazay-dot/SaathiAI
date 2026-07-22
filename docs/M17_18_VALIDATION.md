# M17.18 — Validation & Completion Report

## Scope delivered

Harness registry persistence is loaded on process bootstrap and written on
mutation so non-pilot discovery/import/trust state survives restart. Fail-closed
on corrupt/oversized/secret-bearing store payloads. External records cannot
rehydrate as executable. Pilot definitions still seed from code; disk may only
apply more-restrictive trust (revoke/quarantine/etc.). No second registry.

## Files changed

- `saathi/application_harness/registry.py` — load-on-boot, persist-on-mutate,
  fail-closed parsing, restrictive pilot overlay, diagnostics via `load_report()`
- `saathi/application_harness/cli.py` — `import-cli-anything` registers + persists
- `tests/test_m17_18_registry_persistence.py` — 15 deterministic tests
- `saathi/repair/critical_checks.json` — 5 blocking `registry.*` checks
- Docs: this file + roadmap / loop state / technical debt updates

## Test results

- **Focused M17.18:** 15 passed.
- **Harness regression (M17.3–7 + 18):** 91 passed.
- **Critical checks `registry.*`:** 5/5 green (11 pytest targets).
- Trading Guardian: unengaged (asserted no trading surface in registry module).

## Architecture reused

Single module `saathi/application_harness/registry.py` remains authority.
`data/application_harnesses/registry.json` is the sole durable store (schema_version 1).
No new DB, no second registry, no change to `run_harness_action` / ledger / missions.

## Remaining / deferred

- Multi-user concurrent registry writers (single-process load is the contract today)
- Optional Control Center cell for load diagnostics (summary already exposes `load`)
- Production OS auto-scheduling and external alert transports remain environment-gated
