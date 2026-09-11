# Security Review — TradingAgents `a33fd4c`

## Summary

Clean for a research codebase. No dangerous execution primitives at all. The one
serious, structural exposure is **prompt injection via ingested internet text**,
which is unmitigated by design.

## Static findings

| Check | Result |
|---|---|
| `subprocess` / `os.system` | **none** in `tradingagents/` or `cli/` |
| `eval(` / `exec(` | **none** |
| `pickle.load` / unsafe `yaml.load` | **none** |
| Hardcoded credentials | **none**; only `.env.example` / `.env.enterprise.example` |
| Secret handling | `PROVIDER_API_KEY_ENV` maps provider → env-var **name**; values read from environment; `"ollama": None` for keyless local |
| Path traversal | **Defended.** `safe_ticker_component()` allowlists `[A-Za-z0-9._\-^=+]`, caps length at 32, and explicitly rejects dot-only values (`.`, `..`, `...`). Applied before checkpoint DB paths and result paths |
| SQLite | parameterised (`DELETE FROM {table} WHERE thread_id = ?`); table name is internal, not user input |
| Deserialisation | JSON only |
| Redis | declared but never imported — no attack surface |
| Outbound endpoints | `alphavantage.co`, `api.stlouisfed.org` (FRED), `api.stocktwits.com`, `reddit.com`, `gamma-api.polymarket.com`, plus provider SDK endpoints. All HTTPS, all expected |
| URL validation | endpoints are constants, not user-supplied — good |
| Dependency risk | `lxml`/`parsel` (XML/HTML parsing of untrusted content), `yfinance` (unofficial scraper) — see `DEPENDENCY_RESOURCE_AUDIT.md` |
| Telemetry / phone-home | none found |

The `safe_ticker_component` docstring explicitly names LLM tool calls influenced by
prompt injection as the threat model. That is unusually thoughtful, and the
dot-only rejection shows the author actually tested the bypass.

## Prompt injection — the material finding

TradingAgents ingests attacker-controllable text from **Reddit, StockTwits, and
news headlines**, formats it, and inserts it into analyst prompts. `reddit.py`
applies `_strip_html()` + `html.unescape()`, which removes markup — it does **not**
neutralise instructions. `stocktwits.py` produces, in its own words, a
"formatted plaintext block ready for prompt injection" (meaning insertion).

There is no delimiting, no untrusted-content marking, no instruction-stripping, and
no output constraint tying claims back to evidence.

### Injection paths, ranked

1. **Reddit / StockTwits post → Sentiment Analyst prompt.** Anyone can post. A
   crafted post reaches the model as undifferentiated context.
2. **News headline / article body → News Analyst prompt.** Lower volume, higher
   perceived trust — worse if it lands.
3. **Injected text → analyst report → bull/bear debate → Research Manager →
   Trader → Portfolio Manager.** The prose report is carried verbatim through every
   downstream prompt, so one injection influences the entire chain.
4. **Injected text → Portfolio Manager decision → `TradingMemoryLog` →
   `get_past_context()` → future runs.** This is the serious one: the decision log
   stores prose **verbatim** and re-injects it into later prompts. An injection can
   become **persistent** across runs and tickers (cross-ticker lessons are shared).
5. **LLM tool-call arguments → filesystem paths.** *Mitigated* by
   `safe_ticker_component`.

### Consequence bound

In TradingAgents itself, a successful injection can only corrupt a *rating string* —
there is no execution path, no broker, no funds. The blast radius is bad research,
not a bad trade.

**In SaathiOS the bound is different and must stay that way.** If an LLM research
layer is ever adopted, injected content must be unable to move a position. That
property is guaranteed only by the deterministic plane, not by sanitisation.

## Requirements for any SaathiOS adoption

1. **Classify ingested external text as `UNTRUSTED_DATA` at the type level.** Not a
   convention — a distinct type that cannot be concatenated into a system prompt.
2. **Delimit and label** untrusted blocks in prompts, with an explicit instruction
   that content inside is data to analyse and never instructions to follow.
3. **No verbatim carry-forward.** Analysts emit *structured evidence records*
   (claim, value, source, timestamp, confidence). Downstream stages consume the
   structure, not the prose. This alone removes injection paths 3 and 4.
4. **No untrusted text in persistent memory.** Journal lessons are structured
   fields, never free text (see `MEMORY_REFLECTION_ANALYSIS.md`).
5. **Keep the path-safety pattern.** Adopt `safe_ticker_component`'s allowlist +
   dot-only rejection for any SaathiOS identifier that reaches a filesystem path.
6. **Deterministic-plane invariance test.** The deterministic chain must produce
   identical output for adversarial and benign research input. Make it a
   certification gate.
7. **Defer Reddit/StockTwits ingestion entirely** until 1–4 exist. Highest injection
   volume, lowest signal.

## Classification

| Item | Verdict |
|---|---|
| Execution primitives (shell/eval/pickle) | **SAFE** |
| Secret handling | **SAFE** |
| Path traversal defence | **SAFE — adopt the pattern** |
| SQLite usage | **SAFE** |
| Network endpoints | **SAFE_WITH_LIMITATION** — fixed, HTTPS, but no rate limiting |
| `lxml` / `parsel` / `yfinance` | **SECURITY_REVIEW_REQUIRED** if ever adopted |
| Untrusted content → prompt | **REQUIRES_CONFIGURATION** — must be redesigned before any SaathiOS use |
| Untrusted content → persistent memory → future prompts | **BLOCK** — do not replicate |
