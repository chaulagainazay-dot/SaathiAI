# Data-quality decision

CRYPTO-DATASET-1 acquired the predefined 2018-01 through 2025-12 monthly `1d`
archives for BTCUSDT and ETHUSDT from the official Binance public Spot archive. All
192 ZIPs matched their retained published `.CHECKSUM` values. Normalization produced
5,844 canonical `HistoricalBar` records with zero gaps, duplicates, conflicts, or
out-of-order rows.

The exact source revision is bound by dataset version
`sha256-0f1290db14ab0037e6a69e25bcd1d7928087629cf11630f0ac2c52dbb27768e8`
and canonical content SHA-256
`2e7df608235789aec05a3170cd70158e1d628d8118e058658c491de3b0640858`.
Raw archives and checksums are locally read-only; changed future provider checksums
create a new dataset revision rather than replacing this evidence.

Point-in-time decisions cannot see a bar before its exclusive close. Historical
archive publication time is not reconstructable more precisely, so
`ARCHIVE_PUBLICATION_HISTORY_NOT_RECONSTRUCTED` and
`BAR_CLOSE_AVAILABILITY_PRECISION` remain explicit limitations. No synthetic or replay
fixture contributed to strategy promotion.

Current evidence status: `CERTIFIED_REAL_HISTORICAL` with documented PIT limitations.
