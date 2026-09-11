# TARGETED_TEST_REPORT

```text
python3.12 -m pytest \
  tests/test_m17_1_live.py::test_live_browser_dom_and_click \
  tests/test_m62_8_workspace.py \
  tests/portfolio_performance/ tests/portfolio_construction/ \
  tests/portfolio_risk_engine/ tests/fund_ledger/ -q
→ 77 passed
```

Browser isolated stress: 5/5 pass for `test_live_browser_dom_and_click`.
