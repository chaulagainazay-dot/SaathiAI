# M62.2 — Deterministic Replay

`ReplayEngine` replays a bar series in a stable order (sorted by start_time then
instrument), so the same input yields the same event order regardless of insertion
order (certified). Step-mode, no wall-clock dependency. Controls: start, pause,
resume, stop, reset; `checkpoint()`/`restore()` (rejects corrupted or
dataset-version-mismatched checkpoints). Replay places NO orders and exposes events
via a stable `ReplayEvent` interface for future backtest/simulation layers.
