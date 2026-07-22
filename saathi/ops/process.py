"""M13.5 process/status — safe backend status + stale-process detection.

Never kills unknown processes. `status` reports whether a backend is listening
and, if reachable, whether its running commit matches the working tree — the
stale-backend failure M11 hit. Termination requires clear ownership evidence
and is left to the operator (documented in the runbook), not automated here.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PORT = 8765


def _listeners(port: int) -> list[int]:
    try:
        out = subprocess.run(["lsof", "-iTCP", f"-sTCP:LISTEN", "-P", "-n"],
                             capture_output=True, text=True, timeout=5).stdout
        pids = []
        for ln in out.splitlines():
            if f":{port}" in ln:
                parts = ln.split()
                if len(parts) > 1 and parts[1].isdigit():
                    pids.append(int(parts[1]))
        return sorted(set(pids))
    except Exception:
        return []


def working_tree_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        return "unknown"


def backend_status(port: int = DEFAULT_PORT) -> dict:
    pids = _listeners(port)
    result = {"port": port, "listening": bool(pids), "pids": pids,
              "duplicate": len(pids) > 1, "working_tree_commit": working_tree_commit()}
    if pids:
        # try to read the running backend's reported commit (stale detection)
        try:
            import httpx
            import os
            headers = {}
            tok = os.getenv("SAATHI_TOKEN")
            if tok:
                headers["x-saathi-token"] = tok
            r = httpx.get(f"http://127.0.0.1:{port}/api/v1/system/version",
                         headers=headers, timeout=3)
            if r.status_code == 200:
                running = r.json().get("commit", "unknown")
                result["running_commit"] = running
                result["stale"] = (running != result["working_tree_commit"]
                                   and running != "unknown")
        except Exception:
            result["running_commit"] = "unreachable"
    return result
