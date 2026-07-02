"""File Lifecycle Engine — the ONLY sanctioned deleter (SES-019A Parts 1 & 6).

No other module deletes files directly. Departments submit their intent here;
the engine checks each file's declared lifecycle class against policy and
either performs the deletion or refuses it. The cardinal guarantee:

    A PERMANENT-class file is never auto-deleted, under any circumstance,
    regardless of which directory it is found in.

Class is *declared* in a job manifest, never inferred from file extension or
folder name. A directory with a missing/corrupt manifest is skipped and
flagged, never guessed at.

Independently testable (AP-12): the engine operates on any root path and
takes an injectable "now" clock; tests run against a temp dir.
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable


class LifecycleClass(str, Enum):
    PERMANENT = "permanent"     # never auto-deleted
    ARCHIVE = "archive"         # deletable only after verified cloud upload
    WORKING = "working"         # deletable on job completion
    TEMPORARY = "temporary"     # deletable after use / short TTL
    DISPOSABLE = "disposable"   # deletable freely on schedule


# Whether the engine may ever auto-delete a member of this class.
AUTO_DELETE_ELIGIBLE = {
    LifecycleClass.PERMANENT: False,
    LifecycleClass.ARCHIVE: True,      # gated on upload_verified (checked by caller/Cleanup Engine)
    LifecycleClass.WORKING: True,
    LifecycleClass.TEMPORARY: True,
    LifecycleClass.DISPOSABLE: True,
}


@dataclass
class DeletionResult:
    path: str
    deleted: bool
    reason: str
    freed_bytes: int = 0


@dataclass
class JobCleanupResult:
    job_id: str
    results: list[DeletionResult]
    skipped_reason: str | None = None

    @property
    def freed_bytes(self) -> int:
        return sum(r.freed_bytes for r in self.results if r.deleted)

    @property
    def ok(self) -> bool:
        return self.skipped_reason is None


def _path_size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


class LifecycleEngine:
    def __init__(self, now: Callable[[], float] = time.time):
        self._now = now

    # --- the single guard every deletion passes through ------------------
    def may_delete(self, lifecycle_class: LifecycleClass, upload_verified: bool = False) -> tuple[bool, str]:
        if lifecycle_class is LifecycleClass.PERMANENT:
            return False, "permanent class is never auto-deleted"
        if not AUTO_DELETE_ELIGIBLE.get(lifecycle_class, False):
            return False, f"{lifecycle_class.value} not auto-delete-eligible"
        if lifecycle_class is LifecycleClass.ARCHIVE and not upload_verified:
            return False, "archive class requires verified upload before deletion"
        return True, "eligible"

    def delete(
        self,
        path: Path,
        lifecycle_class: LifecycleClass,
        upload_verified: bool = False,
        dry_run: bool = False,
    ) -> DeletionResult:
        allowed, reason = self.may_delete(lifecycle_class, upload_verified)
        if not allowed:
            # A refused PERMANENT deletion is a "protected" outcome, not a failure.
            return DeletionResult(str(path), False, reason)
        if not path.exists():
            return DeletionResult(str(path), False, "path does not exist")
        size = _path_size(path)
        if dry_run:
            return DeletionResult(str(path), False, "dry-run: would delete", freed_bytes=size)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return DeletionResult(str(path), True, "deleted", freed_bytes=size)

    # --- job-directory cleanup driven by manifest.json -------------------
    def cleanup_job(self, job_dir: Path, dry_run: bool = False) -> JobCleanupResult:
        """Delete every eligible file/dir in a job directory per its manifest.
        Skips (does not guess) if the manifest is missing or unreadable.
        With ``dry_run=True`` nothing is deleted; results report what would be."""
        manifest_path = job_dir / "manifest.json"
        if not manifest_path.exists():
            return JobCleanupResult(job_dir.name, [], skipped_reason="manifest.json missing — flagged for review")
        try:
            manifest = json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            return JobCleanupResult(job_dir.name, [], skipped_reason=f"manifest unreadable: {e}")

        job_id = manifest.get("job_id", job_dir.name)
        upload_verified = bool(manifest.get("upload_verified", False))
        results: list[DeletionResult] = []

        for rel, spec in manifest.get("files", {}).items():
            try:
                cls = LifecycleClass(spec.get("class", "permanent"))
            except ValueError:
                results.append(DeletionResult(rel, False, f"unknown class {spec.get('class')!r} — skipped"))
                continue
            target = job_dir / rel
            results.append(self.delete(target, cls, upload_verified=upload_verified, dry_run=dry_run))

        return JobCleanupResult(job_id, results)
