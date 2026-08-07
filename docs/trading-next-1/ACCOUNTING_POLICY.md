# ACCOUNTING_POLICY

| Policy | Value |
| --- | --- |
| Environment | PAPER only |
| Long-only | Yes — shorts raise LedgerError |
| Leverage | Disabled |
| Negative cash | Forbidden by default |
| Lot method | **FIFO** |
| Fee on buy | Allocated into lot cost price |
| Fee on sell | Cash deduction; separate total_fees |
| Corrections | Append CORRECTION / opposite fill — no silent delete |
| Multi-currency mix | Rejected without explicit conversion |

