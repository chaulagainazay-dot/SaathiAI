# Security and adversarial review

- Strategies are selected from a static registry; arbitrary expressions, pickle, module imports, generated Python, and filesystem strategy paths are rejected.
- Only canonical Binance BTC/USDT and ETH/USDT spot identities are accepted. Perpetual/futures symbols and cross-asset rows fail closed.
- The zero-cost path and same-bar fill delay are rejected.
- Parameter mappings are immutable; a changed or expanded post-registration grid is rejected.
- Dataset content hash, revision lineage, timestamp awareness, OHLC integrity, and instrument consistency are checked.
- Final-test selection depends only on TRAIN/VALIDATION. A test-only price shock does not change the locked configuration.
- BTC and ETH are separate runners; cross-asset test outcomes cannot select either configuration.
- Walk-forward OOS segments are chronological, non-overlapping, and all retained.
- Synthetic evidence always remains `RESEARCH_ONLY`; it cannot be laundered into a paper candidate.
- No strategy, signal, or result object has execution authority.

Known debt: final-test spending and qualification state are not durable across restart. Escalate persistence before long-running PAPER/SHADOW operation.
