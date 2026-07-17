# M21.3 Release Check

## Command

```bash
python -m saathi.inference.release_check
python -m saathi.inference.release_check --json
python -m saathi.inference.release_check --explain
python -m saathi.m20_console residual-inference
```

Exit **0** pass, **2** fail. Offline, deterministic, no network, no secrets.

## Rules (blocking)

| Rule ID | Intent |
|---------|--------|
| unknown_inference_path | residual UNKNOWN = 0 |
| direct_provider_bypass | residual DIRECT_PROVIDER_BYPASS = 0 |
| new_llm_generate_call_site | frozen allowlist |
| direct_provider_url | outside allowlist |
| direct_sdk_constructor | OpenAI/Anthropic outside allowlist |
| duplicate_request_model | only request.py |
| duplicate_governance_type | no second circuit/cost classes outside inference |
| raw_prompt_or_output_logging | log_prompt/output=True |
| transitional_unknown_enabled | unknown must be disabled |
| trading_caller_registration | no enabled trading callers |
| exchange_import_in_inference | no ccxt/binance/… |
| fake_provider_production | fake remains TEST |
| production_certified_true | must stay false this milestone |
| chat_engine_missing_adapter | chat must use adapter |
| llm_helper_direct_provider | no URLs in _llm_helper |
| legacy_without_expiry | exceptions need expiry |
| manifest_exception_no_expiry | manifest exact |

## Integration

* CLI: `saathi.inference.release_check`
* Console: `python -m saathi.m20_console residual-inference`
* Tests: `tests/test_m21_3_residual_path_migration.py`

## Failure format

JSON findings: `rule_id`, `path`, `line`, `symbol`, `detail`, `severity`.
