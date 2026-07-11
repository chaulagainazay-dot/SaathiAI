"""M13 storage safety — REAL disk preflight, quotas, checksum dedup, cleanup,
and workspace path confinement.

The user has previously suffered severe disk exhaustion from video generation,
so disk safety is a hard gate: `preflight` uses the real `shutil.disk_usage`
and refuses generation when free space would drop below a safety margin.
All artifact paths are confined under the project workspace — traversal is
rejected. Media binaries live on disk (referenced by URI), never in SQLite.
"""
from __future__ import annotations

import hashlib
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STUDIO_ROOT = ROOT / "data" / "studio_workspaces"

# safety margins
MIN_FREE_GB = 5.0                 # never let free space drop below this
DEFAULT_PROJECT_QUOTA_GB = 10.0
DEFAULT_GLOBAL_QUOTA_GB = 60.0
RENDER_CACHE_QUOTA_GB = 20.0


class StorageError(Exception):
    pass


class PathTraversal(StorageError):
    pass


class InsufficientDisk(StorageError):
    pass


class QuotaExceeded(StorageError):
    pass


@dataclass
class DiskEstimate:
    source_mb: float
    temp_mb: float
    output_mb: float

    @property
    def total_mb(self) -> float:
        return self.source_mb + self.temp_mb + self.output_mb


def free_gb(path: Path | None = None) -> float:
    p = path or STUDIO_ROOT
    p.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(str(p)).free / 1e9


def project_dir(project_id: str) -> Path:
    d = STUDIO_ROOT / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_path(project_id: str, rel: str) -> Path:
    """Resolve `rel` under the project workspace. Rejects traversal/absolute
    paths that would escape the workspace."""
    base = project_dir(project_id).resolve()
    # strip any leading slashes so an "absolute" rel is treated as workspace-relative
    candidate = (base / rel.lstrip("/\\")).resolve()
    if base != candidate and base not in candidate.parents:
        raise PathTraversal(f"path escapes project workspace: {rel!r}")
    return candidate


def preflight(project_id: str, estimate: DiskEstimate, *,
              project_quota_gb: float = DEFAULT_PROJECT_QUOTA_GB) -> None:
    """Hard gate before any media generation. Raises if it would be unsafe.

    Checks (all real): free disk after the job stays above MIN_FREE_GB, and the
    project's current usage + this job stays under its quota.
    """
    need_gb = estimate.total_mb / 1000.0
    avail = free_gb()
    if avail - need_gb < MIN_FREE_GB:
        raise InsufficientDisk(
            f"insufficient disk: {avail:.1f}GB free, job needs ~{need_gb:.1f}GB, "
            f"would breach the {MIN_FREE_GB}GB safety margin")
    used_gb = project_usage_bytes(project_id) / 1e9
    if used_gb + need_gb > project_quota_gb:
        raise QuotaExceeded(
            f"project quota: {used_gb:.1f}GB used + {need_gb:.1f}GB > "
            f"{project_quota_gb}GB quota")


def project_usage_bytes(project_id: str) -> int:
    d = STUDIO_ROOT / project_id
    if not d.exists():
        return 0
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file())


def checksum_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:32]


def checksum_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def dedupe_store(project_id: str, data: bytes, *, ext: str = "bin") -> tuple[Path, str, bool]:
    """Content-addressed store: identical bytes map to one file. Returns
    (path, checksum, was_new)."""
    cs = checksum_bytes(data)
    d = safe_path(project_id, f"assets/{cs}.{ext}")
    d.parent.mkdir(parents=True, exist_ok=True)
    if d.exists():
        return d, cs, False
    d.write_bytes(data)
    return d, cs, True


def cleanup_temp(project_id: str, *, older_than_sec: float = 0) -> int:
    """Remove temp/partial files. Returns count removed."""
    tmp = STUDIO_ROOT / project_id / "tmp"
    if not tmp.exists():
        return 0
    now = time.time()
    n = 0
    for f in tmp.rglob("*"):
        if f.is_file() and (now - f.stat().st_mtime) >= older_than_sec:
            try:
                f.unlink(); n += 1
            except OSError:
                pass
    return n


def cleanup_partial_downloads(project_id: str) -> int:
    """Remove *.part / *.partial abandoned-download files."""
    d = STUDIO_ROOT / project_id
    if not d.exists():
        return 0
    n = 0
    for f in list(d.rglob("*.part")) + list(d.rglob("*.partial")):
        try:
            f.unlink(); n += 1
        except OSError:
            pass
    return n


def storage_health() -> dict:
    total_used = 0
    projects = 0
    if STUDIO_ROOT.exists():
        for p in STUDIO_ROOT.iterdir():
            if p.is_dir():
                projects += 1
                total_used += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return {
        "free_gb": round(free_gb(), 1),
        "min_free_gb": MIN_FREE_GB,
        "healthy": free_gb() > MIN_FREE_GB,
        "studio_used_gb": round(total_used / 1e9, 2),
        "global_quota_gb": DEFAULT_GLOBAL_QUOTA_GB,
        "projects": projects,
    }
