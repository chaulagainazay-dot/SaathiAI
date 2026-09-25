# Upstream Inventory — TauricResearch/TradingAgents

## Identity

| Field | Value |
|---|---|
| Upstream | `https://github.com/TauricResearch/TradingAgents.git` |
| Branch | `main` |
| SHA evaluated | `a33fd4c0f134485a43553a2c23a63cb14adbd88f` (2026-07-18) |
| Latest tag | `v0.3.1` (`5a3d1b5`) |
| License | **Apache License 2.0** — permissive, patent grant, requires attribution and NOTICE of changes |
| Repository size | 8.8 MB (shallow clone, depth 50) |
| Python requirement | `>=3.10` (host default `python3` is 3.9.6 — evaluation used Homebrew `python3.12`) |
| Clone location | `~/dev-toolkits/TradingAgents` — **outside** the SaathiOS repository |
| Isolated venv | `~/dev-toolkits/TradingAgents/.venv-eval` — separate from `SaathiAI/.venv` |

Apache-2.0 is compatible with adopting ideas. Copying source files would require
retaining the licence header and NOTICE; this evaluation recommends adopting
*patterns*, not files, so the question does not arise.

## Source scale

| Area | Python files | Lines |
|---|---|---|
| `tradingagents/agents` | 27 | 2,396 |
| `tradingagents/dataflows` | 20 | 2,949 |
| `tradingagents/graph` | 9 | 1,179 |
| `tradingagents/llm_clients` | 12 | 1,141 |
| `cli` | — | 2,154 |
| `tests` | 56 files | 6,335 |
| **Total** | **137** | **16,663** |

Test-to-source ratio is roughly 1:1.6 — unusually good for a project of this kind,
and the single strongest quality signal in the repository.

## Subsystems

**Agents** (`tradingagents/agents/`)
- `analysts/` — `fundamentals_analyst`, `market_analyst`, `news_analyst`, `sentiment_analyst`, `social_media_analyst`
- `researchers/` — `bull_researcher`, `bear_researcher`
- `managers/` — `research_manager`, `portfolio_manager`
- `risk_mgmt/` — `aggressive_debator`, `conservative_debator`, `neutral_debator`
- `trader/trader.py`
- `schemas.py` — Pydantic structured-output contracts
- `utils/` — `memory.py` (decision log), `agent_states.py`, `structured.py`, `rating.py`, plus tool modules (`core_stock_tools`, `fundamental_data_tools`, `macro_data_tools`, `news_data_tools`, `technical_indicators_tools`, `prediction_markets_tools`, `market_data_validation_tools`)

**Graph** (`tradingagents/graph/`)
- `trading_graph.py` — orchestration entry point, `propagate()`
- `setup.py` — LangGraph node/edge wiring
- `conditional_logic.py` — routing and debate termination
- `analyst_execution.py` — analyst node execution plan
- `checkpointer.py` — SQLite checkpoint/resume
- `reflection.py` — post-outcome reflection
- `signal_processing.py` — deterministic rating extraction
- `propagation.py`

**Dataflows** (`tradingagents/dataflows/`)
- Alpha Vantage family (`alpha_vantage{,_common,_fundamentals,_indicator,_news,_stock}.py`)
- `y_finance.py`, `yfinance_news.py`, `stockstats_utils.py`
- `fred.py` (macro), `reddit.py`, `stocktwits.py`, `polymarket.py` (prediction markets)
- `interface.py` (vendor routing), `market_data_validator.py`, `symbol_utils.py`, `errors.py`, `config.py`, `utils.py`

**LLM clients** (`tradingagents/llm_clients/`)
- `factory.py`, `base_client.py`, `capabilities.py`, `model_catalog.py`, `validators.py`, `api_key_env.py`
- Concrete: `openai_client`, `anthropic_client`, `google_client`, `azure_client`, `bedrock_client`
- OpenAI-compatible `base_url` override reaches Ollama, DeepSeek, Qwen, GLM, MiniMax, Groq, NVIDIA, xAI

**CLI** — `cli/` (2,154 lines), `questionary` + `rich` interactive runner.

**Not present despite being advertised or declared:** no backtesting harness, no
order management, no broker adapter, no portfolio accounting, no ledger, no
reconciliation, no approval workflow, no RBAC, no audit trail. TradingAgents ends
at a rating string.

## Declared dependencies vs actual use

`backtrader>=1.9.78.123` and `redis>=6.2.0` are declared in `pyproject.toml` and
**imported nowhere in the source tree** (verified by grep across all `.py`).
They are phantom dependencies. Any claim that TradingAgents "includes
Backtrader backtesting" is not supported by this commit.
