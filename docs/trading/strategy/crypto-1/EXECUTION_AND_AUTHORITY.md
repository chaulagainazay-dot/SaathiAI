# Signal, fill, and authority boundary

All three strategy evaluators return canonical `saathi.platform.signal.TradingSignal` objects with `LONG_BIAS`, `REDUCE_BIAS`, `NEUTRAL`, or `NO_SIGNAL`. They never return quantity, orders, OMS messages, cash reservations, broker calls, gateway requests, or executable intents.

The research simulator alone applies hypothetical long/flat sizing. A signal generated from observation `t` may fill only at the open of the next available observation, or a later configured stress observation. `fill_at > decision_at` is tested. There is no short position and no borrowed cash.

`TradingIntentProposal` remains proposal-only and is not required by the baseline qualification run. LLM research is not an input.

Permanent result authority: no live trading, broker, private account, withdrawal, leverage, signal execution, intent execution, or LLM execution authority.
