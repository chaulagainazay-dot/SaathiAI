# Infrastructure Layer

The architectural home for SaathiAI's platform services:

- **Model Router** — provider-agnostic `generate()` over Claude/GPT/DeepSeek/GLM/Qwen/Groq/Gemini/Ollama
- **Browser Service** — `open/extract/search/screenshot/pdf/monitor` over HTTP → Playwright → Camofox tiers
- **Connector Registry** *(Phase 1.3)* — external services (Telegram, YouTube, GitHub, …) behind one `execute()`
- **Voice Engine** *(Phase 1.4)* — `listen/transcribe/speak/interrupt`
- **Diagnostics** — health of every provider, browser, connector, token, and latency

## The dependency rule

```
Executive → Research → Learning → Business OS → Infrastructure → External Providers
```

No department knows whether it is talking to Claude, OpenRouter, Playwright, Camofox,
Telegram, or GitHub. It imports only this layer.

## Migration is gradual (no big-bang refactor)

This package currently **re-exports** the existing top-level modules, so both paths
resolve to the same object:

```python
from saathi.model_router import router          # old — still works (~20 callers, live VM)
from saathi.infrastructure.model_router import router   # new — same object
```

- **Nothing was moved.** Wrappers here are `from saathi.<module> import *`.
- **New code imports `saathi.infrastructure.*`.** Existing files stay untouched.
- **Later (≈v0.6):** physically relocate implementations here; the old paths become the shims; eventually delete them.

This keeps M5.1 an *infrastructure* milestone, not a refactor milestone (Dev Rule #3: certify, then merge — don't mix in restructuring).
