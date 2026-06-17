# Integrations

## LLM Providers
| Provider | Use | Key env var |
|----------|-----|-------------|
| Groq (llama) | Primary LLM — fast, free tier | `GROQ_API_KEY` |
| Google Gemini | Fallback | `GOOGLE_API_KEY` |
| Anthropic Claude | Heavy tasks | `ANTHROPIC_API_KEY` |

## Image Generation
- **Pollinations.ai** — FREE, no API key. Flux model.
  - Endpoint: `https://image.pollinations.ai/prompt/{encoded}?width=...&model=flux&nologo=true`
  - Mr. Yeti styles built in at server.py `_STYLE_PREFIX`
  - Baadar endpoint: `POST /api/v1/generate_image`
- **Higgsfield AI** — Paid. SoulIds for character consistency. Node.js SDK.
  - Not yet wired. Would need `HF_CREDENTIALS=KEY_ID:KEY_SECRET`

## Voice / TTS
- macOS `say` command — free, built-in (current)
- gTTS — Google TTS (current fallback)
- Cartesia Sonic 3.5 — pending (needs `CARTESIA_API_KEY`)

## Social / Publishing
- Meta Business Suite — manual posting (Ajay does this)
- Facebook/Instagram — no API auto-post yet (OAuth needed)
- YouTube — no auto-upload yet (Google OAuth needed)
- Telegram bot — @AjayGmailbot, two-way (ACTIVE)
  - Chat ID: 919874672, Token: `TELEGRAM_BOT_TOKEN`

## Internet Reach Tools (`saathi/tools/internet_reach.py`)
All non-privileged, no voice gate:
- `web_search` — DuckDuckGo instant answers
- `read_webpage` — Jina Reader (r.jina.ai)
- `youtube_info`, `youtube_subtitles` — yt-dlp
- `github_repo` — gh CLI + Jina README
- `rss_feed` — feedparser
- `bilibili_search` — Bilibili API

## Database
- SQLite at `data/baadar.db` — conversation history, feedback, improvements
- HCGMS: Supabase (external, separate project)
