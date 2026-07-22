# M22 Operations

## Disable inference (all)

```bash
export SAATHI_INFERENCE_KILL_ALL=1
```

## Disable one provider family

```bash
# See saathi.inference.provider_policy for env names
export SAATHI_PROVIDER_KILL_GEMINI=1
export SAATHI_PROVIDER_KILL_GROQ=1
```

## Release check

```bash
.venv/bin/python -m saathi.inference.release_check --explain
```

## Runtime readiness (production config gate)

```bash
.venv/bin/python -m saathi.inference.runtime_gate
# or
.venv/bin/python -m saathi.m20_console runtime-readiness
```

## Cloud fallback

Remains **disabled** by default (`allow_cloud_fallback=false`). Do not set `SAATHI_ALLOW_CLOUD_FALLBACK=1` without operator policy.

## Live providers

Ollama / cloud live certification is **not** part of M22. Do not install Ollama or add credentials for certification.
