"""M20.0/M20.4 — JSON engineering store (not a second run ledger / mission DB).

M20.4 adds process-safe file locking, lease ownership helpers, and approvals.
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from saathi.engineering.models import (
    Checkpoint,
    EngineeringBacklogItem,
    EngineeringTask,
    ItemStatus,
    can_transition,
    new_id,
)

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover — non-Unix
    fcntl = None  # type: ignore


class EngineeringStore:
    """File-backed backlog, sessions, checkpoints. Owner: Engineering Orchestrator."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.backlog_path = self.root / "backlog.json"
        self.sessions_path = self.root / "sessions.json"
        self.checkpoints_path = self.root / "checkpoints.json"
        self.approvals_path = self.root / "approvals.json"
        self.history_path = self.root / "history.jsonl"
        self.lock_path = self.root / ".store.lock"
        self._ensure()

    def _ensure(self) -> None:
        if not self.backlog_path.exists():
            self._write_json(self.backlog_path, {"items": {}})
        if not self.sessions_path.exists():
            self._write_json(self.sessions_path, {"sessions": {}})
        if not self.checkpoints_path.exists():
            self._write_json(self.checkpoints_path, {"checkpoints": []})
        if not self.approvals_path.exists():
            self._write_json(self.approvals_path, {"approvals": {}})

    @contextmanager
    def lock(self, *, exclusive: bool = True) -> Iterator[None]:
        """Process-safe coordination for multi-writer hosts."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.lock_path, "a+", encoding="utf-8")
        try:
            if fcntl is not None:
                fcntl.flock(
                    fh.fileno(),
                    fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH,
                )
            yield
        finally:
            try:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            fh.close()

    def _write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # backup previous for corruption recovery
        if path.exists() and path.stat().st_size > 0:
            bak = path.with_suffix(path.suffix + ".bak")
            try:
                bak.write_bytes(path.read_bytes())
            except Exception:
                pass
        tmp = path.with_suffix(".tmp")
        payload = json.dumps(data, indent=2, default=str)
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)

    def _read_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            bak = path.with_suffix(path.suffix + ".bak")
            if bak.exists():
                try:
                    return json.loads(bak.read_text(encoding="utf-8"))
                except Exception:
                    pass
            return {"_corrupt": True, "path": str(path)}

    # ---- backlog ----
    def list_items(self) -> list[EngineeringBacklogItem]:
        data = self._read_json(self.backlog_path)
        return [
            EngineeringBacklogItem.from_dict(v)
            for v in data.get("items", {}).values()
        ]

    def get_item(self, item_id: str) -> EngineeringBacklogItem | None:
        data = self._read_json(self.backlog_path)
        raw = data.get("items", {}).get(item_id)
        return EngineeringBacklogItem.from_dict(raw) if raw else None

    def upsert_item(self, item: EngineeringBacklogItem) -> EngineeringBacklogItem:
        data = self._read_json(self.backlog_path)
        items = data.setdefault("items", {})
        if item.item_id in items:
            prev = EngineeringBacklogItem.from_dict(items[item.item_id])
            if prev.status != item.status and not can_transition(prev.status, item.status):
                raise ValueError(
                    f"invalid_status_transition:{prev.status}->{item.status}"
                )
        elif any(i.get("item_id") == item.item_id for i in items.values()):
            raise ValueError(f"duplicate_id:{item.item_id}")
        # duplicate id check for same id key collision already handled
        for other_id, other in items.items():
            if other_id != item.item_id and other.get("item_id") == item.item_id:
                raise ValueError(f"duplicate_id:{item.item_id}")
        item.updated_at = time.time()
        items[item.item_id] = item.to_dict()
        self._write_json(self.backlog_path, data)
        return item

    def add_item(self, item: EngineeringBacklogItem) -> EngineeringBacklogItem:
        if self.get_item(item.item_id):
            raise ValueError(f"duplicate_id:{item.item_id}")
        return self.upsert_item(item)

    def set_status(self, item_id: str, status: str | ItemStatus) -> EngineeringBacklogItem:
        item = self.get_item(item_id)
        if not item:
            raise KeyError(item_id)
        st = status.value if isinstance(status, ItemStatus) else status
        if not can_transition(item.status, st):
            raise ValueError(f"invalid_status_transition:{item.status}->{st}")
        item.status = st
        return self.upsert_item(item)

    def dependency_ready(self, item: EngineeringBacklogItem) -> tuple[bool, list[str]]:
        missing = []
        for dep in item.dependencies:
            d = self.get_item(dep)
            if not d:
                missing.append(f"missing:{dep}")
            elif d.status != ItemStatus.COMPLETED.value:
                missing.append(f"incomplete:{dep}:{d.status}")
        return (len(missing) == 0, missing)

    # ---- sessions ----
    def put_session(self, session: dict[str, Any]) -> dict[str, Any]:
        with self.lock():
            data = self._read_json(self.sessions_path)
            if data.get("_corrupt"):
                raise RuntimeError("sessions_store_corrupt")
            sessions = data.setdefault("sessions", {})
            sid = session.get("session_id") or new_id("sess")
            session["session_id"] = sid
            session["updated_at"] = time.time()
            # lease ownership
            if "owner_pid" not in session:
                session["owner_pid"] = os.getpid()
            if "lease_until" not in session and session.get("status") in {
                "pending", "starting", "running", "stalled", "awaiting_approval",
            }:
                session["lease_until"] = time.time() + 600
            sessions[sid] = session
            self._write_json(self.sessions_path, data)
            return session

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        data = self._read_json(self.sessions_path)
        if data.get("_corrupt"):
            return None
        return data.get("sessions", {}).get(session_id)

    def list_sessions(self, active_only: bool = False) -> list[dict[str, Any]]:
        data = self._read_json(self.sessions_path)
        if data.get("_corrupt"):
            return []
        out = list(data.get("sessions", {}).values())
        if active_only:
            active = {
                "pending", "starting", "running", "stalled", "awaiting_approval",
                "paused",
            }
            out = [s for s in out if s.get("status") in active]
        return out

    def active_session_count(self) -> int:
        return len(self.list_sessions(active_only=True))

    def reclaim_stale_leases(self, *, now: float | None = None) -> list[str]:
        """Mark sessions with expired leases as terminated (stale-owner recovery)."""
        now = now if now is not None else time.time()
        reclaimed = []
        with self.lock():
            data = self._read_json(self.sessions_path)
            sessions = data.get("sessions") or {}
            for sid, s in list(sessions.items()):
                if s.get("status") not in {
                    "pending", "starting", "running", "stalled", "awaiting_approval", "paused",
                }:
                    continue
                lease = float(s.get("lease_until") or 0)
                if lease and lease < now:
                    s["status"] = "terminated"
                    s["stop_reason"] = "stale_lease"
                    s["updated_at"] = now
                    sessions[sid] = s
                    reclaimed.append(sid)
            if reclaimed:
                self._write_json(self.sessions_path, data)
        return reclaimed

    # ---- approvals (M20.4) ----
    def put_approval(self, approval: dict[str, Any]) -> dict[str, Any]:
        with self.lock():
            data = self._read_json(self.approvals_path)
            if data.get("_corrupt"):
                raise RuntimeError("approvals_store_corrupt")
            apps = data.setdefault("approvals", {})
            aid = approval.get("approval_id") or new_id("appr")
            approval["approval_id"] = aid
            apps[aid] = approval
            self._write_json(self.approvals_path, data)
            return approval

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        data = self._read_json(self.approvals_path)
        if data.get("_corrupt"):
            return None
        return (data.get("approvals") or {}).get(approval_id)

    def list_approvals(self) -> list[dict[str, Any]]:
        data = self._read_json(self.approvals_path)
        if data.get("_corrupt"):
            return []
        return list((data.get("approvals") or {}).values())

    # ---- checkpoints ----
    def add_checkpoint(self, cp: Checkpoint) -> Checkpoint:
        data = self._read_json(self.checkpoints_path)
        cps = data.setdefault("checkpoints", [])
        cps.append(cp.to_dict())
        self._write_json(self.checkpoints_path, data)
        return cp

    def checkpoints_for(self, task_id: str = "", session_id: str = "") -> list[dict]:
        data = self._read_json(self.checkpoints_path)
        out = data.get("checkpoints", [])
        if task_id:
            out = [c for c in out if c.get("task_id") == task_id]
        if session_id:
            out = [c for c in out if c.get("session_id") == session_id]
        return out

    # ---- history ----
    def append_history(self, event: dict[str, Any]) -> None:
        event = dict(event)
        event.setdefault("ts", time.time())
        with self.history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")

    def save_task(self, task: EngineeringTask) -> None:
        path = self.root / "tasks" / f"{task.task_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(task.to_dict(), indent=2), encoding="utf-8")
