"""Phase 6 — BrowserResearchProvider over the EXISTING GovernedBrowser.

No browser-use, no second browser framework, no second permission system. All
acquisition is a governed READ through ``saathi.browser.GovernedBrowser``, which
already enforces domain policy, SSRF blocking, prompt-injection detection, and
the ExecutionGateway browser boundary. This provider only bounds resources and
normalizes the safe result into a ``FetchedPage``.
"""
from __future__ import annotations

import time

from saathi.browser_research.contract import BrowserResearchProvider, FetchedPage

# Governed record statuses we treat as a clean read vs an explicit denial.
_SUCCEEDED = "succeeded"
_DENIED = "denied"


class GovernedBrowserResearchProvider(BrowserResearchProvider):
    def __init__(
        self,
        *,
        allowed_hosts: list[str] | tuple[str, ...],
        mode: str = "service",
        governed_browser=None,
        max_pages: int = 6,
        max_runtime_sec: float = 90.0,
        workspace=None,
        environment: str = "dev",
    ):
        self.allowed_hosts = list(allowed_hosts)
        self.max_pages = int(max_pages)
        self.max_runtime_sec = float(max_runtime_sec)
        self.environment = environment
        self._pages_fetched = 0
        self._started = time.time()
        self._closed = False
        if governed_browser is not None:
            self._gb = governed_browser
        else:
            from saathi.browser.governed import GovernedBrowser
            self._gb = GovernedBrowser(
                mode=mode, allowed_hosts=self.allowed_hosts, workspace=workspace,
            )

    @property
    def pages_fetched(self) -> int:
        return self._pages_fetched

    def fetch(self, url: str, *, mission_id: str, actor: str = "user:owner",
              selector: str = "", timeout: int = 30) -> FetchedPage:
        if self._closed:
            raise RuntimeError("provider closed; start a new mission")
        # Resource bound: cap pages per mission (Phase 14).
        if self._pages_fetched >= self.max_pages:
            return FetchedPage(url=url, final_origin="", title="", content="",
                               status="blocked", error_category="max_pages_exceeded")
        # Runtime bound: refuse to start a fetch once the mission budget is spent.
        if (time.time() - self._started) > self.max_runtime_sec:
            return FetchedPage(url=url, final_origin="", title="", content="",
                               status="blocked", error_category="max_runtime_exceeded")

        # Always a governed READ — the only action path that stashes the body for
        # out-of-band collection. Never open/navigate (no body), never a mutation.
        # force_new: research reads are repeatable and must not collide with a
        # prior identical governed read via idempotency dedup.
        rec = self._gb.execute(
            action="read", url=url, actor=actor, selector=selector,
            mission_id=mission_id, request_source="api",
            environment=self.environment, force_new=True,
        )
        self._pages_fetched += 1

        status = getattr(rec, "status", "failed")
        exec_id = getattr(rec, "execution_id", "") or ""
        body = self._gb.take_content(exec_id) or {}

        if status == _SUCCEEDED:
            norm = "succeeded"
        elif status == _DENIED:
            norm = "denied"
        else:
            norm = "failed"

        return FetchedPage(
            url=url,
            final_origin=str(body.get("final_origin") or ""),
            title=str(body.get("page_title") or ""),
            content=str(body.get("content") or ""),
            status=norm,
            injection_hits=tuple(body.get("injection_hits") or ()),
            retrieval_ts=time.time(),
            error_category=("" if norm == "succeeded" else str(getattr(rec, "failure_category", "") or norm)),
        )

    def cleanup(self) -> dict:
        """Shut the browser down after the mission and prove cleanup (Phase 14)."""
        method = "noop"
        try:
            svc = getattr(self._gb.adapter, "_service", None)
            if svc is not None:
                for name in ("close", "shutdown", "stop", "dispose"):
                    fn = getattr(svc, name, None)
                    if callable(fn):
                        fn()
                        method = name
                        break
                self._gb.adapter._service = None
        except Exception as e:  # cleanup must never raise
            method = f"error:{type(e).__name__}"
        self._closed = True
        return {
            "closed": True,
            "method": method,
            "pages_fetched": self._pages_fetched,
            "runtime_sec": round(time.time() - self._started, 3),
        }
