# M21.4 — Release Gate Integration

## Integration point

`saathi/ops/release_gate.py` → `release_check()`

After storage/config/db/backup/secret/git gates, the canonical release path now runs:

1. `saathi.inference.release_check.run_release_check()`  
2. `saathi.inference.runtime_gate.evaluate_runtime_gate(...)` (static + live detect)

## Command

```bash
# Inference architecture only
python -m saathi.inference.release_check
python -m saathi.inference.release_check --explain

# Canonical ops release gate (includes inference)
python -c "from saathi.ops.release_gate import release_check; print(release_check(run_backup=False))"
```

## Failure behavior

* Inference release check not ok → exit `EXIT_PROVIDER` (8), blocks release  
* Runtime gate not ok → exit `EXIT_PROVIDER` (8), blocks release  
* Report includes `gates.inference_release_check` and `gates.m21_4_runtime_gate`  
* `production_certified` always reported false from these gates in M21.4  

## Rules (stable IDs from M21.3 release_check)

Includes (non-exhaustive): `unknown_inference_path`, `direct_provider_bypass`, `new_llm_generate_call_site`, `direct_provider_url`, `direct_sdk_constructor`, `trading_caller_registration`, `exchange_import_in_inference`, `fake_provider_production`, `production_certified_true`, `manifest_*`, `chat_engine_missing_adapter`.

## Properties

* No network for static scan  
* No secret access  
* No raw prompt/output access  
* Deterministic JSON  
* File/line/symbol/detail on findings  
