# Official source contract

Verified on 2026-09-03 against Binance's official public-data documentation and a bounded
request to the archive host.

- Documentation: <https://github.com/binance/binance-public-data/blob/master/README.md>
- Archive root: <https://data.binance.vision/data/spot/monthly/klines/>
- Object path:
  `data/spot/monthly/klines/{SYMBOL}/1d/{SYMBOL}-1d-{YYYY}-{MM}.zip`
- Companion checksum: the same filename with `.CHECKSUM` appended.
- ZIP member: exactly one `{SYMBOL}-1d-{YYYY}-{MM}.csv` file.
- CSV: headerless, strict UTF-8, exactly 12 kline fields in the official order.
- Timestamp units: milliseconds before 2025-01-01; microseconds from 2025-01-01 onward.
- Verification: SHA-256; the checksum record must name the exact archive.
- Source revisions: Binance documents that archived files can later be updated. A changed
  checksum is therefore a new local dataset revision, never a silent replacement.

The acquisition client permits only HTTPS responses whose initial and final host is
`data.binance.vision`. It performs no retries, uses no API key, and does not contact account,
order, margin, futures, or withdrawal endpoints.

## Point-in-time semantics

- `event_timestamp`: UTC bar open.
- `as_of`: exclusive UTC bar close.
- `available_at`: exclusive UTC bar close, at bar-level precision.
- `received_at`: actual archive retrieval timestamp.

The archive does not encode historical publication instants for each row. The manifest
therefore records `ARCHIVE_PUBLICATION_HISTORY_NOT_RECONSTRUCTED` and
`BAR_CLOSE_AVAILABILITY_PRECISION`. This policy never makes a future bar visible before its
own close, but it does not claim second-level archive-publication reconstruction.
