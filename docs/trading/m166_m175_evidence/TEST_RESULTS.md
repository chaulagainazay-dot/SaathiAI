# M166–M175 Test Results

## Focused backend

```
.venv/bin/python -m pytest tests/test_m166_m175_trading_guardian.py -q
28 passed
```

## M62 trading stack regression

```
.venv/bin/python -m pytest tests/test_m62_trading_models.py tests/test_m62_2_market_data.py \
  tests/test_m62_3_research.py tests/test_m62_4_strategy.py tests/test_m62_5_paper_broker.py \
  tests/test_m62_6_reconciliation.py tests/test_m62_7_safety.py tests/test_m166_m175_trading_guardian.py -q
233 passed
```

## Full backend

```
.venv/bin/python -m pytest tests/ -q
5481 passed, 1 skipped
```

## Frontend

```
cd saathi-os && npm test
216 passed
```

Includes `lib/m166_trading_guardian.test.js` paper-only label checks.

## Lint

```
cd saathi-os && npm run lint
exit 0
```

## Security scans (tg package)

- Live broker / credential enablement: none
- Unsafe exec/eval/subprocess/socket: none
- Public listener bind: none
- Authority self-approval enablement: denied by design
- `LIVE_TRADING_AUTHORIZED = False`, `LIVE_ORDER_CAPABLE = False`, `BROKER_CREDENTIAL_SUPPORT = False`
