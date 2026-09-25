# MD-1.1 Migration

- `MdRegisterBody`: removed `US`/`XNAS` defaults; omitted fields are neutral.
- `DatasetRegistry`: validates identity, derives NEPSE only for explicit NEPSE
  market, and stores `UNKNOWN` for generic missing venue.
- OHLCV normalizer: removed XNAS fallback; non-synthetic rows without identity
  reject, while synthetic fixtures use explicit non-real `SIM`.
- Historical import: explicit `market=NEPSE` forces NPR, Asia/Kathmandu, and the
  canonical NEPSE calendar even through the generic local-file adapter.
- Calendar checks: unknown dataset venue returns `UNKNOWN_VENUE` instead of
  applying XNAS sessions.

Explicit XNAS callers and the existing synthetic US/XNAS fixture remain
functional. No unsafe compatibility default was restored.
