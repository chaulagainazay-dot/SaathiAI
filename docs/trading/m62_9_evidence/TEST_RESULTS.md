# M62.9 — Test & Regression Results

Environment: isolated venv, Python 3.12.13, pytest 9.1.1.
Command: `python -m pytest tests/<suite>.py -q`

## Full trading suite — 146 passed, 0 failed

| suite | result | scope |
|---|---|---|
| `test_m62_trading_models.py` | 19 passed | M62.1 canonical domain models |
| `test_m62_2_market_data.py` | 16 passed | M62.2 market data quality + replay |
| `test_m62_3_research.py` | 14 passed | M62.3 evidence-backed thesis pipeline |
| `test_m62_4_strategy.py` | 47 passed | M62.4 strategy engine + backtesting |
| `test_m62_5_paper_broker.py` | 46 passed | M62.5 paper broker lifecycle |
| `test_m49_3_trading_boundary.py` | 4 passed | trading tool boundary (prohibited financial-execution) |
| **TOTAL** | **146 passed** | |

## Scenario coverage already proven by the M62.5 suite

- **Safety (fail-closed)**: prohibited configs (LIVE/PRODUCTION/REAL_MONEY/LEVERAGE/
  MARGIN/SHORT_SELLING/OPTIONS/FUTURES/PERPETUALS/DERIVATIVES/BORROWING/LIVE_BROKER)
  each raise `PaperSafetyError`; non-PAPER environment rejected.
- **State machines**: broker + account transition edges; terminal immutability.
- **Fill engine (pure, deterministic)**: market buy at ask+slippage; limit not-crossed →
  no fill; limit never fills beyond limit; partial fill on low liquidity; invalid/stale
  quality and closed market block fills; identical inputs → identical `result_hash`.
- **Service flow**: reserve→fill, intent↔order separation, insufficient cash rejected,
  oversell rejected, SELL realizes P&L, partial-then-complete, Guardian veto BEFORE
  submission (intent → REJECTED).
- **Idempotency**: duplicate submission → one order; duplicate market event → one fill.
- **Cancellation**: cancel-open releases reservation; cancel-after-fill rejected;
  partial-then-cancel retains fill; fill-after-cancel rejected.
- **Halt**: blocks new orders; requires account owner.
- **Persistence / restart**: order + reservation preserved; no duplicate fill after
  restart; fills immutable/append-only.
- **Tenant isolation**: cross-tenant read/cancel/account access rejected.
- **Permissions**: viewer cannot propose/submit.
- **Adversarial**: negative quantity, unsupported side (SHORT)/type (STOP), atomic
  rollback on approval failure, financial-execution tool PROHIBITED, no broker import
  in research/strategy.
- **Gateway integration**: submit consumes approval atomically then fills through the
  Gateway; reused approval blocked; cross-tenant approval rejected; missing approval
  blocked.
- **HTTP**: full `/paper` lifecycle; unauth = 401; no order route outside `/paper`.
