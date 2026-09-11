# Replay architecture

`PointInTimeDataset.replay` uses a deterministic `ReplayClock` and orders visible events by `available_at`, `as_of`, canonical instrument, and source record id. Wall-clock time is not consulted.
