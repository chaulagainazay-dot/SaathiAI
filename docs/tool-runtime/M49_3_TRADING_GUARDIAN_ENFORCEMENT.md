# M49.3 Trading Guardian Enforcement

Exact state: `TRADING_GUARDIAN_UNENGAGED_ADVISORY_ONLY`

- market/advisory tools → FINANCIAL_ADVISORY with approval
- order submission / cancel / withdraw / leverage → PROHIBITED
- generic shell cannot invoke trading CLIs (freeform shell blocked)
- approval cannot override financial execution prohibition
- dry-run cannot become live execution
- paper/advisory cannot access live broker credentials
