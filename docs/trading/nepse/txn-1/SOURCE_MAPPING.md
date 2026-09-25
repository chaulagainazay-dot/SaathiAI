# Provisional Source Mapping

All three mappings are `SOURCE_SCHEMA_UNVERIFIED`. They are deterministic
fixtures for contract testing, not claims about genuine exports.

| Source | Provisional schema | Required fingerprint |
|---|---|---|
| Meroshare | `MEROSHARE_TRANSACTION_PROVISIONAL_V1` | `Scrip`, `Transaction Type`, `Trade Date`, `Quantity` |
| TMS | `TMS_TRANSACTION_PROVISIONAL_V1` | `Symbol`, `Trade Type`, `Trade Date`, `Quantity`, `Contract No` |
| Nepal Share | `NEPAL_SHARE_TRANSACTION_PROVISIONAL_V1` | `Stock`, `Description`, `Date`, `Qty`, `Reference No` |

Source selection is explicit through `parse_meroshare_transactions`,
`parse_tms_transactions`, or `parse_nepal_share_transactions`. There is no
best-match source guessing.

Mappings live in `transactions/source_schemas.py`, separate from the canonical
models and parser. Known exact aliases include `Purchase -> BUY`, `Sale ->
SELL`, explicit bonus/rights/IPO/FPO/transfer/dividend/adjustment labels, and
their uppercase equivalents after exact case/whitespace normalization. No
substring, fuzzy, or model-driven matching exists.

`EXACT_ALIAS` means the cell exactly matched a provisional mapping. It does not
mean the real provider schema has been verified. `VERIFIED_ALIAS` is reserved
and unused until NEPSE-SCHEMA-1 receives genuine redacted headers and semantics.
If transaction type and description map to two different known meanings, the
row is rejected as `AMBIGUOUS_TRANSACTION`. Unknown text remains `UNKNOWN` and
is preserved.

No source is upgraded to `VERIFIED` by NEPSE-TXN-1.
