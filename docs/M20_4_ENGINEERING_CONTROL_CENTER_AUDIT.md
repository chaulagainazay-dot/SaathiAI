# M20.4 — Engineering Control Center & Supervised Read-Only Sessions Audit

**Date:** 2026-07-16
**Starting commit:** `51918a9e01cb263fd27173db6f4b14f23007e082`
**Branch:** `milestone/m7-security-engine`
**Preserved ancestors:** M20.0 `a9eb12a`, M20.1 OpenJarvis `cf83ced`, M20.2 inference `f38ca66`

## Numbering decision

The implementation brief labeled this work **M20.2**. Repository already contains:

| Label | Topic |
|-------|--------|
| M20.0 | Engineering Orchestrator pilot |
| M20.1 | OpenJarvis selective inference runtime |
| M20.2 | Governed local inference execution path |
| M20.3 | Opt-in LLM caller migration (`cheap_ask`, `prose_clean`) |

Therefore this milestone is canonical **M20.4** (Engineering Control Center + supervised read-only sessions). Brief labels “M20.2”/engineering were renumbered to avoid collisions with inference M20.2 and LLM adoption M20.3.

## Intake

- Clean working tree at start of implementation; origin synced `0 0`.
- No merge/rebase/bisect.
- M20.0 engineering package present and tested.
- Control Center uses `ControlCenterAggregator` cell pattern (read-only).
- M20.1/M20.2 inference packages orthogonal; not modified for this milestone beyond docs matrix.

## Delivered

1. Versioned engineering read model (`engineering_status.v1`)
2. Control Center facet + `/api/v1/control/engineering` + CLI
3. Repository integrity snapshots + quarantine on mutation
4. Bound read-only approvals for real Claude adapters
5. Store file locking + lease reclaim
6. Session lifecycle: paused / blocked / terminated / quarantined
7. CLI: control-center, approve-readonly, integrity, launch --mode readonly
8. Deterministic tests (mock pilot; Claude live environment-optional)

## Non-goals (still forbidden)

Autonomous coding writes, commits, pushes, merge, deploy, trading, unrestricted shell, credential mutation.
