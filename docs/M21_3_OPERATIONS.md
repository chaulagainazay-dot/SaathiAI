# M21.3 Operations

## Disable (no code edits)

```bash
export SAATHI_INFERENCE_KILL_ALL=1
export SAATHI_PROVIDER_KILL_OLLAMA=1
unset SAATHI_INFERENCE_ENABLED SAATHI_INFERENCE_GATEWAY_ENABLED SAATHI_ALLOW_CLOUD_FALLBACK
export SAATHI_LLM_GENERATE_DEPRECATION_WARN=0   # optional: silence deprecation in prod
```

## Operator visibility

```bash
python -m saathi.inference.residual_paths
python -m saathi.inference.release_check --explain
python -m saathi.m20_console residual-inference
python -m saathi.m20_console provider-governance
python -m saathi.m20_console status
```

## Production certification

Remains **false**. M21.3 does not enable live providers, cloud fallback, or deployment.
