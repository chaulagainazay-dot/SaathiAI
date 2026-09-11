# STRATEGY-CRYPTO-1 final decision

**CRYPTO_STRATEGY_QUALIFICATION_CERTIFIED_WITH_LIMITATIONS**

The frozen three-family, two-instrument preregistration was executed once against the
certified real public Binance Spot dataset. It consumed 72 accounted trials and six
distinct final-TEST evaluations. No configuration or hypothesis was changed after TEST.

Exact survivor count: **1**.

- `crypto_spot_mean_reversion@1.0.0` on `BINANCE:BTC/USDT`:
  `PAPER_CANDIDATE`.
- BTC trend/momentum, BTC breakout, ETH trend/momentum, and ETH breakout:
  `OOS_VALIDATED_WITH_LIMITATIONS`; they are not paper candidates.
- ETH mean reversion: `REJECTED`.

The survivor's final TEST net return was `0.1895318557`, versus BTC buy-and-hold
`0.2649373883`; its benchmark-relative return was therefore negative
(`-0.0754055326`). Its two pre-TEST walk-forward OOS segments were both positive and it
remained positive under every frozen cost and stress scenario. The negative TRAIN
result and benchmark underperformance are preserved; `PAPER_CANDIDATE` is not a claim
of statistical significance or live readiness.

The exact qualification artifact has SHA-256
`45a115c978047e228c769d05cbef48e5d1a59070c94f4706dc2903f561bccd40`
and is stored read-only under `data/research/strategy-crypto-1/` keyed by the certified
dataset version. Detailed economic results are in `ECONOMIC_RESULTS.md` and
`RESULTS.json`.

The single final canonical offline regression passed with exit code 0: 7,944 passed,
8 skipped, and 12 deselected. Its durable log is
`/tmp/saathios-crypto-dataset1-final.log` with SHA-256
`0526c518ee543c068bc06f7586fe2f9f586e0280c9a72bcb6161ed699a27dbd4`.
Post-cleanup `storage_report()` shows 20.2 GB free and healthy.

The next dependency is `PORTFOLIO-CONSTRUCTION-V2`, bounded to certified candidate use.
`STRATEGY-NEPSE-1` remains deferred while `NEPSE_COST_POLICY_UNVERIFIED` is open.
No long-running PAPER/SHADOW process may start until RESEARCH-3 persistence debt for
decisions, signals, intents, outcomes, lessons, and qualification state is closed.
