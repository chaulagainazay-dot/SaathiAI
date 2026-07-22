"""Evidence collector — read-only capture of the repository/runtime state.

Everything here is safe (Level 0). It records env-variable PRESENCE only,
never values, and redacts free-text before returning.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from saathi.repair.incident import RepairEvidence
from saathi.repair.secrets_scan import redact

ROOT = Path(__file__).resolve().parent.parent.parent

# Env vars we care about — reported as *_PRESENT booleans only.
_ENV_KEYS = [
    "HF_TOKEN", "HUGGINGFACE_TOKEN", "GMAIL_CREDENTIALS", "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY", "GROQ_API_KEY", "TELEGRAM_BOT_TOKEN",
    "FIREBASE_CREDENTIALS_JSON", "SUPABASE_SERVICE_KEY",
]


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=str(ROOT), capture_output=True, text=True, timeout=15
        ).stdout.strip()
    except Exception:
        return ""


def collect_git_state(ev: RepairEvidence) -> RepairEvidence:
    ev.git_branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    ev.git_head = _git("rev-parse", "HEAD")[:12]
    dirty = _git("status", "--short")
    ev.git_dirty_files = [ln[3:] for ln in dirty.splitlines() if ln.strip()][:50]
    ev.recent_commits = _git("log", "--oneline", "-8").splitlines()
    return ev


def collect_env_presence(ev: RepairEvidence) -> RepairEvidence:
    presence: dict[str, bool] = {}
    for key in _ENV_KEYS:
        presence[f"{key}_PRESENT"] = bool(os.getenv(key))
    # File-based credentials (presence only)
    presence["FIREBASE_ADMIN_PRESENT"] = (ROOT / "firebase-admin.json").exists()
    ev.env_presence = presence
    return ev


def collect_server_smoke(ev: RepairEvidence) -> RepairEvidence:
    """Import the FastAPI app and count routes. Records failure, never raises."""
    try:
        from saathi.server import app
        ev.server_import_ok = True
        ev.route_count = len(app.routes)
    except Exception as exc:  # startup failure is itself evidence
        ev.server_import_ok = False
        ev.stack_trace = (ev.stack_trace or "") + "\n" + redact(repr(exc))
    return ev


def collect_health(ev: RepairEvidence) -> RepairEvidence:
    try:
        from saathi.health import health_check
        h = health_check()
        ev.health_overall = h.get("overall", "")
    except Exception:
        ev.health_overall = "unknown"
    return ev


def collect(base: RepairEvidence | None = None, *, with_server: bool = True) -> RepairEvidence:
    """Full read-only evidence sweep."""
    ev = base or RepairEvidence()
    collect_git_state(ev)
    collect_env_presence(ev)
    if with_server:
        collect_server_smoke(ev)
        collect_health(ev)
    return ev.sanitize()
