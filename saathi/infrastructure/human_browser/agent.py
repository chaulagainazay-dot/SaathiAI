"""Mac Agent — runs on the trusted machine; the ONLY thing that touches Chrome.

Claims signed jobs, verifies them (signature + expiry + replay), and dispatches
to a HumanBrowser backend driving your real, logged-in Chrome profiles. Rejects
anything it can't cryptographically trust — a compromised VM can still only
enqueue jobs signed with the shared secret, never drive the browser directly.
"""
from __future__ import annotations

import os

from .driver import HumanBrowser
from .jobs import HumanJob, verify, NonceStore, JobError
from .queue import JobQueue, JobResult


class MacAgent:
    def __init__(self, queue: JobQueue, backend: HumanBrowser, *,
                 secret: str | None = None, nonces: NonceStore | None = None):
        self._q = queue
        self._backend = backend
        self._secret = secret if secret is not None else os.getenv("HUMAN_BROWSER_SECRET", "")
        self._nonces = nonces if nonces is not None else NonceStore()

    def run_once(self) -> JobResult | None:
        """Process at most one job. Returns the result, or None if idle."""
        env = self._q.claim()
        if env is None:
            return None
        job = HumanJob.from_dict(env.job)
        # 1. verify trust BEFORE doing anything with the payload
        try:
            verify(job, env.signature, self._secret, nonces=self._nonces)
        except JobError as e:
            result = JobResult(job_id=job.id, ok=False, error=f"rejected: {e}")
            self._q.complete(result)
            return result
        # 2. execute against the real browser
        try:
            data = self._backend.execute(job.capability, profile=job.profile, **job.payload)
            result = JobResult(job_id=job.id, ok=True,
                               data=data if isinstance(data, dict) else {"result": data},
                               screenshot_b64=(data or {}).get("screenshot_b64", "") if isinstance(data, dict) else "")
        except Exception as e:
            result = JobResult(job_id=job.id, ok=False, error=f"{type(e).__name__}: {e}")
        self._q.complete(result)
        return result

    def run_forever(self, *, idle_sleep: float = 0.5) -> None:  # pragma: no cover
        import time
        while True:
            if self.run_once() is None:
                time.sleep(idle_sleep)
