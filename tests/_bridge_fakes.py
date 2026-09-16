"""Shared fakes for the Observation Bridge tests: a Playwright-shaped read-only fake page
(no real browser, no credentials) and a manager seeder. Used both in-process and by the
subprocess server in the process-boundary test."""
from __future__ import annotations

from saathi.platform.finance.browser_runtime import RuntimeState
from saathi.platform.finance.observer import TMSBrowserPortfolioObserver
from saathi.platform.finance.policy import Provider


class _Cell:
    def __init__(self, text):
        self._t = text

    def count(self):
        return 1 if self._t is not None else 0

    def inner_text(self):
        return "" if self._t is None else str(self._t)


class _Loc:
    def __init__(self, elems):
        self._e = list(elems)

    def count(self):
        return len(self._e)

    @property
    def first(self):
        return self._e[0] if self._e else _Cell(None)

    def nth(self, i):
        return self._e[i]

    def inner_text(self):
        return self._e[0].inner_text() if self._e else ""


class _Row:
    def __init__(self, cells: dict):
        self._cells = cells

    def locator(self, sel):
        t = self._cells.get(sel)
        return _Loc([_Cell(t)]) if t is not None else _Loc([])


class FakePage:
    """Read-only Playwright-shaped page. Exposes `.url` and `.locator(sel)` only — the same
    surface ReadOnlyPageReader consumes. No click/type/goto/evaluate."""

    def __init__(self, url: str, rows: list[dict], *, present=True, has_table=True,
                 headers=None):
        self.url = url
        self._rows = [_Row(r) for r in rows]
        self._present = present
        self._has_table = has_table
        self._headers = list(headers or [])

    def locator(self, sel: str):
        s = sel.lower()
        if "tr" in s and "th" not in s:
            return _Loc(self._rows)
        if "th" in s or ("td" in s and "child" not in s):
            return _Loc([_Cell(h) for h in self._headers])
        if "table" in s or "grid" in s or "role" in s:
            return _Loc([_Cell("t")] if self._has_table else [])
        return _Loc([_Cell("x")] if self._present else [])


class FakeCtx:
    def __init__(self, pages):
        self.pages = list(pages)


def tms_rows_cellmap(rows: list[dict]) -> list[dict]:
    """Map friendly rows ({symbol,quantity,...}) to the TMS observer's cell selectors."""
    fs = TMSBrowserPortfolioObserver.FIELD_SELECTORS
    return [{cell: r.get(fname) for fname, cell in fs.items()} for r in rows]


def seed_fake_runtime(manager, provider: Provider, *, url: str, rows: list[dict],
                      headers=None, authenticated=True, read_on=True):
    """Insert an owner-authenticated runtime with a live fake page into the manager
    singleton (test/bootstrap only — never production)."""
    rt = manager.open(provider, launch=False)
    rt.runtime_state = RuntimeState.OPEN_OWNER_CONTROL
    if authenticated:
        manager.mark_owner_authenticated(rt.runtime_id)
    page = FakePage(url, tms_rows_cellmap(rows), headers=headers)
    manager._pw[provider] = (None, FakeCtx([page]))
    if authenticated and read_on:
        manager.set_saathi_read(rt.runtime_id, True)
    return rt
