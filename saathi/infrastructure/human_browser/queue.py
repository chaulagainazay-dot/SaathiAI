"""Job queue — the transport between the VM (producer) and the Mac Agent (consumer).

The VM enqueues a *signed envelope* (job + signature). The Mac Agent claims it,
verifies, executes, and posts a result. The abstraction is deliberately tiny so
the real transport (an authenticated HTTP endpoint the Mac Agent long-polls, or
Redis/SQS) can drop in without touching callers. `InMemoryQueue` backs tests.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .jobs import HumanJob


@dataclass
class Envelope:
    job: dict           # HumanJob.to_dict()
    signature: str


@dataclass
class JobResult:
    job_id: str
    ok: bool
    data: dict = field(default_factory=dict)
    error: str = ""
    screenshot_b64: str = ""


class JobQueue:
    """Contract. Producer: enqueue / await_result. Consumer: claim / complete."""
    def enqueue(self, env: Envelope) -> str: raise NotImplementedError
    def claim(self) -> Envelope | None: raise NotImplementedError
    def complete(self, result: JobResult) -> None: raise NotImplementedError
    def await_result(self, job_id: str, *, timeout: float = 120) -> JobResult: raise NotImplementedError


class InMemoryQueue(JobQueue):
    def __init__(self):
        self._pending: list[Envelope] = []
        self._results: dict[str, JobResult] = {}

    def enqueue(self, env: Envelope) -> str:
        self._pending.append(env)
        return env.job["id"]

    def claim(self) -> Envelope | None:
        return self._pending.pop(0) if self._pending else None

    def complete(self, result: JobResult) -> None:
        self._results[result.job_id] = result

    def await_result(self, job_id: str, *, timeout: float = 120, poll: float = 0.01) -> JobResult:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if job_id in self._results:
                return self._results.pop(job_id)
            time.sleep(poll)
        return JobResult(job_id=job_id, ok=False, error="timeout waiting for Mac Agent")

    # test/inspection helpers
    def pending_count(self) -> int:
        return len(self._pending)


class HttpQueueClient(JobQueue):
    """Mac Agent side — claims/completes jobs over authenticated HTTP to the VM.
    (The VM's proxy enqueues into an in-process queue that the VM endpoints read.)"""

    def __init__(self, base_url: str, token: str, transport=None, timeout: float = 65):
        self._base = base_url.rstrip("/")
        self._token = token
        self._transport = transport
        self._timeout = timeout

    def _client(self):
        import httpx
        return httpx.Client(timeout=self._timeout, transport=self._transport,
                            base_url=self._base, headers={"x-saathi-token": self._token})

    def claim(self) -> Envelope | None:
        with self._client() as c:
            r = c.get("/api/v1/human/claim")
        if r.status_code == 204 or not r.content:
            return None
        r.raise_for_status()
        d = r.json().get("envelope")
        return Envelope(job=d["job"], signature=d["signature"]) if d else None

    def complete(self, result: JobResult) -> None:
        with self._client() as c:
            c.post("/api/v1/human/complete", json={
                "job_id": result.job_id, "ok": result.ok, "data": result.data,
                "error": result.error, "screenshot_b64": result.screenshot_b64,
            }).raise_for_status()
