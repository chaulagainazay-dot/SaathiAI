# M24 Validation

## Focused tests

```bash
python -m pytest tests/test_m24_durable_provider_governance.py -q
```

Coverage includes: durable circuit restart, reservation concurrency, settle idempotency, recovery, multi-process budget, SSRF, release_check, runtime_gate M24 checks.

## Related regression

```bash
python -m pytest tests/test_m21_2_provider_governance.py tests/test_m22_provider_migration.py tests/test_m23_governed_chat_default.py tests/test_m21_4_runtime_consolidation.py -q
```

## Release / gate

```bash
python -m saathi.inference.release_check
python -m saathi.inference.runtime_gate
```

## Full suite

```bash
python -m pytest -q
```

## Critical invariants

```text
residual exceptions = 0
process-local production authorities = 0
production_certified = false
cloud fallback default = false
Trading Guardian = UNCHANGED / UNENGAGED
```
