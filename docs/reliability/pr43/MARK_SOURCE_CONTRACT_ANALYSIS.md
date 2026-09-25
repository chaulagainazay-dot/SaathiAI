# MARK_SOURCE_CONTRACT_ANALYSIS

## Intended semantics (post T-NEXT-1.1)

`get_account().mark_source` answers: **where do books valuation marks come from?**

| Condition | `mark_source` |
| --- | --- |
| Canonical fund open + ledger state available | `canonical_fund_ledger_marks_or_cost` |
| Fund missing / books unavailable | `oms_lifecycle_fallback` |

Also set:

- `books_authority` = `canonical_fund_ledger` when books overlay applies
- `source` = `canonical_fund_ledger`
- OMS cash/avg-cost remain in `oms_lifecycle` shadow — not books authority

## Outcome

```text
A. canonical_fund_ledger_marks_or_cost is correct
```

The expectation `replay/fixture` is a **stale pre-cutover** test assumption. Market-event fixture provenance is not the books mark authority after T-NEXT-1.1.

## Consumers

Only `tests/test_m62_8_workspace.py` asserted `replay/fixture`. Production path is `PaperTradingService.get_account`.

## Fix

- Update workspace test expectation to canonical value.
- Add `test_account_detail_canonical_books_mark_source_after_cutover` for explicit contract.
