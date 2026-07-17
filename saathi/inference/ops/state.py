"""M26 — Atomic operational state store (JSON files)."""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATE_DIR = ROOT / "docs" / "evidence" / "m26"
SCHEMA = "m26.ops_state.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def atomic_write_json(path: Path, payload: dict[str, Any], *, mode: int = 0o600) -> None:
    """Atomic JSON write; refuses to follow symlinks for the final path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise OSError(f"refusing to write through symlink: {path}")
    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex[:8]}.tmp")
    data = json.dumps(payload, indent=2, default=str) + "\n"
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    try:
        os.write(fd, data.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def load_json(path: Path) -> Optional[dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        if path.is_symlink():
            return None
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


class OpsStateStore:
    """Thread-safe ops state under an isolated directory."""

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
        self.state_path = self.state_dir / "ops_state.json"
        self.incidents_path = self.state_dir / "incidents.json"
        self.events_path = self.state_dir / "ops_events.jsonl"
        self.mode_history_path = self.state_dir / "mode_history.jsonl"
        self._lock = threading.RLock()

    def default_state(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "service_id": "",
            "owner_token": "",
            "phase": "STOPPED",
            "rollout_mode": "OFF",
            "provider_state": "STOPPED",
            "started_at": None,
            "stopped_at": None,
            "drain_started_at": None,
            "drain_deadline_at": None,
            "active_requests": 0,
            "queued_requests": 0,
            "max_concurrent": 1,
            "canary_percent": 10,
            "canary_allowlist": [],
            "idle_unload_enabled": False,
            "cooldown_until": None,
            "failure_window": [],
            "last_error": "",
            "updated_at": _utc_now(),
            "privacy_safe": True,
            "owns_external_provider_process": False,
            "cloud_fallback": False,
            "trading_guardian": "UNCHANGED_UNENGAGED",
        }

    def load(self) -> dict[str, Any]:
        with self._lock:
            data = load_json(self.state_path)
            if not data:
                return self.default_state()
            base = self.default_state()
            base.update(data)
            return base

    def save(self, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = dict(state)
            state["schema"] = SCHEMA
            state["updated_at"] = _utc_now()
            state["privacy_safe"] = True
            state["owns_external_provider_process"] = False
            state["cloud_fallback"] = False
            state["trading_guardian"] = "UNCHANGED_UNENGAGED"
            atomic_write_json(self.state_path, state)
            return state

    def update(self, **kwargs: Any) -> dict[str, Any]:
        with self._lock:
            st = self.load()
            st.update(kwargs)
            return self.save(st)

    def load_incidents(self) -> list[dict[str, Any]]:
        with self._lock:
            data = load_json(self.incidents_path)
            if not data:
                return []
            return list(data.get("incidents") or [])

    def save_incidents(self, incidents: list[dict[str, Any]]) -> None:
        with self._lock:
            atomic_write_json(
                self.incidents_path,
                {
                    "schema": "m26.incidents.v1",
                    "updated_at": _utc_now(),
                    "incidents": incidents,
                    "privacy_safe": True,
                },
            )

    def append_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            line = json.dumps(event, default=str) + "\n"
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(line)

    def append_mode_history(self, record: dict[str, Any]) -> None:
        with self._lock:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            line = json.dumps(record, default=str) + "\n"
            with open(self.mode_history_path, "a", encoding="utf-8") as f:
                f.write(line)
