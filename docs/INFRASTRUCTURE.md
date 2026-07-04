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

## Sanctioned direct-SDK exceptions (intentional, not violations)
The "no provider imports outside infrastructure" rule has a few deliberate carve-outs:
- **`saathi/agent.py`** — the Agent Runtime (tool-use, streaming, multi-turn). A
  separate abstraction from the capability router (see `infrastructure/README.md`).
- **`tools/auto_dev.py`** — Agent Runtime (Claude `tool_use` build/review loop).
- **`vision.py`** — multimodal (image input); the router's text `generate()` can't carry it yet.
- **`tools/speaking_eval.py`** — speech/audio (Whisper); belongs to the Conversation
  speech layer, to be routed there in a later phase.
- **`tools/writing_eval.py`** — IELTS band scorer pinned to Gemini for scoring
  accuracy; a product-tuned path. Revisit after the exam.

`tools/prose.py` was migrated to the Model Router (plain completion, low stakes).

## Closed in the M5.1 Integration Sprint
- Model Router emits `model.selected / model.fallback / model.failed`.
- Browser Service emits `browser.started / blocked / escalated / finished`.
- Event→Episode bridge (`saathi/episode_bridge.py`): `conversation.completed`,
  `connector.executed`, `browser.finished` → Episodes (wired at server startup).
- Reverse dependency removed: Conversation Engine no longer imports `saathi.agent`
  (brain registered via `register_default_brain` at startup).

## Human Browser Driver (`infrastructure.human_browser`)
Third execution mode after API and headless Browser — publish through your real,
logged-in Chrome. **The VM never drives your browser or holds a cookie:** it signs
a `HumanJob` (HMAC-SHA256, `expires_at`, one-time `nonce`) and drops it on a queue;
the **Mac Agent** on your trusted machine verifies and drives your Chrome profiles.

```
VM: HumanBrowserProxy.execute("publish_video", profile="ajay/youtube", …)  → signs + enqueues
    ↳ /api/v1/human/{claim,complete}  (authenticated relay; never runs a browser)
Mac: MacAgent(HttpQueueClient, ChromeBackend, secret).run_forever()  → verifies + drives Chrome
```

- **Profiles:** `profiles/ajay/{youtube,facebook,instagram,…}` — persistent Chrome
  contexts, log in once, reused forever (`ProfileStore`). Live only on the Mac.
- **Escalation tier:** `HumanTier` slots into the Browser Service as `HTTP → Playwright
  → Camofox → Human` (opt-in; needs a queue + `HUMAN_BROWSER_SECRET`).
- **Mode selection:** register a human-backed connector at lower reliability than the
  API/Browser connectors for the same capability — the registry's `best()` picks API
  first, Browser next, Human last. Departments stay provider-agnostic.
- **Run the agent (Mac only):** `python -m saathi.infrastructure.human_browser.run_agent`
  with `SAATHI_BASE_URL`, `SAATHI_TOKEN`, `HUMAN_BROWSER_SECRET` set.

Security model: a compromised VM can only enqueue jobs signed with the shared secret
— it can never drive the browser or read your sessions. Rotate `HUMAN_BROWSER_SECRET`
to revoke.
