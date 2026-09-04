# NEPSE-LEDGER-1 Reconciliation Contract

`NEPSEExternalTransaction` is evidence. `reconcile_transactions` produces immutable `NEPSEImportProposal` records and typed reconciliation statuses; it never appends Fund Ledger events. The Canonical Fund Ledger remains the sole accounting authority.

BUY/SELL and cash dividend facts are mapped only when deterministically known. Corporate actions, transfers, and other events remain proposal-only with `UNSUPPORTED_LEDGER_EVENT`/`POLICY_REQUIRED` warnings until an approved ledger event contract exists.
