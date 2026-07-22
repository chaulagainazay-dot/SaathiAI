# M23 — Operations

## Flags / posture

| Item | Value |
|------|-------|
| governed_chat_default | true |
| legacy_chat_execution | unavailable (False) |
| allow_cloud_fallback | false (unchanged) |
| production_certified | false |
| chat_engine caller | PILOT, tools_allowed=false, max_retries=0 |

## Disable procedure

```bash
# Global inference kill (blocks chat preflight before provider)
export SAATHI_INFERENCE_KILL_ALL=1

# Or stop serving chat API routes at reverse-proxy / process level
# Chat has no independent production enable flag beyond inference kills.
```

## Release check

```bash
.venv/bin/python -m saathi.inference.release_check
.venv/bin/python -m saathi.inference.release_check --json
```

## Runtime gate

```bash
.venv/bin/python -m saathi.inference.runtime_gate
.venv/bin/python -m saathi.inference.runtime_gate --json
```

M23 evidence checks include: `chat_governed_default`, `legacy_chat_paths`,
`chat_residual_exception_count`, `chat_privacy_check`, `chat_streaming_check`,
`chat_tool_governance`.

## Focused tests

```bash
.venv/bin/python -m pytest tests/test_m23_governed_chat_default.py -q
```

## Limitations remaining

* Circuit breaker process-local (M24)
* Daily cost process-local (M24)
* Live Ollama ENVIRONMENT_BLOCKED
* Multi-process budget consistency not in M23
