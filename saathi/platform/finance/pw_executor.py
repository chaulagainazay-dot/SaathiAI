"""Single-thread Playwright executor.

Playwright's SYNC objects (playwright / browser / context / page / CDP session) are
bound to the OS thread that created them — they cannot be touched from another thread.
FastAPI runs sync route handlers across an anyio threadpool, so a persistent, owner-
controlled headed browser (and a continuous CDP screencast) must live on ONE long-lived
thread with every operation marshalled onto it.

This executor owns that thread. `sync_playwright().start()` runs on it; every browser
operation is submitted as a callable and executed there, results/exceptions returned to
the caller. It carries no financial authority and no page-specific logic — it is pure
thread affinity. Nothing here clicks/types/observes; callers pass the callables.
"""
from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import Future
from typing import Any, Callable


class PlaywrightExecutor:
    """A daemon thread that owns the Playwright sync driver. Lazy: the thread starts on
    first submit. All Playwright object access must go through `submit`/`call`."""

    def __init__(self):
        self._q: "queue.Queue[tuple[Callable, Future]]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._pw = None                      # the sync_playwright() handle, created on-thread
        self._stopped = False

    # ── lifecycle ───────────────────────────────────────────────────────────────
    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stopped = False
            self._thread = threading.Thread(target=self._run, name="pw-executor", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while True:
            try:
                fn, fut = self._q.get()
            except Exception:
                continue
            if fn is None:                    # shutdown sentinel
                # stop playwright on its own thread, then exit
                if self._pw is not None:
                    try:
                        self._pw.stop()
                    except Exception:
                        pass
                    self._pw = None
                if fut is not None:
                    fut.set_result(True)
                return
            try:
                fut.set_result(fn())
            except Exception as e:            # marshal the exception back to the caller
                fut.set_exception(e)

    def submit(self, fn: Callable[[], Any], *, timeout: float = 30.0) -> Any:
        """Run fn() on the executor thread; block for the result (or raise its exception)."""
        self._ensure_thread()
        fut: Future = Future()
        self._q.put((fn, fut))
        return fut.result(timeout=timeout)

    def playwright(self):
        """The sync Playwright handle, started on the executor thread (created once)."""
        return self.submit(self.pw_onthread, timeout=60.0)

    def pw_onthread(self):
        """Sync Playwright handle — created on first use. MUST be called only from inside a
        callable already running on the executor thread (never via submit-within-submit)."""
        if self._pw is None:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
        return self._pw

    def stop(self, *, timeout: float = 10.0) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._pw = None
                return
        fut: Future = Future()
        self._q.put((None, fut))
        try:
            fut.result(timeout=timeout)
        except Exception:
            pass

    @property
    def alive(self) -> bool:
        t = self._thread
        return bool(t and t.is_alive())
