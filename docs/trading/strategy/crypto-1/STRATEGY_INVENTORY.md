# STRATEGY-CRYPTO-1 existing strategy inventory

Inventory completed against certified HEAD `0af241516cc7fe6374af7e4c6cbc7cafe64aa160` before final-test evaluation.

| Classification | Strategy ID / implementation | Inputs and output | Look-ahead / semantics review | Parameters, costs, venue, tests |
|---|---|---|---|---|
| COMBINE | `trend_following` and `momentum_rs` in `saathi/platform/tg/strategies/` | Moving averages, prior range, volume, return, benchmark/breadth; legacy `TradeSignal` entry | Both use trailing windows, but the legacy output is not the canonical `TradingSignal`; relative-strength breadth/sector assumptions do not transfer cleanly to two spot assets | 5–6 parameters each; cost-unaware evaluators; wildcard instruments and daily timeframe; covered by institutional-strategy tests |
| KEEP AS INFRASTRUCTURE | `valid_momentum` in `saathi/platform/strategy/fixtures.py` | SMA relationship; declarative entry/exit | Trailing feature contract is mature, but this is a synthetic fixture with a sizing rule, not qualification evidence | 3 features/rules; simulated cost path exists; fixture coverage in `test_m62_4_strategy.py` |
| ADAPT | `kotegawa_mean_reversion` in `saathi/platform/tg/strategies/` and `valid_mean_reversion` fixture | Prior mean/deviation, volume, reversal, liquidity/spread; legacy entry-only `TradeSignal` or declarative entry/exit | Trailing windows are usable; venue-specific breadth/volume gates and direct stop-price fields are not reused in the baseline signal | 7 legacy parameters reduced to 3; legacy evaluator cost-unaware; wildcard venue; existing strategy and M62.4 tests |
| ADAPT NARROWLY | Breakout branch in `BacktestEngineV2` | Prior 20 closes and same-loop target position | Prior range excludes the decision value, but the engine executes at that decision bar, sizes directly, defaults to synthetic data, and is not PIT/revision aware | One implicit lookback; commission/slippage but no independent spread; synthetic-focused tests |
| REJECT FOR QUALIFICATION | `BacktestEngineV2` as a whole | Inline trend/mean/breakout decisions, quantities, fills and ranking | Same-bar execution and synthetic fallback violate STRATEGY-CRYPTO-1 | Not used by this milestone |
| KEEP | `TradingSignal`, `TradingIntentProposal`, PIT revision resolver, OOS lock, walk-forward result, and crypto cost model | Canonical proposal-only boundaries | Certified predecessors; no strategy execution authority | Reused and extended by focused tests |

Selected initial families, exactly three:

1. `crypto_spot_trend_momentum` — combined and simplified from mature trend/momentum logic.
2. `crypto_spot_breakout` — narrowly adapted prior-range hypothesis with a new canonical evaluator.
3. `crypto_spot_mean_reversion` — simplified bounded deviation plus reversal confirmation.

No RSI, MACD, ATR, Bollinger stack, LLM research input, shorting, leverage, futures, perpetuals, options, or margin was added.
