# M21.3 Validation

## Focused suite (this session)

```bash
.venv/bin/python -m pytest tests/test_m21_3_residual_path_migration.py -q
.venv/bin/python -m pytest tests/test_m21_2_provider_governance.py tests/test_m21_1_request_contract.py tests/test_m21_0_production_config.py -q
.venv/bin/python -m pytest tests/test_m20_2_governed_local_inference.py tests/test_m20_3_opt_in_llm_caller_migration.py tests/test_m20_7_console_consolidation.py tests/test_m20_9_final_certification.py -q
.venv/bin/python -m saathi.inference.bypass_guard
.venv/bin/python -m saathi.inference.release_check --explain
git diff --check
```

## Outcomes

| Suite | Result |
|-------|--------|
| test_m21_3_* | **PASS** (43) |
| M21.0–M21.2 combined | **PASS** (181 with m21_3) |
| M20.2/3/7/9 | **PASS** (after test caller + chat assertion updates) |
| release_check | **PASS** |
| bypass_guard | **PASS** |
| Full repo `pytest -q` | **NOT_RUN** (bounded session; do not claim full-suite cert) |

## Live providers

ENVIRONMENT_BLOCKED — no Ollama install / no paid credentials / no cloud enablement.
