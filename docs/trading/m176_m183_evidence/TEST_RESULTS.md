# M176–M183 Test Results

## Focused M176–M183

```
.venv/bin/python -m pytest tests/test_m176_m183_paper_validation.py -q
18 passed (included in combined 46 with M166)
```

## M166–M175 + M176–M183 focused

```
tests/test_m176_m183_paper_validation.py tests/test_m166_m175_trading_guardian.py
46 passed
```

## M62 strategy/paper + focused

```
139 passed (with m62_4 + m62_5 + m166 + m176)
```

## Full backend

```
5499 passed, 1 skipped
```

## Frontend

```
npm test → 218 passed
```

## ESLint

```
passed
```

## Production build

```
passed (includes /trading/research)
```

## Playwright

```
node scripts/m183_trading_guardian_browser_cert.mjs
result: TRADING_GUARDIAN_BROWSER_CERT_PASSED
failed_gates: 0
failed_journeys: 0
owner_signoff: NOT_CLAIMED_AUTOMATED_ONLY
```

Evidence: `docs/trading/m176_m183_evidence/browser/M183_BROWSER_CERT.json`
