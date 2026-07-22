# M21.4 — Production-Configuration Gate

## Command

```bash
python -m saathi.inference.runtime_gate
python -m saathi.inference.runtime_gate --explain
python -m saathi.m20_console runtime-readiness
```

## Inputs

* `InferenceSettings` via `validate_production_config` (M21.0)
* Static `run_release_check` (M21.3)
* Residual exception manifest validation
* Residual path unknown/bypass counts
* Fake/test isolation under production posture
* Cloud fallback posture
* Trading Guardian isolation
* Kill-switch authority inventory
* Cost/privacy descriptor metadata
* Live provider probe (read-only; no install)
* Injected suite/scan evidence (`full_suite_status`, `secret_scan_status`, `critical_check_status`)

## States

```text
PASS | FAIL | BLOCKED | NOT_APPLICABLE | NOT_TESTED | ENVIRONMENT_BLOCKED
```

`NOT_TESTED` and `ENVIRONMENT_BLOCKED` **never** collapse to `PASS`.

## Blocking rules (gate `ok`)

* Production config blocking findings → FAIL  
* Release check blocking findings → FAIL  
* Residual manifest structural failure → FAIL  
* Unknown path / direct bypass nonzero → FAIL  
* Fake provider enabled in production posture → FAIL  
* Cloud fallback enabled in production posture → FAIL/BLOCKED  
* Trading inference caller or exchange import in inference → FAIL  
* Secret scan injected FAIL → FAIL  
* Critical check injected FAIL → FAIL  

Non-blocking for pilot `ok` but **block certification**:

* Live provider ENVIRONMENT_BLOCKED / NOT_TESTED  
* Full suite NOT_TESTED  
* Secret scan NOT_TESTED  
* Critical checks NOT_TESTED  

## Production certification

`production_certified` remains **false** unless every mandatory check is genuinely `PASS`, including live provider certification.  
Manual override cannot force true when blockers exist.  
M21.4 evaluate path hard-defaults `production_certified=false`.

## Result (typical M21.4 environment)

```text
ok=True
production_certified=false
overall_state=ENVIRONMENT_BLOCKED  # live Ollama absent
live_provider.blocker=ollama_binary_absent
```
