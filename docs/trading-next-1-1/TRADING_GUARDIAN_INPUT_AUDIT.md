# TRADING_GUARDIAN_INPUT_AUDIT

`_guardian_review` portfolio inputs:

| Input | Source |
| --- | --- |
| cash | ledger cash − OMS reserved_cash |
| positions qty/avg | ledger when fund open |
| fallback | OMS lifecycle if fund unavailable |

TG logic/limits **unchanged**. Fail-closed preserved.
`portfolio_input_source` recorded on decision public payload.

