# M21.0 Validation

## Commands

```bash
cd /Users/macbookpro/SaathiAI
python -m pytest tests/test_m21_0_production_config.py -q
python -m pytest tests/test_m20_7_console_consolidation.py -q
python -m saathi.inference.prod_config validate
python -m saathi.inference.prod_config inventory
python -m saathi.m20_console prod-config | head
```

## Expected

* M21.0 tests: all pass (`UNIT_TESTED`)
* Default `validate`: `ok: true`, `posture: pilot_safe`, `production_certified: false`
* Inventory includes `governed_local_gateway`, `legacy_llm_generate`, residual `chat_engine`
* Policy: cloud families `policy_disabled` by default; kill switches work
* M20.7 console tests still pass (flag catalog extended)

## Honesty

| Claim | Tier |
|-------|------|
| Config validation + kill switches | UNIT_TESTED |
| Path inventory completeness | SOURCE_INSPECTED (+ static suite) |
| Live Ollama generation | ENVIRONMENT_BLOCKED (unchanged) |
| Production certification | NOT claimed |
| Full suite green | NOT claimed unless run |

## Non-goals verified

* No TG engagement
* No second ModelRouter
* No model download
* No M21.1 caller migration
