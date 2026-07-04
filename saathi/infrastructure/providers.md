# Infrastructure Providers

What each service can route to. Providers are wrapped behind an abstraction;
departments never name them.

## Model Router (`infrastructure.model_router`)

| Provider | Backing | Labels | Cost | Quality |
|---|---|---|---|---|
| anthropic/claude | native Anthropic | standard, reasoning, multimodal, long | 6.0 | 1 |
| openai/gpt-4o | native OpenAI | standard, reasoning, multimodal, long | 5.0 | 1 |
| deepseek/deepseek-chat | OpenRouter | standard, reasoning, long | 0.3 | 1 |
| glm/glm-4.6 | OpenRouter | standard, reasoning, long | 0.5 | 2 |
| qwen/qwen-2.5-72b | OpenRouter | screening, standard, fast, long | 0.4 | 2 |
| groq/llama-3.3-70b | native Groq | screening, standard, fast | 0.0 | 2 |
| gemini/2.5-flash-lite | native Gemini | screening, standard, multimodal, long, fast | 0.5 | 2 |
| ollama/local | local | screening, standard, fast, **private** | 0.0 | 3 |

Keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY` (GLM/DeepSeek/Qwen),
`GROQ_API_KEY`, `GOOGLE_API_KEY`, `OLLAMA_HOST`.

## Browser Service (`infrastructure.browser`)

| Tier | Backing | Capabilities | Dependency |
|---|---|---|---|
| http | httpx | fetch, search | always available |
| playwright | Playwright | fetch, render_js, screenshot, pdf, dom | `pip install playwright` |
| camofox | Camoufox | fetch, render_js, screenshot, dom, **evade** | `pip install camoufox` |

## Connector Registry (`infrastructure.connectors`) — Phase 1.3

Planned: telegram, youtube, github, reddit, n8n, runway, flux, heygen, hyperframes,
tradingview, binance, supabase — each exposing `health/authenticate/execute/capabilities/rate_limits`.

## Voice Engine (`infrastructure.voice`) — Phase 1.4

Planned: whisper (STT), kokoro (TTS), openai (STT/TTS) behind `listen/transcribe/speak/interrupt`.
