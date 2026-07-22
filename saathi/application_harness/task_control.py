"""M17.8 governed long-running harness task control.

Owns the lifecycle of a long-running harness process WITHOUT introducing a second
execution engine: every task still runs through the one ApplicationHarnessAdapter
boundary. Adds cooperative cancellation, orphan-free process-group kill (inherited
from the adapter's start_new_session + killpg), and a durable run journal with
boot-time crash reconciliation.

Ownership is enforced before anything is spawned — a caller may only launch/cancel
its own run — so cross-user cancellation or task hijacking is blocked at this
layer, above the adapter's own ownership/trust gates.
"""
from __future__ import annotations

import threading

from saathi.application_harness.adapter import ApplicationHarnessAdapter, HarnessResult
from saathi.application_harness.models import HarnessDefinition, HarnessActionIntent
from saathi.application_harness.run_journal import RunJournal


class CancelToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


class TaskHandle:
    def __init__(self, run_id: str, owner: str):
        self.run_id = run_id
        self.owner = owner
        self.token = CancelToken()
        self._thread: threading.Thread | None = None
        self._result: HarnessResult | None = None

    def join(self, timeout: float | None = None) -> HarnessResult | None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        return self._result


class HarnessTaskController:
    """One controller per process; tracks in-flight runs so they can be
    cancelled by id and reconciled after a crash."""

    def __init__(self, journal: RunJournal | None = None,
                 adapter: ApplicationHarnessAdapter | None = None):
        self.journal = journal or RunJournal()
        self._adapter = adapter or ApplicationHarnessAdapter()
        self._active: dict[str, TaskHandle] = {}
        self._lock = threading.Lock()

    def launch(self, *, run_id: str, defn: HarnessDefinition,
               intent: HarnessActionIntent, argv: list, work_dir: str,
               file_roots: list, owner: str, timeout: float = 60.0,
               limits=None) -> TaskHandle:
        handle = TaskHandle(run_id, owner)
        # ownership gate BEFORE spawning — never run another user's task.
        if intent.user_id != owner:
            handle._result = HarnessResult(
                "blocked", None, "", "", 0.0,
                error_code="HARNESS_PERMISSION_BLOCKED:ownership")
            return handle

        def _run():
            res = self._adapter.run(
                defn=defn, intent=intent, argv=argv, work_dir=work_dir,
                file_roots=file_roots, timeout=timeout, limits=limits,
                cancel_token=handle.token, run_id=run_id, journal=self.journal)
            handle._result = res
            with self._lock:
                self._active.pop(run_id, None)

        t = threading.Thread(target=_run, name=f"harness-task-{run_id}", daemon=True)
        handle._thread = t
        with self._lock:
            self._active[run_id] = handle
        t.start()
        return handle

    def cancel(self, run_id: str, *, requester: str) -> dict:
        with self._lock:
            handle = self._active.get(run_id)
        if handle is None:
            return {"cancelled": False, "reason": "unknown_or_finished"}
        if requester != handle.owner:
            return {"cancelled": False, "reason": "HARNESS_PERMISSION_BLOCKED:ownership"}
        handle.token.cancel()
        return {"cancelled": True, "run_id": run_id}

    def active_ids(self) -> list[str]:
        with self._lock:
            return list(self._active)

    def reconcile_on_boot(self) -> list[str]:
        """Detect runs interrupted by a crash (journal 'running' with a dead PID)
        and record them as crash_recovered. Returns reconciled run ids."""
        return self.journal.reconcile()
