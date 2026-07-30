# M208–M215 Test Results (fresh recovery verification)

**Terminal verdict:** `OPERATIONAL_GRADUATION_CERTIFIED_WITH_LIMITATIONS`

## Focused M208–M215

```
tests/test_m208_m215_ops_graduation.py
15 passed in 0.25s
EXIT:0
```

Raw: `FOCUSED_M208_M215_TESTS.txt`

## M200 compatibility

```
tests/test_m200_m207_durable_paper.py
15 passed in 0.21s
EXIT:0
```

Raw: `M200_COMPAT_TESTS.txt`

## Broader M192–M208

```
42 passed in 0.41s
EXIT:0
```

Raw: `BROADER_TG_REGRESSION.txt`

## TG M166–M215 regression

```
115 passed in 0.96s
EXIT:0
```

Raw: `TG_M166_M215_REGRESSION.txt`

## Full backend

```
5568 passed, 1 skipped, 321 warnings in 882.40s
EXIT:0
```

Raw: `FULL_BACKEND_SUITE.txt`

## Frontend

| Suite | Result | Raw |
| --- | --- | --- |
| M208 unit | 2 passed | `FRONTEND_M208_UNIT.txt` |
| Trading unit | 33 passed | `FRONTEND_TRADING_UNIT.txt` |
| Full frontend | 240 passed | `FRONTEND_FULL_SUITE.txt` |
| Production build | pass | `FRONTEND_BUILD.txt` |

Node: v26.4.0 · npm: 11.17.0

## Browser

```
OPS_GRADUATION_BROWSER_CERT_PASSED_WITH_LIMITATIONS
failed_gates: 0
failed_journeys: 1 (api_paper_approvals soft)
screenshots: 11
```

Raw: `BROWSER_CERT_LOG.txt`, `browser/M215_BROWSER_CERT.json`

## Safety scans

- `AUTHORITY_SCAN.json` — all_required_ok
- `CREDENTIAL_SCAN.json` — pass
- `LIVE_PATH_SCAN.json` — pass
- `SECURITY_SCAN.json` — pass

THE SYSTEM REMAINS PAPER ONLY.
LIVE TRADING IS NOT AUTHORIZED.
NO STRATEGY IS AUTOMATICALLY PROMOTED TO LIVE EXECUTION.
