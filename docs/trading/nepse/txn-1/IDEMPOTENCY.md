# Transaction Identity and Duplicate Policy

IDs are deterministic `NEPSE-TXN-<sha256-prefix>` values.

When any source reference is present, identity uses the source plus the ordered
set of external reference, contract number, and settlement reference. This
keeps source-issued identity authoritative and makes a reused reference with
different facts visible as a conflict.

Without a source reference, identity hashes normalized source facts:

- source and canonical instrument ID;
- trade date and transaction type;
- quantity and unit price;
- gross and net amount;
- normalized raw type and description.

Row number, file name, file fingerprint, raw-row hash, and `received_at` are not
identity inputs. Reordering an export or importing the same event from a later
download therefore does not change the transaction ID. The exact source-file
fingerprint and per-row `raw_ref` remain separate provenance.

Duplicate rows are never merged or dropped:

- `EXACT_DUPLICATE`: same ID and same normalized facts;
- `CONFLICTING_DUPLICATE`: same ID but different normalized facts, including
  settlement or explicit availability facts;
- `POSSIBLE_DUPLICATE`: no source references, different IDs, but the same
  source/instrument/date/type/quantity/price core;
- `UNIQUE`: none of the above.

The first row remains `UNIQUE`; every later matching row is listed in
`duplicate_rows` and remains in `transactions`. A cryptographic collision with
different facts is therefore surfaced as `CONFLICTING_DUPLICATE`, never
silently treated as the same transaction.
