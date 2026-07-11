"""M13.5 runtime identity — safe build/version/schema metadata.

Used by the /api/v1/system/version endpoint and by the frontend to detect a
stale/incompatible backend (the exact failure that broke M11's first live
smoke test). Exposes only counts + a commit hash — never secrets/paths/env.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

API_VERSION = "1.0"
ROUTE_MANIFEST_VERSION = "m15"
# schema versions per subsystem db (bumped when a table changes)
SCHEMA_VERSIONS = {
    "chat": "m8", "memory": "m9", "agent_runtime": "m10",
    "voice_os": "m12", "studio_os": "m13", "ceo_os": "m14", "repair": "m9",
    "connectors": "m15",
}
CRITICAL_MANIFEST_VERSION = "m15.3"

_PROCESS_START = time.time()


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=3).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def git_branch() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=3).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def identity(route_count: int = 0) -> dict:
    return {
        "commit": git_commit(),
        "branch": git_branch(),
        "api_version": API_VERSION,
        "route_manifest_version": ROUTE_MANIFEST_VERSION,
        "critical_manifest_version": CRITICAL_MANIFEST_VERSION,
        "schema_versions": SCHEMA_VERSIONS,
        "process_start": _PROCESS_START,
        "uptime_sec": round(time.time() - _PROCESS_START, 1),
        "route_count": route_count,
    }


def compatible(frontend_api_version: str, frontend_route_manifest: str) -> dict:
    """Frontend calls this contract to detect a version mismatch.

    Returns {compatible, reason}. Incompatible when API major differs or the
    route-manifest version the frontend was built against no longer matches.
    """
    reasons = []
    if not frontend_api_version:
        reasons.append("frontend did not report an API version")
    else:
        fe_major = frontend_api_version.split(".")[0]
        be_major = API_VERSION.split(".")[0]
        if fe_major != be_major:
            reasons.append(f"API major mismatch: frontend {frontend_api_version} "
                           f"vs backend {API_VERSION}")
    if frontend_route_manifest and frontend_route_manifest != ROUTE_MANIFEST_VERSION:
        reasons.append(f"route manifest mismatch: frontend {frontend_route_manifest} "
                       f"vs backend {ROUTE_MANIFEST_VERSION}")
    return {"compatible": not reasons, "reason": "; ".join(reasons) or "ok"}
