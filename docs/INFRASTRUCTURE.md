# SaathiAI Infrastructure Layer

The provider-agnostic substrate every department sits on. Departments call
abstractions; they never know which model, browser, connector, or speech engine
serves them.

```
Application    Executive · Business OS · Finance · AI Studio · Travel · Learning · Knowledge
    │
Capabilities   Research · Discovery · Execution · Content Factory · Learning Runtime
    │
Infrastructure Model Router · Browser Service · Browser Sessions · Connector Registry
    │           · Conversation Engine · Diagnostics
Drivers        anthropic · openai · openrouter · gemini · ollama · playwright · camofox
    │           · telegram · github · youtube · n8n · filesystem · whisper · kokoro
External       LLM APIs · browsers · Telegram · GitHub · YouTube · n8n · filesystem
```

**Dependency rule:** Application → Capabilities → Infrastructure → Drivers → SDKs.
Never the reverse. Infrastructure must never import a department module (the
Conversation Engine's reasoning brain is *registered* by the app via
`register_default_brain`, not imported).

## Model Router — `infrastructure.model_router`
Capability labels (`screening/standard/reasoning/multimodal/fast/long/private`) →
ranked provider chain → execute with fallback. `generate(label, prompt)`.
Providers: Claude, GPT-4o, DeepSeek, GLM, Qwen (via OpenRouter), Groq, Gemini, Ollama.
Add a provider → **§ How to add a provider**.

## Browser Service — `infrastructure.browser`
`open/extract/search/screenshot/pdf/snapshot/monitor/download` over an escalation
chain **HTTP → Playwright → Camofox** (cheapest capable first; escalate on
bot-wall/JS-wall). Named sessions (`session=`) persist cookies + login.

## Connector Registry — `infrastructure.connectors`
External services as uniform drivers. `registry.execute(capability=…, **payload)`
or `registry.get(id)`. Ranked `best(capability)` (health→reliability→cost→latency).
Drivers: Telegram, GitHub, n8n, Browser, YouTube, Filesystem. Manifest-declared
capabilities. Add one → **`connectors/HOW_TO_ADD_A_CONNECTOR.md`**.

## Conversation Engine — `infrastructure.conversation`
One brain for every channel. `engine.handle(session, message|audio, speak=)`:
`audio→STT → command? → Command Router, else Executive Intelligence → (speak?→TTS)`.
Adapters: Keyboard, API, Voice, Telegram. Voice = `listen/speak/interrupt/stop`
over `speech/` drivers. Add speech → **§ How to add speech**.

## Diagnostics
`connectors.diagnostics.snapshot()` (Router + Browser + Connectors) and
`conversation.diagnostics.snapshot()` (Voice/STT/TTS/WakeWord/Sessions), 🟢🟡🔴.

---

## How to add a provider (Model Router) — ~15 min
1. Add a `ProviderSpec` to `DEFAULT_PROVIDERS` in `saathi/model_router.py`.
2. Add a caller fn + `env_availability` branch + `DEFAULT_CALLERS` entry in `saathi/llm.py`.
3. No department changes. Test: provider-parity in `tests/test_model_router_providers.py`.

## How to add a connector — ~20 min
See `saathi/infrastructure/connectors/HOW_TO_ADD_A_CONNECTOR.md` (driver + manifest;
register in `drivers/__init__.py` + `_DEFAULT_DRIVER_CLASSES`).

## How to add speech (STT/TTS) — ~15 min
1. Implement `SttDriver`/`TtsDriver` in `conversation/speech/<engine>.py` with a
   guarded `available()`.
2. Slot it into `best_stt()`/`best_tts()` in `speech/__init__.py`.
3. No adapter/engine changes.

## How to debug
- **Which providers/tiers/connectors are live?** `connectors.diagnostics.snapshot()`.
- **Why did a call fail over?** Event Fabric: `connector.*`, `conversation.*`, `voice.*`.
- **A connector is red?** `connector.diagnostics()` → `{healthy, latency_ms, quota_remaining,
  authenticated, last_success, last_error}`.
- **Migration policy** (old top-level modules vs `infrastructure/`): `infrastructure/README.md`.

## Known gaps (M5.1 Integration Sprint findings)
- Model Router + Browser Service do not yet emit Event-Fabric events (`model.*`,
  `browser.*`) — only Opik tracing / return values.
- Event→Episode bridge is partial: `conversation.*`/`connector.*` events publish,
  but only the Telegram command path records Episodes today.
- `tools/prose.py`, `tools/auto_dev.py`, `vision.py` still import LLM SDKs directly
  (Agent-Runtime-adjacent; not yet routed through the Model Router).
