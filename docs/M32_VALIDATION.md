# M32 — Validation

## Focused tests

- `tests/test_m32_provider_adapter.py` — **84 passed** (selection, contract, config,
  request/response normalization, error taxonomy, retry decisions, idempotency store,
  rate limits, verification/drift, redaction/evidence).
- `tests/test_m32_provider_runtime.py` — **44 passed** (bounded execution, timeouts,
  cancellation, shutdown, retry integration, idempotency integration, rate limits,
  health/quarantine, shadow/simulation/dry-run, CANARY/ACTIVE rejection, composed
  eligibility, non-mutating reads, failure injection, invariants).
- Combined: **128 passed**.

## Regression (M26–M31)

| Suite | Result |
|-------|--------|
| `test_m26_inference_operations` | 50 passed |
| `test_m27_connector_framework` | 32 passed |
| `test_m28_connector_migration` | 26 passed |
| `test_m29_connector_identity` | 28 passed |
| `test_m30_connector_conformance` | 38 passed |
| `test_m31_credentials` | 43 passed |

## M25 production certification

| Suite | Result |
|-------|--------|
| `test_m25_cert_evidence` | 18 passed |
| `test_m25_live_provider_certification` | 14 passed |

## Canonical checks

- `git diff --check` → clean.
- Secret scan over new provider/testing/test files → clean (only synthetic markers).
- Connector conformance verify → `ok: true`, all 4 gov connectors
  `CERTIFIED_WITH_LIMITATIONS`, `connector_bypasses: 0`, drift `ok: true`.
- Connector certification drift (post re-assess) → fresh.
- Provider bypass check → `production_bypasses: 0` (M32 provider runtime allowlisted
  as a governed call site).
- Provider verification (CLI `verify`) → `SIMULATION_VERIFIED`.
- Provider verification drift (CLI `drift`) → `ok: true`.
- M32 evidence (`docs/evidence/m32/`, 16 files + verification registry) → leak-scan clean.

## Note on the bypass-guard edit

Allowlisting `saathi/connectors/providers/runtime.py` in `gov/bypass_guard.py`
(a fingerprinted file) drifted the 4 gov connector certifications to STALE. They
were re-assessed via the canonical `python -m saathi.connectors.conformance
assess-all`, restoring `CERTIFIED_WITH_LIMITATIONS` (fresh). The regenerated M30
certification store + per-connector fingerprints are committed as the correct new
state. The M28 `deprecation_events.jsonl` append (pure test side-effect, new
timestamps only) was restored and NOT committed.

## Full suite

`.venv/bin/python -m pytest -q` → **3458 passed, 1 skipped, 0 failed** (715.75s).
