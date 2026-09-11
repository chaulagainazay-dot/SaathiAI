"""FM-I1.5 pre-declared performance thresholds (defined BEFORE measurement).

These bounds are for the in-process FakeInMemoryHarness proof only.
They are not production SLAs. Failing a threshold fails the stress gate.
"""
from __future__ import annotations

# All latencies are wall-clock milliseconds on a single developer/CI host.
# They intentionally leave headroom for CI noise without being unbounded.

MAX_SESSION_START_MS = 50.0
MAX_TURN_PROCESSING_MS = 50.0
MAX_CANCEL_LATENCY_MS = 50.0

# Events per second for a single session producing multi-turn text events.
MIN_EVENT_THROUGHPUT_EPS = 200.0

# Per-session residual after close+purge: event list retained only while session
# remains in harness map; after purge_closed_sessions session count must drop.
MAX_RESIDENT_CLOSED_SESSIONS = 0

# Concurrent stress (bounded by controller max_sessions for admission tests;
# isolation stress may raise max_sessions temporarily).
CONCURRENCY_LEVELS = (10, 50, 100)

# Memory: allow at most this many MiB growth for 50 multi-turn sessions
# (RSS delta). Soft bound — measured with tracemalloc where available.
MAX_MEMORY_GROWTH_MIB_50_SESSIONS = 64.0

# Replay: normalized fingerprint fields must match across two scripted runs.
REPLAY_NORMALIZE_DROP_KEYS = frozenset({"timestamp", "event_id"})
