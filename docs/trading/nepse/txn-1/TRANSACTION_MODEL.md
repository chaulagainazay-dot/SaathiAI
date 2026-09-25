# NEPSE-TXN-1 Transaction Model

`saathi.platform.nepse.transactions.NEPSEExternalTransaction` is the canonical
normalized representation of an external NEPSE activity record. It is an
immutable import proposal, not a Fund Ledger event, position mutation, cash
mutation, order, or execution request.

The architecture is:

```text
untrusted CSV/TSV bytes or text
  -> explicitly selected provisional source adapter
  -> bounded canonical parser
  -> canonical NepseInstrument resolution
  -> NEPSEExternalTransaction validation
  -> NEPSETransactionImportResult
  -> future reconciliation
  -> future explicit ledger application
```

The typed vocabulary is `BUY`, `SELL`, `BONUS`, `RIGHTS_ALLOTMENT`,
`IPO_ALLOTMENT`, `FPO_ALLOTMENT`, `TRANSFER_IN`, `TRANSFER_OUT`,
`DIVIDEND_CASH`, `DIVIDEND_STOCK`, `MERGER_ADJUSTMENT`, `SPLIT_ADJUSTMENT`,
`CORPORATE_ACTION`, `REVERSAL`, and `UNKNOWN`.

## Conventions

- Instrument identity must resolve to an existing `NepseInstrument`; a raw
  symbol is never sufficient.
- Quantity is `Decimal`, unsigned, positive, and whole when present. `SELL` and
  `TRANSFER_OUT` express direction through their type, not a negative quantity.
- `BUY` and `SELL` require a positive unit price. Corporate actions and
  transfers may legitimately omit price. Absent values remain `None`, never a
  fabricated zero.
- Money uses `Decimal`; the provisional schemas accept NPR only. Magnitude is
  bounded at `1E18` and scale at eight decimal places to prevent numeric bombs.
- `UNKNOWN` is an accepted normalized fact with the original type and
  description preserved and an `UNKNOWN_TRANSACTION_TYPE` warning. It is not
  silently coerced to a known financial event.
- Corporate-action facts carry no cost-basis or posting decision.

`NEPSETransactionImportResult` counts duplicates inside `accepted` because the
rows remain available for reconciliation. Its invariant is always:

```text
accepted + rejected == rows_seen
```

Blank physical records are not transaction rows. Whole-file security failures
raise a typed `NEPSETransactionFileError` before any partial result can escape.
