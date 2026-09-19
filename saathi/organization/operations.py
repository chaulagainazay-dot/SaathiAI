"""Company operations loop — keeps the AI company working on its standing duties.

One daemon thread. Every ``tick`` it picks the most overdue duty from the
roster (``duties.py``), shows the role as busy for at least ``visible_sec``,
runs the deterministic read-only check, records the result, and schedules the
next run. It shares the organization's single work slot with owner missions,
so there is never more than one unit of work at a time and owner missions
always win. Paused/resumed by the owner; state persists across restarts.

Resource profile: SQLite reads + small file reads; no model inference.
"""
from __future__ import annotations

import os
import threading
import time

from saathi.organization.charter import load_charter
from saathi.organization.duties import DUTIES, run_duty
from saathi.organization.models import BUSY_STATUS_BY_ACTIVITY
from saathi.organization.store import default_store

STATUS_FOR = {"complete": "COMPLETE", "awaiting_evidence": "AWAITING_EVIDENCE", "error": "ERROR"}


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _publish(name: str, payload: dict) -> None:
    try:
        from saathi.events import bus
        bus.publish_sync(f"org.{name}", payload)
    except Exception:
        pass


class OperationsLoop:
    _instance: "OperationsLoop | None" = None
    _lock = threading.Lock()

    def __init__(self, *, tick_sec: float | None = None, visible_sec: float | None = None):
        self.tick = tick_sec if tick_sec is not None else _f("SAATHI_ORG_TICK_SEC", 6.0)
        self.visible = visible_sec if visible_sec is not None else _f("SAATHI_ORG_DUTY_VISIBLE_SEC", 3.0)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.current: dict | None = None
        self.started_at: float | None = None
        self.completed = 0

    @classmethod
    def instance(cls) -> "OperationsLoop":
        with cls._lock:
            if cls._instance is None:
                cls._instance = OperationsLoop()
            return cls._instance

    # ── control ───────────────────────────────────────────────────────────
    @property
    def enabled_by_owner(self) -> bool:
        return default_store().get_setting("operations", "running") == "running"

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def set_running(self, running: bool) -> dict:
        default_store().set_setting("operations", "running" if running else "paused")
        _publish("operations.changed", {"running": running})
        if running:
            self.start()
        return self.status()

    def start(self) -> None:
        if self.alive:
            return
        default_store().reset_running_duties()
        self._stop.clear()
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._loop, name="org-operations", daemon=True)
        self._thread.start()

    def start_if_enabled(self) -> bool:
        if os.environ.get("SAATHI_ORG_OPERATIONS", "1") == "0":
            return False
        if self.enabled_by_owner:
            self.start()
            return True
        return False

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    # ── scheduling ────────────────────────────────────────────────────────
    _req_cache: tuple[float, dict] = (0.0, {})

    def runnable_duties(self) -> list:
        """Roles whose hard requirements are met (unmet → shown UNAVAILABLE, not re-run).
        Availability is re-checked at most once a minute."""
        from saathi.organization import dependencies as deps
        ch = load_charter()
        at, req = OperationsLoop._req_cache
        if time.time() - at > 60 or not req:
            req = deps.check_all({k for r in ch.roles.values() for k in r.requires})
            OperationsLoop._req_cache = (time.time(), req)
        out = []
        for rid in ch.role_order:
            d = DUTIES.get(rid)
            role = ch.roles[rid]
            if d and all(req[k][0] == deps.AVAILABLE for k in role.requires):
                out.append(d)
        return out

    def next_duty(self, now: float | None = None):
        now = now or time.time()
        state = default_store().duties()
        best, best_due = None, None
        for i, d in enumerate(self.runnable_duties()):
            s = state.get(d.role_id)
            due = (s or {}).get("next_due_at") or 0.0
            if not s:  # never run: specialists first (roster order), digests after their teams
                due = (1.0 if d.is_digest else 0.0) * 1e-3 + i * 1e-6
            if due <= now and (best_due is None or due < best_due):
                best, best_due = d, due
        return best

    def run_once(self) -> dict | None:
        """Run the most overdue duty (if any). Returns the recorded result."""
        from saathi.organization import missions
        duty = self.next_duty()
        if duty is None:
            return None
        if not missions._slots.acquire(blocking=False):
            return None                          # an owner mission is running — it wins
        try:
            return self._run(duty)
        finally:
            missions._slots.release()

    def _run(self, duty) -> dict:
        store = default_store()
        role = load_charter().roles[duty.role_id]
        busy = BUSY_STATUS_BY_ACTIVITY[role.activity].value
        store.duty_start(duty.role_id, duty.title)
        with store._conn() as c:
            c.execute("UPDATE org_duty SET status=? WHERE role_id=?", (busy, duty.role_id))
        self.current = {"role_id": duty.role_id, "title": duty.title, "started_at": time.time()}
        store.event("duty.started", role_id=duty.role_id, detail={"title": duty.title})
        _publish("duty.started", {"role_id": duty.role_id, "status": busy})
        t0 = time.time()
        recent = {rid: s["output"] for rid, s in store.duties().items() if s.get("finished_at")}
        out = run_duty(duty, {"recent": recent, "role_id": duty.role_id})
        left = self.visible - (time.time() - t0)
        if left > 0:
            self._stop.wait(left)
        status = STATUS_FOR.get(out.get("status"), "ERROR")
        reason = "; ".join(out.get("gaps", [])[:2]) if status != "COMPLETE" else ""
        store.duty_finish(duty.role_id, status=status, reason=reason[:300], output=out,
                          next_due_at=time.time() + duty.interval_sec)
        store.event("duty.completed", role_id=duty.role_id, detail={"status": status})
        _publish("duty.completed", {"role_id": duty.role_id, "status": status})
        self.current = None
        self.completed += 1
        return {"role_id": duty.role_id, "status": status, "output": out}

    def _loop(self) -> None:
        last_prune = 0.0
        while not self._stop.is_set():
            try:
                if self.enabled_by_owner:
                    self.run_once()
                else:
                    self.current = None
                if time.time() - last_prune > 3600:
                    default_store().prune_events()
                    last_prune = time.time()
            except Exception:
                self.current = None               # never let one bad duty kill the loop
            self._stop.wait(self.tick)

    def status(self) -> dict:
        state = default_store().duties()
        runnable = self.runnable_duties()
        now = time.time()
        upcoming = sorted(((s.get("next_due_at") or 0, rid) for rid, s in state.items()
                           if s.get("finished_at")), key=lambda x: x[0])[:5]
        by = {}
        for s in state.values():
            by[s["status"]] = by.get(s["status"], 0) + 1
        return {
            "running": self.enabled_by_owner and self.alive,
            "owner_setting": "running" if self.enabled_by_owner else "paused",
            "thread_alive": self.alive,
            "current": self.current,
            "tick_sec": self.tick,
            "visible_sec": self.visible,
            "duties_total": len(DUTIES),
            "duties_runnable": len(runnable),
            "duties_run_once": sum(1 for s in state.values() if s.get("runs")),
            "completed_since_start": self.completed,
            "overdue": sum(1 for d in runnable
                           if (state.get(d.role_id) or {}).get("next_due_at", 0) <= now),
            "by_status": by,
            "upcoming": [{"role_id": rid, "due_in_sec": max(0, round(due - now))} for due, rid in upcoming],
            "llm_used": False,
        }
