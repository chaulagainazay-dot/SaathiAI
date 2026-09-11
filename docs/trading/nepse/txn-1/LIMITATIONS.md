# Limitations

- `Meroshare`, `TMS`, and `Nepal Share` transaction schemas remain
  `SOURCE_SCHEMA_UNVERIFIED`. Only synthetic provisional fixtures were tested.
- Real source compatibility and end-to-end import are not certified. Genuine
  redacted headers and semantics remain NEPSE-SCHEMA-1.
- Only UTF-8 CSV/TSV is accepted. `.xlsx` is not read and no dependency was
  added.
- The repository still ships no populated NEPSE instrument list. Callers must
  supply canonical `NepseInstrument` records; unknown listings reject closed.
- Bikram Sambat dates are unsupported. Ambiguous numeric dates reject closed.
- Non-NPR values reject because an unverified provisional schema cannot prove a
  different currency.
- Availability is only carried when an explicit timezone-aware field exists;
  no historical availability is inferred.
- Accounting treatment, cost basis, reconciliation, and ledger application are
  not implemented here.
- No real provider, broker, account, order, or market-data connection was used.

These limitations are compatible with
`NEPSE_TRANSACTION_IMPORT_CONTRACT_CERTIFIED_WITH_LIMITATIONS`; they prevent a
claim of real source-specific import certification.
