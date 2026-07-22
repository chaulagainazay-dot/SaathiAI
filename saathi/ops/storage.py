"""M13.5 ops storage — global disk/storage tracking + thresholds + cleanup.

Thresholds gate heavy tasks (renders, backups) before disk damage — the user
has hit disk exhaustion historically. Cleanup is always preview-first
(dry-run) and auditable; user artifacts are never deleted silently.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"

WARN_GB = 10.0
BLOCK_GB = 5.0
CRITICAL_GB = 2.0


def free_gb() -> float:
    DATA.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(str(DATA)).free / 1e9


def _dir_bytes(p: Path) -> int:
    if not p.exists():
        return 0
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def storage_report() -> dict:
    fg = free_gb()
    level = ("critical" if fg < CRITICAL_GB else "block" if fg < BLOCK_GB
             else "warning" if fg < WARN_GB else "ok")
    return {
        "free_gb": round(fg, 1),
        "level": level,
        "thresholds": {"warn_gb": WARN_GB, "block_gb": BLOCK_GB, "critical_gb": CRITICAL_GB},
        "healthy": fg >= BLOCK_GB,
        "usage_mb": {
            "databases": round(sum(f.stat().st_size for f in DATA.glob("*.db")) / 1e6, 1),
            "studio_workspaces": round(_dir_bytes(DATA / "studio_workspaces") / 1e6, 1),
            "backups": round(_dir_bytes(DATA / "backups") / 1e6, 1),
            "artifacts_repairs": round(_dir_bytes(ROOT / "artifacts") / 1e6, 1),
        },
    }


def allow_heavy_task() -> tuple[bool, str]:
    fg = free_gb()
    if fg < BLOCK_GB:
        return False, f"disk below block threshold: {fg:.1f}GB < {BLOCK_GB}GB"
    return True, "ok"


# ── cleanup (preview-first, auditable) ──────────────────────────────────────
def cleanup_candidates(*, temp_older_sec: float = 3600) -> list[dict]:
    """Return removable items WITHOUT deleting. Only temp/partial/abandoned
    files — never user artifacts (scripts, final videos, thumbnails)."""
    out: list[dict] = []
    now = time.time()
    sw = DATA / "studio_workspaces"
    if sw.exists():
        for proj in sw.iterdir():
            for f in list((proj / "tmp").rglob("*")) if (proj / "tmp").exists() else []:
                if f.is_file() and (now - f.stat().st_mtime) >= temp_older_sec:
                    out.append({"path": str(f), "kind": "studio_temp",
                               "size": f.stat().st_size})
            for f in list(proj.rglob("*.part")) + list(proj.rglob("*.partial")):
                if f.is_file():
                    out.append({"path": str(f), "kind": "partial_download",
                               "size": f.stat().st_size})
    return out


def run_cleanup(*, apply: bool = False, temp_older_sec: float = 3600) -> dict:
    cands = cleanup_candidates(temp_older_sec=temp_older_sec)
    removed = 0
    freed = 0
    if apply:
        for c in cands:
            try:
                Path(c["path"]).unlink()
                removed += 1
                freed += c["size"]
            except OSError:
                pass
    return {"applied": apply, "candidates": len(cands),
            "removed": removed, "freed_bytes": freed if apply else 0,
            "would_free_bytes": sum(c["size"] for c in cands)}
