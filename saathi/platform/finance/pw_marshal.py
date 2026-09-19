"""Executor-bound read-only proxies for a Playwright Page/Locator.

`FinancialBrowserRuntimeManager.live_page()` returns a `MarshalledPage` instead of the raw
Playwright page. Every attribute the read-only observer touches (`.url`, `.locator(...)`,
`.count()`, `.first`, `.nth()`, `.inner_text()`) is executed on the single Playwright
executor thread and only primitives cross back. This lets the FROZEN observation bridge and
the deterministic observer run unchanged against a real page while respecting Playwright's
thread affinity. These proxies expose ONLY read methods — no click/type/goto/eval — so they
add no interaction surface.
"""
from __future__ import annotations

from typing import Any, Callable


class _MarshalledLocator:
    def __init__(self, executor, make: Callable[[], Any]):
        # `make` builds the underlying Locator ON the executor thread when needed.
        self._exec = executor
        self._make = make

    def count(self) -> int:
        return int(self._exec.submit(lambda: self._make().count()))

    def inner_text(self) -> str:
        return str(self._exec.submit(lambda: self._make().inner_text()))

    @property
    def first(self) -> "_MarshalledLocator":
        parent = self._make
        return _MarshalledLocator(self._exec, lambda: parent().first)

    def nth(self, i: int) -> "_MarshalledLocator":
        parent = self._make
        return _MarshalledLocator(self._exec, lambda: parent().nth(i))

    def locator(self, selector: str) -> "_MarshalledLocator":
        parent = self._make
        return _MarshalledLocator(self._exec, lambda: parent().locator(selector))


class MarshalledPage:
    """Read-only, executor-bound view of a live Playwright page."""

    def __init__(self, executor, page):
        self._exec = executor
        self._page = page

    @property
    def url(self) -> str:
        try:
            return str(self._exec.submit(lambda: self._page.url))
        except Exception:
            return ""

    def locator(self, selector: str) -> _MarshalledLocator:
        return _MarshalledLocator(self._exec, lambda: self._page.locator(selector))
