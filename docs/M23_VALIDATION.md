# M23 — Validation Plan and Results

## Focused

```bash
.venv/bin/python -m pytest tests/test_m23_governed_chat_default.py -q
```

Expected: all pass.

## Regression (M22 / M21 / chat)

```bash
.venv/bin/python -m pytest \
  tests/test_m22_provider_migration.py \
  tests/test_m21_0_production_config.py \
  tests/test_m21_1_request_contract.py \
  tests/test_m21_2_provider_governance.py \
  tests/test_m21_3_residual_path_migration.py \
  tests/test_m21_4_runtime_consolidation.py \
  tests/test_chat.py \
  -q
```

## Full suite

```bash
.venv/bin/python -m pytest -q --tb=line
```

## Release / gate

```bash
.venv/bin/python -m saathi.inference.release_check
.venv/bin/python -m saathi.inference.runtime_gate --json
```

## Results (filled at milestone close)

See `docs/M23_FINAL_REPORT.md`.
