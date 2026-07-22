# M22 Validation

## Focused tests

```bash
.venv/bin/python -m pytest \
  tests/test_m22_provider_migration.py \
  tests/test_m21_3_residual_path_migration.py \
  tests/test_m21_4_runtime_consolidation.py \
  tests/test_model_router_providers.py \
  tests/test_failure_injection.py \
  tests/test_infra_events.py \
  tests/test_m20_3_opt_in_llm_caller_migration.py \
  -q
```

**Result (pre-full-suite):** 215 passed, 0 failed.

## Release check

```bash
.venv/bin/python -m saathi.inference.release_check
```

Expect: ok=true, production_certified=false, m22_facade_check=true.

## Residual manifest

```bash
.venv/bin/python -c "from saathi.inference.runtime_gate import validate_residual_manifest; print(validate_residual_manifest())"
```

Expect: GateState.PASS, exception_count=3.

## Full suite

```bash
.venv/bin/python -m pytest -q --tb=line
```

**Result:** 2951 passed, 1 skipped, 0 failed (~660s).

## Secret scan

`scan_content` over `saathi/**/*.py`: **clean**.

## Release check / residual

* release_check: ok=true, production_certified=false, m22_facade_check=true
* validate_residual_manifest: PASS, exception_count=3
