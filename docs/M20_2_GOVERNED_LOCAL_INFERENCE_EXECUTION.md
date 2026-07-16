# M20.2 — Governed Local Inference Execution Path

**Status:** Pilot implemented (default-off)
**Date:** 2026-07-16
**Prior:** M20.1 `saathi/inference` runtime + catalogue
**Not claimed:** production-ready · global llm.generate migration · streaming · OpenJarvis process · Trading Guardian integration

---

## Execution path

```text
caller (explicit opt-in / ToolIntent)
  → SaathiExecutionSystem / ModelGateway
  → feature gates (SAATHI_INFERENCE_ENABLED + SAATHI_INFERENCE_GATEWAY_ENABLED)
  → InferenceRequest validation
  → hardware gate (M20.1 profile)
  → ModelRouter (authoritative) via route_with_governance
  → local-only filter
  → Ollama engine (allowlisted loopback host)
  → installed + hardware-suitable model (no pull)
  → StructuredInferenceResult + evidence events
```

OpenJarvis is **not** a runtime dependency. ModelRouter is **not** duplicated.

## Request contract

`saathi.inference.request.InferenceRequest`

Validated fields include prompt, max tokens, timeout, sensitivity, local_only,
streaming (rejected), tool use (rejected), force_model / force URL (rejected).

Built from ToolIntent via `request_from_toolintent_parameters`.

## ModelRouter ownership

`ModelRouter.route` / `route_with_governance` select `ProviderSpec` chain.
The inference layer:

* never substitutes a different provider
* may only pick a catalogue **model id** under the selected local provider
* fails closed if no installed, hardware-suitable model exists

## Configuration (defaults safe)

| Variable | Default |
|----------|---------|
| `SAATHI_INFERENCE_ENABLED` | false |
| `SAATHI_INFERENCE_GATEWAY_ENABLED` | false |
| `SAATHI_ALLOW_CLOUD_FALLBACK` | false |
| `SAATHI_OLLAMA_BASE_URL` / `OLLAMA_HOST` | `http://127.0.0.1:11434` |
| `SAATHI_OLLAMA_ALLOWED_HOSTS` | 127.0.0.1,localhost,::1 |
| `SAATHI_LOCAL_ENGINE_ALLOWLIST` | ollama |
| `SAATHI_INFERENCE_MAX_PROMPT_CHARS` | 16000 |
| `SAATHI_INFERENCE_MAX_OUTPUT_TOKENS` | 1024 |
| `SAATHI_INFERENCE_MIN_AVAILABLE_MEMORY_GB` | 1.5 |
| `SAATHI_INFERENCE_MAX_CONCURRENT` | 1 |

## Hardware policy

Uses M20.1 `HardwareProfile`. Enforces min available memory, skips models above recommended size or that fail memory fit (e.g. 8B on 8 GB class), concurrency=1, no download, no fabricated energy metrics.

## Fallback

Default: none. Cloud providers selected by router are denied for this pilot.
Only ModelRouter-approved **local** chain members are eligible.

## Evidence events

`inference.request_received`, `hardware_ok`, `router_decision`, `engine_health`,
`execution_started`, `execution_completed`, `failed`, `idempotent_hit`.
Prompt stored as fingerprint only.

## Compatibility

Existing `llm.generate` and chat-llm override paths remain default behaviour.
Chat may continue to override `_get_model_policy` → `chat-llm`.

## Disable

```bash
unset SAATHI_INFERENCE_ENABLED SAATHI_INFERENCE_GATEWAY_ENABLED
# or
export SAATHI_INFERENCE_ENABLED=0
export SAATHI_INFERENCE_GATEWAY_ENABLED=0
```

## Rollback

Revert M20.2 commit; or leave flags off (package idle). M20.1 remains available independently.

## Next slice (not this milestone)

M20.3 candidate: opt-in migration of selected callers from direct `llm.generate`
to governed path — still not global chat default, still no streaming.
