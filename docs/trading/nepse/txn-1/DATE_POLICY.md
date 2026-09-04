# Date and Availability Policy

NEPSE-TXN-1 uses MD-1's distinction between event time and knowledge time.

| Field | Contract |
|---|---|
| `trade_date` | Required source event date |
| `settlement_date` | Optional explicit settlement date; cannot precede trade date |
| `available_at` | Optional timezone-aware earliest legitimate availability supplied by the provisional record; never inferred from trade date |
| `received_at` | Timezone-aware ingestion time; defaults to current UTC when the caller does not supply it |

If `available_at` is absent it remains `None`. The importer does not invent a
historical timestamp for a user-uploaded export. When present, it must not
precede the trade date in `Asia/Kathmandu` and must not be later than
`received_at`.

Accepted date formats are deliberately narrow:

- `YYYY-MM-DD`;
- `DD/MM/YYYY` only when the value cannot also be interpreted as MM/DD.

Values such as `01/02/2026` are `AMBIGUOUS_DATE`. Invalid calendar dates are
`INVALID_DATE`. Year-first slash forms and other unsupported forms are
`UNSUPPORTED_DATE_FORMAT`. No Bikram Sambat conversion library or ad-hoc
conversion rule was added; BS input remains an explicit future requirement.
