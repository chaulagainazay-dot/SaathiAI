# DUAL_AUTHORITY_AUDIT

| Writer | Role after cutover |
| --- | --- |
| PaperStore cash/positions | OMS lifecycle + reservation only |
| PortfolioLedgerService | **Sole books authority** |
| strategy/accounting | Backtest only (unchanged) |
| TG portfolio engines | Risk/analytics — must not own cash |

Constant: `LEGACY_OMS_STATE_NOT_BOOKS_AUTHORITY = True`

