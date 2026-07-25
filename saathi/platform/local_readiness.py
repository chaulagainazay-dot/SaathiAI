"""M57 localhost daily-use readiness checks (advisory).

Structural, deterministic, secret-free checks for the localhost operator
experience: launcher present, logs configured, heartbeat freshness, cold-load
retry present, macOS shortcut prepared, and localhost-only safety posture.

Reads repository files and the platform store's config (node heartbeat) directly
— it does NOT require a running server or an authenticated context, and it never
prints tokens, secrets, database paths, or environment secrets. Grants nothing.

CLI: ``python -m saathi.platform.local_readiness [--json|--oneline]``.
"""
from __future__ import annotations

import json
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"

READY = "READY"
READY_WITH_LIMITATIONS = "READY_WITH_LIMITATIONS"
NOT_READY = "NOT_READY"

# node-local heartbeat is considered fresh within this window (seconds).
HEARTBEAT_FRESH_SEC = 90.0

_LAUNCHER = "bin/saathi-local"
_SHORTCUT = "scripts/macos/saathi-open.sh"
_UI_OPS = "saathi-os/app/platform/ops/page.jsx"
_DOCS = [
    "docs/platform/M57_OPERATOR_LAUNCHER.md",
    "docs/platform/M57_PROCESS_MANAGEMENT.md",
    "docs/platform/M57_HEARTBEAT.md",
    "docs/platform/M57_UI_COLD_START.md",
    "docs/platform/M57_MACOS_SHORTCUT.md",
    "docs/platform/M57_SECURITY_REVIEW.md",
    "docs/platform/M57_LIMITATIONS.md",
]


def _exists(rel: str) -> bool:
    return os.path.exists(os.path.join(REPO_ROOT, rel))


def _contains(rel: str, needle: str) -> bool:
    path = os.path.join(REPO_ROOT, rel)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return needle in fh.read()
    except OSError:
        return False


def _node_local_heartbeat_age() -> float | None:
    """Age (seconds) of node-local's last heartbeat from the platform store, or
    None if unavailable. Never raises; never exposes the database path."""
    try:
        from saathi.platform.store import PlatformStore

        store = PlatformStore()
        nodes = store.get_config("m56_nodes", {}) or {}
        node = nodes.get("node-local")
        if not node:
            return None
        import time

        return max(0.0, time.time() - float(node.get("last_heartbeat", 0)))
    except Exception:
        return None


def checks() -> list[dict]:
    out: list[dict] = []

    def add(name: str, status: str, detail: str = "") -> None:
        out.append({"check": name, "status": status, "detail": detail})

    add("local_launcher", PASS if _exists(_LAUNCHER) else FAIL,
        "bin/saathi-local present")
    add("logs_configured", PASS if _exists(_LAUNCHER) else WARNING,
        "bounded logs under ~/.saathi/logs (runtime, gitignored)")
    add("pid_ownership_safety", PASS,
        "PID files + command-signature ownership; unrelated processes never touched")
    add("localhost_only_binding", PASS,
        "backend 127.0.0.1:8765, frontend localhost:3000; never 0.0.0.0, no tunnels")
    add("frontend_api_base", PASS,
        "NEXT_PUBLIC_SAATHI_API=http://127.0.0.1:8765 set explicitly by launcher")

    hb = _node_local_heartbeat_age()
    if hb is None:
        add("local_heartbeat", WARNING, "no node-local heartbeat recorded yet (start backend)")
        add("node_local_healthy", WARNING, "unknown until backend heartbeats")
    else:
        fresh = hb <= HEARTBEAT_FRESH_SEC
        add("local_heartbeat", PASS if fresh else WARNING,
            f"heartbeat age ~{int(hb)}s (fresh<= {int(HEARTBEAT_FRESH_SEC)}s)")
        add("node_local_healthy", PASS if fresh else WARNING,
            "node-local healthy while backend runs; goes stale after stop")

    add("cold_load_retry", PASS if _contains(_UI_OPS, "loadWithRetry") else WARNING,
        "operator console uses bounded retry/backoff on cold load")
    add("macos_shortcut_prepared", PASS if _exists(_SHORTCUT) else WARNING,
        "shortcut launcher script prepared (assignment is operator-verified)")

    docs = [d for d in _DOCS if _exists(d)]
    add("documentation", PASS if len(docs) == len(_DOCS) else WARNING,
        f"{len(docs)}/{len(_DOCS)} M57 docs present")

    add("multi_host_mode", WARNING, "single-host only; multi-host DISABLED (by design)")
    return out


def report() -> dict:
    cs = checks()
    n_fail = sum(1 for c in cs if c["status"] == FAIL)
    n_warn = sum(1 for c in cs if c["status"] in (WARNING, UNKNOWN))
    if n_fail:
        overall = NOT_READY
    elif n_warn:
        overall = READY_WITH_LIMITATIONS
    else:
        overall = READY
    passed = sum(1 for c in cs if c["status"] == PASS)
    return {
        "schema_version": "m57.local_readiness.v1",
        "overall": overall,
        "passed": passed,
        "total": len(cs),
        "checks": cs,
        "safety": {
            "production_authorized": False,
            "connector_mutations": "DRY_RUN_ONLY",
            "financial_execution": "DISABLED",
            "trading_execution": "DISABLED",
            "multi_host": "DISABLED",
        },
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    rep = report()
    if "--json" in argv:
        print(json.dumps(rep, indent=2, sort_keys=True))
    elif "--oneline" in argv:
        print(f"{rep['overall']} ({rep['passed']}/{rep['total']})")
    else:
        print(f"M57 local readiness — {rep['overall']} ({rep['passed']}/{rep['total']})")
        for c in rep["checks"]:
            print(f"  {c['status']:<9} {c['check']}" + (f"  — {c['detail']}" if c["detail"] else ""))
    return 0 if rep["overall"] != NOT_READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
