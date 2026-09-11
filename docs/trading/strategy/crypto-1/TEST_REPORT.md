# Test report

- Dataset tests were written red-first: the first collection failed because canonical
  `HistoricalBar` support did not yet exist; the completed dataset file has 25 passing
  tests.
- Dataset, strategy, and canonical-bar focused regression: 95 passed.
- Broader dataset/backtest/signal/historical/stress/security focused regression:
  327 passed in 6.47 seconds.
- Live acquisition: 192/192 official Spot archives and 192/192 companion checksums
  retrieved; every published checksum matched before ingestion; persisted
  normalization reproduction passed.
- Frozen strategy qualification: one execution, 72 accounted trials, six spent TEST
  evaluation keys, result artifact SHA-256
  `45a115c978047e228c769d05cbef48e5d1a59070c94f4706dc2903f561bccd40`.
- Canonical offline certification (single final run): 7,944 passed, 8 skipped,
  12 deselected, 324 warnings in 647.91 seconds; exit code 0.
- Durable canonical log: `/tmp/saathios-crypto-dataset1-final.log`.
- Canonical log SHA-256:
  `0526c518ee543c068bc06f7586fe2f9f586e0280c9a72bcb6161ed699a27dbd4`.
- Acquisition log: `/tmp/saathios-crypto-dataset1-acquisition.log`, SHA-256
  `2523a760f59f7e1b28f5f30aaeaf097be8f60678356e4a91a31ce1b51f2298fb`.
- Final `storage_report()`: 20.2 GB free, healthy, after removing only the completed
  1.1 GB pytest sandbox.
