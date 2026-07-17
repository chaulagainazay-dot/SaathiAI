# M22 Migration Notes

## Before → After

### llm.generate

| Before | After |
|--------|-------|
| HTTP callers embedded in `saathi/llm.py` | Callers in `adapters/http_providers.py` |
| Direct `os.getenv` API keys | Credential reads only in adapters |
| `CloudCallerEngine` imported `llm.DEFAULT_CALLERS` | Imports `http_providers` |
| Classification EXPLICIT_LEGACY_EXCEPTION | COMPATIBILITY_FACADE |

### Agent

| Before | After |
|--------|-------|
| `OpenAI` / `Anthropic` constructed in `agent.py` | `build_agent_session()` in `agent_provider` |
| Groq → Gemini cloud hop in agent | Removed; local shimmy/ollama recovery only |
| path_id `agent_sdk_clients` | `agent_runtime_governed` |

### Research

| Before | After |
|--------|-------|
| `httpx` + generativelanguage URL in research.py | `grounded_generate` adapter |
| Direct `config.GOOGLE_API_KEY` | Key resolved inside adapter |

## Compatibility

* `generate(label, prompt, ...)` signature preserved
* Injected `router` / `callers` for tests preserved
* `research()` / `deep_plan()` return shapes preserved (+ privacy field)
* Agent `complete` / `respond` public methods preserved

## Residual after M22

* Chat engine COMPATIBILITY_WRAPPED → M23
* Cloud / openai_compat engines → M24
* Circuit + daily cost process-local
* Live Ollama ENVIRONMENT_BLOCKED without operator install
