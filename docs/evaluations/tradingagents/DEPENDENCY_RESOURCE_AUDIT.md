# Dependency and Resource Audit

Measured, not estimated: full install of `TradingAgents==a33fd4c` plus test extras
into an isolated Python 3.12 venv at `~/dev-toolkits/TradingAgents/.venv-eval`.

## Measured footprint

| Metric | Value |
|---|---|
| Installed size | **385 MB** |
| Packages pulled in | **115** (declared direct: 22) |
| Largest | pandas 70 MB, numpy 34 MB, langchain_community 22 MB, lxml 20 MB, openai 19 MB, sqlalchemy 18 MB, google 16 MB, anthropic 15 MB, langchain_classic 13 MB, cryptography 13 MB |
| Test suite runtime | 131.9 s |

Nothing was installed into SaathiOS's environment. `SaathiAI/.venv` untouched.

## Classification

| Dependency | Class | Note |
|---|---|---|
| `langgraph`, `langgraph-checkpoint-sqlite` | **AVOID** | Orchestration duplicate; see `GRAPH_CHECKPOINT_ANALYSIS.md` |
| `langchain-core`, `langchain-experimental` | **AVOID** | Pulls `langchain_community` (22 MB) + `langchain_classic` (13 MB) + `sqlalchemy` (18 MB) transitively |
| `langchain-openai`, `langchain-anthropic`, `langchain-google-genai` | **ALREADY_HAVE_EQUIVALENT** | `saathi/inference/adapters/` covers these |
| `backtrader` | **AVOID — phantom** | Declared, **imported nowhere**. Verified by grep across the tree. |
| `redis` | **AVOID — phantom** | Declared, **imported nowhere** in `tradingagents/` or `cli/` |
| `pandas`, `numpy` | **ALREADY_HAVE_EQUIVALENT** | Present in SaathiOS |
| `yfinance` | **OPTIONAL / SECURITY_REVIEW_REQUIRED** | Unofficial scraper of a private endpoint; breaks without notice; ToS exposure. SaathiOS has `market_data/licensing.py` for a reason |
| `stockstats` | **OPTIONAL** | Indicator maths SaathiOS can compute itself |
| `parsel`, `lxml` | **HEAVY / SECURITY_REVIEW_REQUIRED** | 20 MB; HTML parsing of untrusted content; XML parser CVE surface |
| `pytz` | **ALREADY_HAVE_EQUIVALENT** | `zoneinfo` is stdlib on 3.12 |
| `questionary`, `rich`, `typer`, `tqdm` | **NEEDED_IF_ADOPTED (CLI only)** | Not needed for library adoption |
| `python-dotenv` | **AVOID** | SaathiOS has its own config/secret path |
| `requests` | **ALREADY_HAVE_EQUIVALENT** | |
| `pydantic` (transitive) | **ALREADY_HAVE_EQUIVALENT** | SaathiOS is a FastAPI codebase |
| `setuptools>=80.9.0` runtime pin | **AVOID** | Runtime dependency on setuptools is a smell |

**Net: zero dependencies recommended for SaathiOS.** Every adoption in this
evaluation is a pattern or a schema, implementable with pydantic and stdlib.

## 8 GB host assessment

| Factor | Finding |
|---|---|
| Disk | 385 MB per environment. Host had ~15 GB free; acceptable to evaluate, wasteful to keep |
| Import-time RAM | pandas + numpy + langchain stack is roughly 250–400 MB resident before any model call |
| Concurrency | Analysts run **sequentially** in the graph, so no parallel model pressure — but also no parallel speedup |
| Local models | Nothing in TradingAgents is local. All compute is remote by default |

## LLM call volume per single ticker-day run

Derived from `conditional_logic.py` and `setup.py` with default config
(`max_debate_rounds=1`, `max_risk_discuss_rounds=1`):

| Stage | Calls |
|---|---|
| 4 analysts × (1 reasoning + 1–3 tool rounds) | 8–16 |
| Bull ⇄ Bear until `count >= 2` | 2 |
| Research Manager | 1 |
| Trader | 1 |
| Risk debators until `count >= 3` | 3 |
| Portfolio Manager | 1 |
| Reflection (deferred, later) | 1 |
| **Total** | **~17–25 calls per ticker-day** |

Context grows monotonically: all four full prose reports are re-injected into
bull, bear, research manager, trader, all three risk debators, and the portfolio
manager. The `Msg Clear` nodes trim the *tool* message history, not the reports.
Realistically 15k–40k input tokens on the later nodes.

**Implication for SaathiOS:** a naive port is ~20 calls and possibly >200k input
tokens per instrument per day. Across a watchlist that is the dominant cost of the
whole system. Any SaathiOS adoption must (a) emit structured evidence rather than
re-injected prose, and (b) cost-gate through `saathi/inference/cost_policy.py` and
`research_orchestrator/budget.py`, both of which already exist.
