"""System Status for the Company View — real probes only, cached briefly.

Each row: ``{system_id, name, status, detail, source, checked_at}`` with status
``OK | DEGRADED | DOWN | NOT_CONNECTED | UNKNOWN``. No percentages are
reported: nothing measures availability as a percentage. A probe that raises
yields UNKNOWN with the exception type, never a green light.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_TTL_SEC = 30.0
_lock = threading.Lock()
_cache: dict = {"at": 0.0, "value": None}


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)


def _agent_runtime() -> tuple[str, str]:
    from saathi.agent_runtime.store import DB_PATH
    if not Path(DB_PATH).exists():
        return "UNKNOWN", "Agent runtime store not initialised"
    with _ro(Path(DB_PATH)) as c:
        total = c.execute("SELECT COUNT(*) FROM orchestration_run").fetchone()[0]
        running = c.execute("SELECT COUNT(*) FROM agent_run WHERE state='running'").fetchone()[0]
    return "OK", f"{total} runs recorded · {running} agent turn(s) running"


def _platform_db() -> tuple[str, str]:
    env = os.environ.get("SAATHI_PLATFORM_DB")
    p = Path(env) if env else ROOT / "data" / "platform" / "platform.db"
    if not p.exists():
        return "DOWN", "platform.db not found"
    with _ro(p) as c:
        c.execute("SELECT 1").fetchone()
        n = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    return "OK", f"platform.db readable · {n} tables"


def _organization() -> tuple[str, str]:
    from saathi.organization.store import default_store
    st = default_store()
    active = len(st.active_missions())
    return "OK", f"{active} organization mission(s) active"


def _research() -> tuple[str, str]:
    from saathi import research_surface
    h = research_surface.health()
    src = h.get("source_health") or {}
    avail = [k for k, v in src.items() if (v or {}).get("status") == "AVAILABLE"]
    unknown = [k for k, v in src.items() if (v or {}).get("status") not in ("AVAILABLE",)]
    status = "OK" if avail and not unknown else ("DEGRADED" if avail else "UNKNOWN")
    return status, (f"{h.get('events', 0)} research events · sources available: "
                    f"{', '.join(avail) or 'none'}" + (f" · unknown: {', '.join(unknown)}" if unknown else ""))


def _trading_guardian() -> tuple[str, str]:
    from saathi.platform.tg.service import default_tg_service
    p = default_tg_service().posture()
    if p.get("paper_only") is True and not p.get("live_trading_authorized"):
        return "OK", f"PAPER-ONLY · live disabled · mode {p.get('authority_mode')}"
    return "DEGRADED", "Posture is not paper-only — investigate"


def _execution_gateway() -> tuple[str, str]:
    from saathi.execution.universal import default_boundary
    m = default_boundary().metrics()
    failed = int(m.get("failed", 0) or 0)
    return ("DEGRADED" if failed else "OK",
            f"running {m.get('running', 0)} · queued {m.get('queued', 0)} · "
            f"denied {m.get('denied', 0)} · failed {failed} (this process)")


def _models() -> tuple[str, str]:
    from saathi.m20_console.status import inference_control_center_facet
    f = inference_control_center_facet()
    running = sorted({e.get("engine_id") for e in f.get("engines", []) if e.get("running")})
    gw = "on" if f.get("gateway_enabled") else "off"
    if not running:
        return "DOWN", f"No local inference engine running · governed gateway {gw}"
    return "OK", (f"{', '.join(running)} running · {f.get('models_installed_count', 0)} models · "
                  f"governed gateway {gw} · {f.get('hardware_available_gb', '?')} GB free")


def _external() -> tuple[str, str]:
    from saathi.connectors.platform.health import platform_health
    h = platform_health()
    live = [c for c in h["connectors"] if c.get("status") in ("healthy", "live-tested")]
    blocked = [c for c in h["connectors"] if not c.get("credential_present") and not c.get("local")]
    status = "OK" if not blocked else "NOT_CONNECTED" if not live else "DEGRADED"
    return status, f"{len(live)} connector(s) live · {len(blocked)} not connected (no credential)"


SYSTEMS: tuple[tuple[str, str, Callable[[], tuple[str, str]]], ...] = (
    ("agent_runtime", "Agent Runtime", _agent_runtime),
    ("organization", "Organization Store", _organization),
    ("database", "Platform Database", _platform_db),
    ("research", "Research Engine", _research),
    ("trading_guardian", "Trading Guardian", _trading_guardian),
    ("execution_gateway", "Execution Gateway", _execution_gateway),
    ("models", "Model Services", _models),
    ("external", "External APIs", _external),
)


def _probe(system_id: str, name: str, fn) -> dict:
    t = time.time()
    try:
        status, detail = fn()
    except Exception as exc:
        status, detail = "UNKNOWN", f"probe failed: {type(exc).__name__}"
    return {"system_id": system_id, "name": name, "status": status, "detail": detail,
            "checked_at": t, "latency_ms": round((time.time() - t) * 1000, 1)}


def system_status(*, force: bool = False) -> dict:
    now = time.time()
    with _lock:
        if not force and _cache["value"] and now - _cache["at"] < CACHE_TTL_SEC:
            return _cache["value"]
        rows = [_probe(sid, name, fn) for sid, name, fn in SYSTEMS]
        worst = "OK"
        for r in rows:
            if r["status"] in ("DOWN",):
                worst = "DOWN"
            elif r["status"] in ("DEGRADED", "UNKNOWN") and worst == "OK":
                worst = "DEGRADED"
        value = {"overall": worst, "systems": rows, "generated_at": now,
                 "cache_ttl_sec": CACHE_TTL_SEC}
        _cache.update(at=now, value=value)
        return value
