"""SaathiAI Storage Intelligence — M1 Step 1.

Foundation of the Infrastructure Department's storage stack (SES-019A).
Independently testable (AP-12): every component takes injectable dependencies
so it can be exercised without a real disk, real clock, or live Telegram.

Built so far:
    StorageDB     — SQLite state (watchdog events, jobs, reports)
    DiskWatchdog  — polls free space, escalates notify/pause/emergency

Not built yet (later Step 1 slices): Lifecycle Engine, Cleanup Engine,
Predictive Storage Engine, Archive Manager. See BUILD_STATUS.md.
"""

from saathi.storage.db import StorageDB
from saathi.storage.watchdog import DiskWatchdog, DiskUsage, WatchdogLevel
from saathi.storage.lifecycle import (
    LifecycleEngine,
    LifecycleClass,
    DeletionResult,
    JobCleanupResult,
)
from saathi.storage.cleanup import CleanupEngine, CleanupRun
from saathi.storage.predictive import (
    PredictiveStorageEngine,
    RenderPlan,
    StorageEstimate,
    RenderDecision,
    profile_for,
)

__all__ = [
    "StorageDB",
    "DiskWatchdog",
    "DiskUsage",
    "WatchdogLevel",
    "LifecycleEngine",
    "LifecycleClass",
    "DeletionResult",
    "JobCleanupResult",
    "CleanupEngine",
    "CleanupRun",
    "PredictiveStorageEngine",
    "RenderPlan",
    "StorageEstimate",
    "RenderDecision",
    "profile_for",
]
