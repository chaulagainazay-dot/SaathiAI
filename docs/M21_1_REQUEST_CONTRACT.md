# M21.1 — Canonical Inference Request Contract

## Verdict form

```text
M21.1 COMPLETE WITH LIMITATIONS — REQUEST CONTRACT READY; LEGACY PATHS REMAIN
```

## Contract version

`m21.1.contract.v1` / request field `contract_version="m21.1"`

## Flow

```text
caller → compatibility adapter (optional)
      → InferenceRequest
      → validate_contract (caller policy + kill + bounds + privacy)
      → ModelRouter
      → governed engine (ollama)
      → privacy-safe result / evidence
```

## Modules

| Module | Role |
|--------|------|
| `saathi/inference/request.py` | Extended InferenceRequest |
| `saathi/inference/contract.py` | Validation, fingerprint, telemetry |
| `saathi/inference/caller_policy.py` | Caller registry |
| `saathi/inference/residual_paths.py` | Residual allowlist |
| `saathi/inference/bypass_guard.py` | AST static guards |
| `saathi/inference/gateway_path.py` | Enforces contract |
| `saathi/inference/compat.py` | Builds contract-compliant requests |

## Safe defaults

local_only=true, cloud_allowed=false, tools/streaming false, max_retries=0, log_prompt/output false, retention metadata_only, cost ceiling 0.

## Disable

```bash
export SAATHI_INFERENCE_KILL_ALL=1
export SAATHI_PROVIDER_KILL_OLLAMA=1
unset SAATHI_INFERENCE_ENABLED SAATHI_INFERENCE_GATEWAY_ENABLED SAATHI_ALLOW_CLOUD_FALLBACK
```

## CLI

```bash
python -m saathi.inference.prod_config callers
python -m saathi.inference.prod_config residual
python -m saathi.inference.bypass_guard
```

## Production certification

Remains **false**. Not M21 complete. Not M21.2.
