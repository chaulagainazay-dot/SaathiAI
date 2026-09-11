# TESTS — UI-NEXT-3.1

## Frontend (saathi-os)

```text
npm test
→ 432 passed, 0 failed

node --test lib/command-motion.test.js
→ pass

npm run build
→ success

npm run cert:ui-next-3-1
→ BROWSER_CERT_PASS
   axe critical=0 serious=0
   19 screenshots
```

## Backend (relevant subset)

```text
pytest tests/test_t_next_1_1_ledger_cutover.py \
       tests/portfolio_performance \
       tests/portfolio_construction \
       tests/portfolio_risk_engine \
       tests/fund_ledger \
       tests/test_m296_m303_portfolio_risk.py \
       tests/test_m166_m175_trading_guardian.py \
       tests/test_m79_voice_runtime.py
→ 136 passed
```

## Not claimed

Full-suite (entire `tests/`) was **not** re-run end-to-end in this mission; predecessor PR #43 already certified full-suite at repair SHA `1855d5a` with tip docs-only at `6016600`.
