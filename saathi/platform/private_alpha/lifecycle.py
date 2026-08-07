"""M159 — Lifecycle ownership helpers (delegates to bin/saathi-local).

Does not implement a second process manager. Encodes safety contracts used by
tests and doctor: localhost-only, PID ownership, refuse unrelated kills.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
LAUNCHER = ROOT / "bin" / "saathi-local"
ALPHA_CLI = ROOT / "bin" / "saathi-alpha"

BACKEND_SIG = re.compile(r"uvicorn\s+saathi\.server:app|-m\s+saathi\.server")
FRONTEND_SIG = re.compile(r"next(-server|\s+dev)")


def launcher_source() -> str:
    return LAUNCHER.read_text(encoding="utf-8") if LAUNCHER.is_file() else ""


def safety_contract() -> dict[str, Any]:
    src = launcher_source()
    return {
        "launcher": str(LAUNCHER.relative_to(ROOT)) if LAUNCHER.is_file() else None,
        "exists": LAUNCHER.is_file(),
        "executable": os.access(LAUNCHER, os.X_OK) if LAUNCHER.is_file() else False,
        "localhost_only": 'BFF_HOST="127.0.0.1"' in src and "--host 0.0.0.0" not in src,
        "refuses_unrelated_kill": "refusing to kill" in src or "UNRELATED" in src,
        "uses_pid_files": "BACKEND_PID" in src and "FRONTEND_PID" in src,
        "command_signature_check": "_is_saathi" in src and "_owned" in src,
        "no_broad_pkill": "pkill" not in src and "killall" not in src,
        "subcommands": [
            "start",
            "stop",
            "restart",
            "status",
            "doctor",
            "open",
            "logs",
        ],
        "production_authorized": False,
    }


def is_saathi_backend_cmd(cmd: str) -> bool:
    return bool(BACKEND_SIG.search(cmd or ""))


def is_saathi_frontend_cmd(cmd: str) -> bool:
    return bool(FRONTEND_SIG.search(cmd or ""))


def may_terminate(pid: int, role: str, *, pidfile_pid: int | None, cmd: str) -> dict[str, Any]:
    """Fail-closed ownership decision. Never recommends killing unrelated PIDs."""
    role = (role or "").lower()
    owned_sig = (
        is_saathi_backend_cmd(cmd)
        if role == "backend"
        else is_saathi_frontend_cmd(cmd)
        if role == "frontend"
        else False
    )
    pidfile_match = pidfile_pid is not None and int(pidfile_pid) == int(pid)
    allowed = bool(owned_sig and pidfile_match)
    return {
        "pid": pid,
        "role": role,
        "signature_match": owned_sig,
        "pidfile_match": pidfile_match,
        "may_terminate": allowed,
        "reason": (
            "launcher-owned SaathiOS process"
            if allowed
            else "refused: ownership ambiguous or unrelated (fail-closed)"
        ),
    }


def run_launcher(subcommand: str, *args: str, timeout: int = 120) -> dict[str, Any]:
    """Invoke bin/saathi-local for real lifecycle operations."""
    if not LAUNCHER.is_file():
        return {"ok": False, "error": "LAUNCHER_MISSING"}
    cmd = [str(LAUNCHER), subcommand, *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-4000:],
            "stderr": (proc.stderr or "")[-2000:],
            "command": [subcommand, *args],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "TIMEOUT", "command": [subcommand, *args]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}
