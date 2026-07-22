# M21.1 Validation

## Commands

```bash
cd /Users/macbookpro/SaathiAI
.venv/bin/pytest tests/test_m21_1_request_contract.py -q
.venv/bin/pytest tests/test_m21_0_production_config.py tests/test_m20_2_governed_local_inference.py tests/test_m20_3_opt_in_llm_caller_migration.py tests/test_m20_7_console_consolidation.py -q
.venv/bin/python -m saathi.inference.bypass_guard
```

## Expected

* M21.1 tests green
* M20.2/M20.3/M20.7/M21.0 regressions green
* Bypass guard `ok: true`
* `production_certified` remains false
* Chat default behavior unchanged (legacy path still present)

## Honesty

| Claim | Tier |
|-------|------|
| Contract validation | UNIT_TESTED |
| Kill before provider | UNIT_TESTED |
| Residual classification | SOURCE_INSPECTED + UNIT |
| Static bypass guard | UNIT_TESTED |
| Live Ollama | ENVIRONMENT_BLOCKED |
| Full suite | NOT_TESTED |
| Production certified | false |
