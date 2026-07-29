# M184–M191 Test Results

## Focused M184–M191

```
.venv/bin/python -m pytest tests/test_m184_m191_historical_research.py -q
27 passed
```

## M166–M191 focused combined

```
tests/test_m184_m191_historical_research.py
tests/test_m176_m183_paper_validation.py
tests/test_m166_m175_trading_guardian.py
73 passed
```

## Full backend

```
5526 passed, 1 skipped
```

## Frontend

```
npm test → 218 passed
```

## Authority scan

```
LIVE_TRADING_AUTHORIZED=false
LIVE_ORDER_CAPABLE=false
BROKER_CREDENTIAL_SUPPORT=false
Binance private path markers rejected
```
