# M25 Validation

## Focused

```bash
python -m pytest tests/test_m25_live_provider_certification.py -q
python -m saathi.inference.live_cert_m25
python -m saathi.inference.release_check
python -m saathi.inference.runtime_gate
```

## Live cases (this host)

All live cases: **ENVIRONMENT_BLOCKED** (provider unavailable).

| Case | Status |
|------|--------|
| Non-stream | ENVIRONMENT_BLOCKED |
| Stream | ENVIRONMENT_BLOCKED |
| Cancel | ENVIRONMENT_BLOCKED |
| Timeout | ENVIRONMENT_BLOCKED |
| Circuit | ENVIRONMENT_BLOCKED |
| Settlement | ENVIRONMENT_BLOCKED |
| Chat e2e | ENVIRONMENT_BLOCKED |
| Kill switch live | ENVIRONMENT_BLOCKED |
| Privacy canary live | ENVIRONMENT_BLOCKED |
| Performance | ENVIRONMENT_BLOCKED |

## Non-live gates (this host)

| Gate | Status |
|------|--------|
| residual_exceptions | PASS (0) |
| durable_governance | PASS |
| cloud_fallback_disabled | PASS |
| endpoint_allowlist | PASS |
| m25_no_mock_as_live | PASS |
| production_certified | false |

## Full suite

```bash
python -m pytest -q
```

**3085 passed, 1 skipped, 0 failed** (670.81s).
