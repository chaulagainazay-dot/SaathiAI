# M17.21 — Validation & Completion Report

## Scope delivered

Control Center **Registry Health** cell — read-only observability over the
existing harness registry (M17.18–M17.20). Deterministic health score and
status; CEO Daily Brief includes registry only when unhealthy; no second
dashboard, registry, or monitoring stack.

## Health model (authoritative `registry.health()`)

Safe fields only (no payload/secrets): overall_status, health_score,
schema_version, registry_revision, pilots/entries counts, lock state, size
limits, critical check inventory, load status/errors, last conflict/recovery,
warnings.

## Scoring (deterministic)

Start at 100. Deduct for load failures, skipped entries, failed validations,
size warnings/near-limit/oversize, conflict, recovery, lock held, quarantine,
critical inventory gap, schema mismatch, atomic write failure. Clamp 0–100.

| Status | Score / conditions |
|--------|-------------------|
| GREEN | score ≥ 80 and no hard load failure |
| YELLOW | 60–79 |
| ORANGE | 40–59 |
| RED | score < 40 or invalid/unsupported/too_large load |

CEO brief threshold: include when status ≠ GREEN **or** score < 80.

## Integration

- Control Center: `registry_health()` cell, overview `registry_health`, attention
  items for RED/ORANGE/YELLOW, API `/api/v1/control/registry` + `/diagnostics`
- CEO OS: `daily_brief` section "Registry Health" only when `include_in_ceo_brief`
- Alerts: via Control Center attention (no duplicate alert subsystem)

## Files changed

- `saathi/application_harness/registry.py` — health(), diagnostics, scoring
- `saathi/control_center/aggregator.py` — cell + attention + overview
- `saathi/control_center/api.py` — registry routes
- `saathi/ceo/service.py` — brief integration
- `tests/test_m17_21_registry_health.py`
- `saathi/repair/critical_checks.json` — 5 checks
- Docs: this file + roadmap / loop state / debt / capability

## Test results

- Focused M17.21: 19 passed
- Registry regression (M17.18–20): 86 passed
- Control Center tests: 11 passed
- Full suite: 1959 passed, 1 skipped, 0 failed
- release-check: exit 0

## Remaining limitations

- critical_checks_green is an operational proxy (does not re-run pytest each poll)
- lock_waiters always 0 (flock does not expose waiter count)
- No multi-host health federation
