"""Cleanup Engine — executes deletions the Lifecycle Engine authorizes (SES-019A Part 9).

Architectural contract: **the Cleanup Engine never decides what to delete.**
It scans directories, hands each job to the Lifecycle Engine, and executes
only what comes back authorized. Flow:

    Cleanup Engine → asks Lifecycle Engine → authorized files returned
        → delete → Storage DB updated → event emitted → Mission Control updated

Capabilities: hourly / nightly / weekly runs, failed-job cleanup, orphan
detection, manifest validation, dry-run mode, and audit logging to
``storage_cleanup_log``. Every run emits ``storage.cleanup.*`` events.

Independently testable (AP-12): storage root, clock, and event publisher are
all injected; tests run against a temp tree with no real scheduler or bus.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from saathi.storage.db import StorageDB
from saathi.storage.lifecycle import LifecycleEngine, JobCleanupResult
from saathi.events import STORAGE_EVENTS

# A job dir is "failed/abandoned" once it is older than this and not in production.
FAILED_JOB_RETENTION_SECONDS = 24 * 3600


@dataclass
class CleanupRun:
    kind: str
    dry_run: bool
    started_at: float
    finished_at: float = 0.0
    jobs_scanned: int = 0
    files_deleted: int = 0
    files_protected: int = 0     # e.g. PERMANENT files the engine refused to touch
    bytes_freed: int = 0
    orphans: list[str] = field(default_factory=list)
    bad_manifests: list[str] = field(default_factory=list)
    ok: bool = True

    def merge_job(self, res: JobCleanupResult) -> None:
        self.jobs_scanned += 1
        if not res.ok:
            self.bad_manifests.append(f"{res.job_id}: {res.skipped_reason}")
            return
        for r in res.results:
            if r.deleted:
                self.files_deleted += 1
                self.bytes_freed += r.freed_bytes
            elif "permanent" in r.reason:
                self.files_protected += 1


class CleanupEngine:
    def __init__(
        self,
        storage_root: Path,
        lifecycle: LifecycleEngine,
        db: StorageDB,
        now: Callable[[], float] = time.time,
        publish: Callable[[str, dict], None] | None = None,
        dry_run: bool = False,
    ):
        self.root = Path(storage_root)
        self.lifecycle = lifecycle
        self.db = db
        self._now = now
        self._publish_fn = publish
        self.dry_run = dry_run
        self.jobs_dir = self.root / "temp" / "jobs"

    def _publish(self, key: str, payload: dict) -> None:
        if self._publish_fn is not None:
            self._publish_fn(STORAGE_EVENTS[key], payload)

    # --- discovery -------------------------------------------------------
    def _job_dirs(self) -> list[Path]:
        if not self.jobs_dir.exists():
            return []
        return [p for p in self.jobs_dir.iterdir() if p.is_dir()]

    def find_orphans(self) -> list[Path]:
        """Job dirs with no manifest.json — cannot be safely reasoned about,
        so they are surfaced for review, never auto-deleted."""
        return [d for d in self._job_dirs() if not (d / "manifest.json").exists()]

    def find_failed_jobs(self, older_than_seconds: int = FAILED_JOB_RETENTION_SECONDS) -> list[Path]:
        cutoff = self._now() - older_than_seconds
        out = []
        for d in self._job_dirs():
            manifest = d / "manifest.json"
            if not manifest.exists():
                continue
            if manifest.stat().st_mtime < cutoff:
                out.append(d)
        return out

    # --- runs ------------------------------------------------------------
    def _run(self, kind: str, job_dirs: list[Path]) -> CleanupRun:
        run = CleanupRun(kind=kind, dry_run=self.dry_run, started_at=self._now())
        self._publish("cleanup_started", {"kind": kind, "dry_run": self.dry_run, "jobs": len(job_dirs)})
        try:
            for d in job_dirs:
                res = self.lifecycle.cleanup_job(d, dry_run=self.dry_run)
                run.merge_job(res)
                if res.ok:
                    for r in res.results:
                        if r.deleted:
                            self._publish("lifecycle_deleted", {"path": r.path, "bytes": r.freed_bytes})
                        elif "permanent" in r.reason:
                            self._publish("lifecycle_protected", {"path": r.path})
            run.orphans = [str(p) for p in self.find_orphans()]
        except Exception as exc:  # a cleanup failure must never crash the caller
            run.ok = False
            self._publish("cleanup_failed", {"kind": kind, "error": str(exc)})
        finally:
            run.finished_at = self._now()
            self._audit(run)
            if run.ok:
                self._publish("cleanup_finished", {
                    "kind": kind, "deleted": run.files_deleted,
                    "protected": run.files_protected, "bytes_freed": run.bytes_freed,
                })
        return run

    def hourly(self) -> CleanupRun:
        """Remove failed/abandoned job dirs (>24h); surface orphans."""
        return self._run("hourly", self.find_failed_jobs())

    def nightly(self) -> CleanupRun:
        """Full pass over every job directory."""
        return self._run("nightly", self._job_dirs())

    def weekly_verify_archives(self) -> CleanupRun:
        """Weekly archive verification pass. Until the Archive Manager exists,
        this validates manifests and reports state without deleting."""
        run = CleanupRun(kind="weekly", dry_run=True, started_at=self._now())
        run.bad_manifests = [str(p) for p in self.find_orphans()]
        run.finished_at = self._now()
        self._audit(run)
        return run

    def clean_one(self, job_dir: Path, kind: str = "manual") -> CleanupRun:
        return self._run(kind, [job_dir])

    def _audit(self, run: CleanupRun) -> None:
        self.db.record_cleanup_run(
            run_kind=run.kind,
            started_at=run.started_at,
            finished_at=run.finished_at,
            dry_run=int(run.dry_run),
            jobs_scanned=run.jobs_scanned,
            files_deleted=run.files_deleted,
            files_protected=run.files_protected,
            bytes_freed=run.bytes_freed,
            orphans_found=len(run.orphans),
            bad_manifests=len(run.bad_manifests),
            ok=int(run.ok),
            detail_json=None,
        )
