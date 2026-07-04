"""VM-side proxy — a HumanBrowser handle that only signs and enqueues jobs.

This is what runs on the server. It implements the HumanBrowser contract but
never launches a browser or holds a cookie: each call becomes a signed HumanJob
on the queue, and it waits for the Mac Agent's result. Personal sessions stay
off the VM.
"""
from __future__ import annotations

import os

from .driver import HumanBrowser
from .jobs import HumanJob, sign, JobError
from .queue import Envelope, JobQueue


class HumanBrowserProxy(HumanBrowser):
    def __init__(self, queue: JobQueue, *, secret: str | None = None, timeout: float = 180):
        self._q = queue
        self._secret = secret if secret is not None else os.getenv("HUMAN_BROWSER_SECRET", "")
        self._timeout = timeout

    def available(self) -> bool:
        # usable only if we can sign jobs and have a queue to reach the agent
        return bool(self._secret) and self._q is not None

    def execute(self, capability: str, *, profile: str = "", **payload) -> dict:
        if not self._secret:
            raise JobError("HUMAN_BROWSER_SECRET not set — cannot sign jobs")
        job = HumanJob(capability=capability, payload=payload, profile=profile)
        env = Envelope(job=job.to_dict(), signature=sign(job, self._secret))
        self._q.enqueue(env)
        result = self._q.await_result(job.id, timeout=self._timeout)
        if not result.ok:
            raise JobError(f"human-browser job failed: {result.error}")
        out = dict(result.data)
        if result.screenshot_b64:
            out["screenshot_b64"] = result.screenshot_b64
        return out
