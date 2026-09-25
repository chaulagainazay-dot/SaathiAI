# Security and Authority Audit

All assertions below are enforced by
`tests/execution_integrity/test_security_authority.py` (19 tests), which
introspects source and class members rather than trusting documentation.

## Authority boundary

| Property | Enforcement | Test |
|---|---|---|
| ReconciliationAuthority holds no execution authority | class member introspection rejects `approve`, `authorize`, `authorise`, `submit`, `execute`, `place_order`, `cancel`, `send`, `trade`, `override`, `force` | `test_reconciliation_authority_exposes_no_execution_verbs` |
| Verdict object exposes no execution verb | same introspection on `ReconciliationVerdict` | `test_reconciliation_verdict_exposes_no_execution_verbs` |
| Authority cannot mutate the ledger | module never references `record_fill`, `post_accepted_fill`, `PortfolioLedgerService`, `record_deposit` | `test_reconciliation_authority_cannot_mutate_a_ledger` |
| Only `RECONCILED` permits execution | exhaustive iteration over `ExecutionReadiness` | `test_no_readiness_other_than_reconciled_permits_execution` |
| `UNKNOWN` blocks, even in permissive mode | explicit | `test_unknown_blocks_execution` |
| `MISMATCH` blocks, even in permissive mode | explicit | `test_mismatch_blocks_execution` |
| `DATA_INSUFFICIENT` blocks, even in permissive mode | explicit | `test_data_insufficient_blocks_execution` |
| No ambiguous outcome is ever retryable | explicit over the ambiguous set | `test_no_ambiguous_outcome_is_ever_safe_to_retry` |
| Unrecognised outcome fails closed | `""`, `"MAYBE"`, `"OK"`, `None`, `0`, `object()` | `test_unrecognised_outcome_fails_closed` |

## LLM exclusion

| Property | Test |
|---|---|
| The integrity module imports no LLM surface (`openai`, `anthropic`, `model_router`, `saathi.inference`, `langchain`, `llm`) | `test_execution_integrity_module_has_no_llm_dependency` |
| No LLM inference is importable from the paper trading execution path | `test_no_llm_inference_import_in_paper_trading_execution_path` |

The second test is the load-bearing one: it greps the entire
`saathi/platform/paper_trading/` tree for any import of `saathi.inference` or
`saathi.model_router`. If a future change makes an LLM reachable from the
execution path, the suite fails.

## TradingAgents exclusion

| Property | Test |
|---|---|
| No `tradingagents` or `TauricResearch` reference anywhere in the execution plane | `test_no_tradingagents_code_in_execution_plane` |
| No `langgraph` or `backtrader` import in the execution plane | `test_no_langgraph_or_backtrader_dependency_in_execution_plane` |

Scope searched: `saathi/platform/paper_trading/`, `saathi/execution/`,
`saathi/platform/fund_ledger/`, `saathi/platform/portfolio_construction/`.

## Paper-only guarantees

| Property | Test |
|---|---|
| Live / production / real-money / leverage / margin / short-selling configuration is refused | `test_paper_safety_rejects_live_configuration` |
| No real broker SDK present (alpaca, ib_insync, ibapi, ccxt, binance, kite, robinhood, tda, schwab, oanda) | `test_no_real_broker_sdk_in_execution_plane` |
| No withdrawal / transfer-out / payout function in the execution plane | `test_no_withdrawal_authority_in_execution_plane` |
| No network egress in the integrity module (`requests`, `httpx`, `urllib`, `socket`, `aiohttp`, `fetch(`) | `test_no_network_egress_in_execution_integrity_module` |

## Determinism

| Property | Test |
|---|---|
| Identical input yields byte-identical verdict | `test_authority_verdict_is_deterministic_for_identical_input` |
| No `random`, `uuid4`, or `secrets` in the integrity module | `test_no_randomness_in_integrity_module` |

## Pre-existing authority tests relied upon

`tests/test_m62_5_paper_broker.py` already proves, and continues to pass:
Trading Guardian veto **before** submission, server-owned approval verification
and atomic consumption, the ExecutionGateway/registered-tool mutation boundary,
tenant isolation, atomic rollback, restart persistence, and the absence of any
live/leverage/short/derivative/network capability.

## Secret scan

No credential, token, key, `.env`, or broker configuration was added by this
mission. Files added: one source module, three test modules, and documentation.
