# Test Suite Report

## Execution — real, offline, no API keys

```
env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u GOOGLE_API_KEY -u XAI_API_KEY \
  .venv-eval/bin/python -m pytest tests -q
```

```
576 passed, 2 skipped, 18 warnings, 69 subtests passed in 131.88s
```

Skips (both correct, neither hides a failure):
- `test_bedrock_provider.py` — `langchain_aws` not installed
- `test_deepseek_reasoning.py` — `DEEPSEEK_API_KEY` not set; the suite refuses to
  make a live call rather than silently passing

No paid API key was supplied. No live trading, no order, no broker call. The suite
is genuinely hermetic — that is itself a quality signal.

Environment: isolated venv, Python 3.12.13, `~/dev-toolkits/TradingAgents/.venv-eval`.
SaathiOS's `.venv` was not touched.

## Coverage by concern

| Concern | Tests | Assessment |
|---|---|---|
| **Look-ahead / date boundaries** | `test_news_lookahead`, `test_date_boundaries`, `test_stockstats_date_column`, `test_yfinance_stale_ohlcv_guard`, `test_market_data_validator` | **Strong on price/news.** Asserts exclusive upper bound, timezone conversion vs truncation, undated-excluded-in-backtest. **No test covers fundamentals filing lag** — the defect in `LOOKAHEAD_AUDIT.md` is untested and therefore undetected |
| **Structured outputs** | `test_structured_agents`, `test_structured_agent_prompts`, `test_capabilities`, `test_model_validation` | **Strong** — covers schema binding, prompt shape, per-model capability selection |
| **Providers** | `test_provider_registry`, `test_openai_compatible_provider`, `test_ollama_base_url`, `test_openai_responses_base_url`, `test_openrouter_model_select`, `test_minimax`, `test_anthropic_effort`, `test_google_api_key`, `test_google_thinking_level`, `test_openai_reasoning_effort`, `test_temperature_config`, `test_llm_max_retries`, `test_api_key_env` | **Very strong** — 13 files; provider quirks are regression-tested, which is why the capability table is trustworthy |
| **Dataflow / vendor** | `test_vendor_routing`, `test_vendor_errors`, `test_alpha_vantage_hardening`, `test_fred`, `test_polymarket`, `test_reddit_fallback`, `test_stocktwits_resilience`, `test_no_data_handling`, `test_ohlcv_cache_freshness`, `test_dataflows_config` | **Strong** — fallback and empty-source paths covered |
| **Checkpoint recovery** | `test_checkpoint_resume` | **Adequate** — covers resume identity incl. the shape signature |
| **Decision memory** | `test_memory_log` | **Adequate** — store/parse/update/rotation. No test of recall-time leakage or lesson staleness |
| **Graph routing** | `test_analyst_execution`, `test_risk_router_path_map`, `test_market_toolnode`, `test_signal_processing` | **Adequate** — node/edge wiring and rating extraction |
| **Security / path traversal** | `test_safe_ticker_component`, `test_symbol_normalization_paths`, `test_ticker_symbol_handling`, `test_symbol_utils`, `test_instrument_identity` | **Strong** for path safety. **Zero tests for prompt injection** |
| **CLI / config** | `test_cli_config_precedence`, `test_cli_env_skip`, `test_cli_no_console`, `test_cli_symbol_handling`, `test_env_overrides`, `test_i18n_coverage` | **Strong** |
| **Backtesting** | none | **Absent — there is no backtesting to test** |
| **Failure handling** | `test_llm_max_retries`, `test_no_data_handling`, `test_vendor_errors` | Adequate |

## Gaps worth naming

1. **No fundamentals look-ahead test.** The most damaging leak in the codebase has
   no test guarding it. Both the fiscal-period filter and the entirely unfiltered
   `OVERVIEW` path would pass CI today.
2. **No prompt-injection test.** Untrusted text reaches prompts with no assertion
   about handling.
3. **No end-to-end graph test.** Nodes are tested; a full `propagate()` is not
   (understandably — it needs an LLM, but a fake client would make it possible).
4. **No memory-recall leakage test.** Nothing asserts that a recalled lesson
   post-dates nothing it shouldn't.
5. **No cost or token-budget test.** Nothing bounds calls per run.

## What SaathiOS should take from the test suite

| Pattern | Verdict |
|---|---|
| Hermetic suite — refuses live calls, skips loudly rather than passing silently | **ADAPT** |
| Boundary-condition date tests per data adapter (inclusive/exclusive, tz-aware, undated) | **ADAPT — high value** |
| Provider-quirk regression tests, one per known misbehaviour | **ADAPT — high value**; pairs with the `ModelCapabilities` borrow |
| Path-safety tests incl. dot-only and normalisation bypasses | **ADAPT** |
| Structured-output + fallback tests | **ADAPT** |
| Test-to-source ratio near 1:1.6 as a norm for a research layer | **ADAPT as a target** |

The test suite is the single most transferable artifact in the repository — more so
than any agent.
