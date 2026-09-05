# Discovery

The existing `PortfolioLedgerService` and append-only `LedgerEvent` remain authoritative. This milestone adds an adapter boundary beside them and does not create a second ledger or portfolio store.
