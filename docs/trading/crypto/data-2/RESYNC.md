# Snapshot/resynchronization

`OrderBookSynchronizer` requires a validated snapshot before LIVE and accepts only contiguous update IDs. Gaps, crossed books, invalid prices/quantities, and depth overflow fail closed and require a fresh snapshot. Current implementation is transport-neutral; wire subscription and REST snapshot orchestration remain bounded follow-up work.
