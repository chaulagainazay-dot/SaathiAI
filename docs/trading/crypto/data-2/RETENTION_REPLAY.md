# Retention and replay capture

Capture is a bounded in-memory diagnostic window with explicit overflow counting; it does not create an unbounded tick archive. Persisted DatasetManifest/replay integration and retention jobs are deferred until a storage budget and CRYPTO-DATA-2 runtime are selected.
