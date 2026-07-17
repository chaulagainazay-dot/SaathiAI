# M21.2 — Operations

## CLI

```bash
python -m saathi.inference.provider_governance providers
python -m saathi.inference.provider_governance availability
python -m saathi.inference.provider_governance costs
python -m saathi.inference.provider_governance failures
python -m saathi.inference.provider_governance circuits
python -m saathi.inference.provider_governance decide [caller_id]
python -m saathi.inference.provider_governance validate
python -m saathi.inference.provider_governance reset-circuit <provider_id> --confirm
python -m saathi.inference.provider_governance disable
python -m saathi.m20_console provider-governance
```

## Disable (no code change)

```bash
export SAATHI_INFERENCE_KILL_ALL=1
export SAATHI_PROVIDER_KILL_OLLAMA=1
unset SAATHI_INFERENCE_ENABLED
unset SAATHI_INFERENCE_GATEWAY_ENABLED
unset SAATHI_ALLOW_CLOUD_FALLBACK
```

## Confirm cloud off

```bash
python -m saathi.inference.provider_governance availability | grep -i cloud
# expect cloud_fallback_default false; cloud providers disabled
```

## Never exposed

API keys, raw env secrets, raw prompts/outputs, private provider payloads.
