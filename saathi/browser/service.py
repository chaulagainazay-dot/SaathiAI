"""BrowserService — the one interface departments call.

Selects the cheapest *capable and available* tier, executes, and escalates on
block/failure up the chain (HTTP → Playwright → Camofox). Tiers are injectable,
so tests drive escalation with fakes — no network, no real browser (AP-12).

    browser.open(url)          → Page          (escalates if JS-walled/blocked)
    browser.extract(url, css?) → text | [str]
    browser.search(query)      → [SearchResult]
    browser.screenshot(url)    → bytes
    browser.pdf(url)           → bytes
    browser.snapshot(url)      → Snapshot       (content fingerprint)
    browser.monitor(url, prev) → {changed, snapshot}
    browser.download(url,dest) → path
"""
from __future__ import annotations

from .base import BrowserTier
from .types import BrowserError, Page, SearchResult, Snapshot, Tier


def _default_tiers() -> list[BrowserTier]:
    from .http_tier import HttpTier
    from .playwright_tier import PlaywrightTier
    from .camofox_tier import CamofoxTier
    return [HttpTier(), PlaywrightTier(), CamofoxTier()]


class BrowserService:
    def __init__(self, tiers: list[BrowserTier] | None = None, sessions=None):
        self._tiers = sorted(tiers if tiers is not None else _default_tiers(),
                             key=lambda t: t.tier)
        if sessions is None:
            from .session import SessionManager
            sessions = SessionManager()
        self._sessions = sessions

    @property
    def sessions(self):
        """The SessionManager (cookies / login state / profiles)."""
        return self._sessions

    # ── tier selection ──────────────────────────────────────────────────
    def _usable(self, cap_attr: str, *, min_tier: Tier = Tier.HTTP) -> list[BrowserTier]:
        out = []
        for t in self._tiers:
            if t.tier < min_tier:
                continue
            if not t.available():
                continue
            if not getattr(t.capabilities(), cap_attr):
                continue
            out.append(t)
        return out

    def tiers_status(self) -> dict[str, bool]:
        """Diagnostics: which tiers are installed/usable right now."""
        return {t.name: t.available() for t in self._tiers}

    # ── open (with escalation + optional named session) ─────────────────
    def open(self, url: str, *, evade: bool = False, timeout: int = 30,
             session: str | None = None) -> Page:
        min_tier = Tier.CAMOFOX if evade else Tier.HTTP
        candidates = self._usable("fetch", min_tier=min_tier)
        if not candidates:
            raise BrowserError(f"no available browser tier can fetch (evade={evade})")
        state = self._sessions.load(session) if session else None
        last: Page | None = None
        last_err: Exception | None = None
        result: Page | None = None
        for t in candidates:
            try:
                page = t.open(url, timeout=timeout, session=state)
            except Exception as e:  # tier crashed — escalate
                last_err = e
                continue
            if page.ok:
                result = page
                break
            last = page  # blocked/non-ok — remember, try a stronger tier
        if result is None:
            result = last
        if state is not None and result is not None:
            self._sessions.save(state)   # persist cookies / login the fetch updated
        if result is not None:
            return result
        raise BrowserError(f"all tiers failed to open {url}: {last_err}")

    # ── extract ─────────────────────────────────────────────────────────
    def extract(self, url: str, selector: str | None = None, *, timeout: int = 30):
        if selector is None:
            return self.open(url, timeout=timeout).text
        for t in self._usable("dom_query"):
            try:
                return t.query(url, selector, timeout=timeout)
            except NotImplementedError:
                continue
            except Exception:
                continue
        raise BrowserError(f"no tier could DOM-query {url!r} for {selector!r}")

    # ── search ──────────────────────────────────────────────────────────
    def search(self, query: str, *, limit: int = 10, timeout: int = 30) -> list[SearchResult]:
        for t in self._tiers:
            if t.available() and "search" in t.capabilities().labels and hasattr(t, "search"):
                return t.search(query, limit=limit, timeout=timeout)  # type: ignore[attr-defined]
        raise BrowserError("no search-capable tier available")

    # ── screenshot / pdf ────────────────────────────────────────────────
    def screenshot(self, url: str, *, full_page: bool = True, timeout: int = 30) -> bytes:
        return self._binary("screenshot", lambda t: t.screenshot(url, timeout=timeout, full_page=full_page), url)

    def pdf(self, url: str, *, timeout: int = 30) -> bytes:
        return self._binary("pdf", lambda t: t.pdf(url, timeout=timeout), url)

    def _binary(self, cap_attr: str, run, url: str) -> bytes:
        tiers = self._usable(cap_attr)
        if not tiers:
            raise BrowserError(f"no available tier can {cap_attr} (install Playwright)")
        last_err: Exception | None = None
        for t in tiers:
            try:
                return run(t)
            except Exception as e:
                last_err = e
                continue
        raise BrowserError(f"all tiers failed to {cap_attr} {url}: {last_err}")

    # ── monitoring ──────────────────────────────────────────────────────
    def snapshot(self, url: str, *, timeout: int = 30) -> Snapshot:
        for t in self._usable("fetch"):
            try:
                return t.snapshot(url, timeout=timeout)
            except Exception:
                continue
        raise BrowserError(f"could not snapshot {url}")

    def monitor(self, url: str, previous_digest: str | None = None, *, timeout: int = 30) -> dict:
        snap = self.snapshot(url, timeout=timeout)
        changed = previous_digest is not None and previous_digest != snap.digest
        return {"changed": changed, "digest": snap.digest, "snapshot": snap,
                "first_seen": previous_digest is None}

    # ── download ────────────────────────────────────────────────────────
    def download(self, url: str, dest: str, *, timeout: int = 60) -> str:
        import httpx
        from pathlib import Path
        p = Path(dest)
        p.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(follow_redirects=True, timeout=timeout) as c:
            with c.stream("GET", url) as r:
                r.raise_for_status()
                with open(p, "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
        return str(p)


# Process-wide default service.
browser = BrowserService()
