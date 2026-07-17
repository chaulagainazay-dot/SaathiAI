# M21.2 — Validation

## Focused suite

```bash
.venv/bin/python -m pytest tests/test_m21_2_provider_governance.py -q
# 93 passed
```

## Regressions

```bash
.venv/bin/python -m pytest tests/test_m21_1_request_contract.py tests/test_m21_0_production_config.py -q
# 45 passed
.venv/bin/python -m pytest tests/test_m20_2_governed_local_inference.py tests/test_m20_3_opt_in_llm_caller_migration.py tests/test_m20_7_console_consolidation.py tests/test_m20_9_final_certification.py -q
# 100 passed
.venv/bin/python -m saathi.inference.bypass_guard
# ok
```

## Evidence tiers

| Claim | Tier |
|-------|------|
| Descriptor / decision / circuit / cost unit logic | UNIT_TESTED |
| M20/M21 regressions | UNIT_TESTED |
| Live Ollama | ENVIRONMENT_BLOCKED / NOT_TESTED |
| Full repository suite | NOT_TESTED |
| Production certification | false |

## production_certified

**false**
