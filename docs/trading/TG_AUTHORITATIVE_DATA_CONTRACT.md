# Authoritative Data Contract (M177)

## Classifications

| Code | Authoritative? | Use |
| --- | --- | --- |
| `HISTORICAL_AUTHENTICATED` | Yes | Proven external historical series |
| `HISTORICAL_LOCAL_DATASET` | Yes | Local operator-provided historical files |
| `SYNTHETIC_VALIDATION` | No | M62 synthetic regimes for research demos |
| `FIXTURE_TEST_ONLY` | No | Unit/integration tests only |
| `INCOMPLETE` | No | Failed/missing mapping — no metrics |
| `REJECTED` | No | Explicit rejection |

## Policy

`AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA = true`

Every result includes provenance: fingerprint, date range, instruments, timeframe,
missing-data stats, fee/slip assumptions, strategy/policy versions.

## Fail-closed

If historical mapping fails → `INCOMPLETE` with `metrics: null`. Never invent numbers.
