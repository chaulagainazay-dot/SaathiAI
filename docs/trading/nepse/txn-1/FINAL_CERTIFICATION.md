# Final Certification

Verdict:

`NEPSE_TRANSACTION_IMPORT_CONTRACT_CERTIFIED_WITH_LIMITATIONS`

Certified implementation facts:

- canonical immutable `NEPSEExternalTransaction` and fully accounted
  `NEPSETransactionImportResult` exist;
- the required typed transaction vocabulary exists, with unknown semantics
  preserved as `UNKNOWN`;
- money and quantities use bounded finite `Decimal` values, with unsigned whole
  NEPSE share quantities;
- every accepted row resolves through a caller-supplied canonical
  `NepseInstrument` master;
- transaction IDs are stable across row reorder and duplicates are surfaced,
  retained, and classified;
- no returned result silently loses a non-blank data row;
- file parsing is bounded and fail-closed for hostile/malformed input;
- `trade_date`, `settlement_date`, `available_at`, and `received_at` remain
  distinct; missing availability remains unknown;
- all source schemas remain honestly `SOURCE_SCHEMA_UNVERIFIED`;
- importer authority is ingestion-only, with zero ledger, order, approval,
  guardian, construction, risk, or execution mutation;
- focused, authority, and canonical offline regressions pass;
- the independent fresh-context review completed and its five findings were
  fixed test-first.

The limitations in `LIMITATIONS.md` are material. This verdict does not certify
real Meroshare, TMS, or Nepal Share exports and grants no live capability.

Dependency recommendation after this stop point: evaluate MD-1.1 venue
consistency first, then NEPSE-SCHEMA-1 when genuine headers are available. If
headers remain unavailable, NEPSE-LEDGER-1 may proceed as contract design over
normalized synthetic transactions only; it must not apply transactions yet.

Final safety status:

- `NO_LIVE_TRADING`
- `NO_REAL_BROKER`
- `NO_LEDGER_MUTATION_FROM_IMPORT`
- `NO_WITHDRAWAL`
- `NO_LEVERAGE`
- `NO_LLM_EXECUTION_AUTHORITY`
