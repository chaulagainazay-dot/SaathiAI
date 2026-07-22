# M21.4 — Operations

## Disable inference (existing M21.0 procedure)

```bash
export SAATHI_INFERENCE_KILL_ALL=1
unset SAATHI_INFERENCE_ENABLED SAATHI_INFERENCE_GATEWAY_ENABLED SAATHI_ALLOW_CLOUD_FALLBACK
# Optional per-provider:
export SAATHI_PROVIDER_KILL_OLLAMA=1
```

Print disable commands:

```bash
python -m saathi.inference.prod_config disable
python -m saathi.m20_console disable
```

## Readiness

```bash
python -m saathi.inference.runtime_gate --explain
python -m saathi.m20_console runtime-readiness
python -m saathi.inference.release_check --explain
python -m saathi.inference.prod_config validate
```

## Critical checks (subset)

```bash
python -m saathi.repair critical   # if CLI available
# or pytest targets from critical_checks.json m21.4.*
.venv/bin/python -m pytest tests/test_m21_4_runtime_consolidation.py -q
```

## Production certification

Do **not** set `production_certified=true` without:

* Full suite PASS (or formally approved equivalent)  
* Secret scan PASS  
* Critical checks PASS  
* Live production-intended provider LIVE_CERTIFIED  
* All mandatory runtime gate checks PASS  
* Operator approval  

M21.4 default: **false**.
