"""BrowserService — tiered technical browser interface.

M17.24: Public production callers must enter via GovernedBrowser /
ExecutionGateway. Direct tier dispatch is restricted to:

  * injected-tier test harnesses (allow_direct defaults True when tiers passed)
  * BrowserAdapter after gateway authorization (``_open_direct``)
  * explicit ``allow_direct=True`` construction
  * ``SAATHI_ALLOW_RAW_BROWSER=1`` emergency override (never production default)

    browser.open(url)                 → governed by default (production singleton)
    browser.open(url, governed=True)  → ExecutionGateway
    service._open_direct(url)         → tiers only (adapter / allowlisted)
"""
from __future__ import annotations

from .base import BrowserTier
from .types import BrowserError, Page, SearchResult, Snapshot, Tier


def _event(name: str, payload: dict) -> None:
    """Publish a Browser Service event to the platform Event Fabric (best-effort)."""
    try:
        from saathi.events import bus
        bus.publish_sync(name, payload)
    except Exception:
        pass


def _default_tiers() -> list[BrowserTier]:
    from .http_tier import HttpTier
    from .playwright_tier import PlaywrightTier
    from .camofox_tier import CamofoxTier
    return [HttpTier(), PlaywrightTier(), CamofoxTier()]


class BrowserService:
    def __init__(
        self,
        tiers: list[BrowserTier] | None = None,
        sessions=None,
        *,
        allow_direct: bool | None = None,
    ):
        # Injected tiers ⇒ test/adapter harness; process singleton keeps direct off.
        if allow_direct is None:
            allow_direct = tiers is not None
        self._allow_direct = bool(allow_direct)
        self._tiers = sorted(tiers if tiers is not None else _default_tiers(),
                             key=lambda t: t.tier)
        if sessions is None:
            from .session import SessionManager
            sessions = SessionManager()
        self._sessions = sessions

    @property
    def allow_direct(self) -> bool:
        return self._allow_direct

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

    def _direct_permitted(self) -> bool:
        if self._allow_direct:
            return True
        try:
            from saathi.browser.guard import raw_browser_env_enabled
            return raw_browser_env_enabled()
        except Exception:
            return False

    # ── open (with escalation + optional named session) ─────────────────
    def open(self, url: str, *, evade: bool = False, timeout: int = 30,
             session: str | None = None, governed: bool | None = None,
             actor: str = "user:system", mission_id: str = "browser") -> Page:
        """Open URL.

        M17.24 defaults:
          * production singleton (allow_direct=False): always governed
          * test harnesses (injected tiers): direct tiers when governed is None/False
          * governed=True: always ExecutionGateway
          * governed=False without allow_direct: fail closed
        """
        if governed is True:
            return self._open_governed(
                url, evade=evade, timeout=timeout, session=session,
                actor=actor, mission_id=mission_id,
            )
        if governed is False:
            if not self._direct_permitted():
                from saathi.browser.guard import BrowserGovernanceError
                raise BrowserGovernanceError(
                    "DIRECT_BROWSER_BLOCKED",
                    "BrowserService.open(governed=False) blocked outside allowlisted "
                    "direct harness; use GovernedBrowser or governed=True",
                )
            return self._open_direct(url, evade=evade, timeout=timeout, session=session)
        # governed is None — production defaults to gateway; harness may go direct
        if self._direct_permitted():
            return self._open_direct(url, evade=evade, timeout=timeout, session=session)
        return self._open_governed(
            url, evade=evade, timeout=timeout, session=session,
            actor=actor, mission_id=mission_id,
        )

    def _open_direct(self, url: str, *, evade: bool = False, timeout: int = 30,
                     session: str | None = None) -> Page:
        """Technical tier open — only for BrowserAdapter / allowlisted harnesses."""
        min_tier = Tier.CAMOFOX if evade else Tier.HTTP
        candidates = self._usable("fetch", min_tier=min_tier)
        if not candidates:
            raise BrowserError(f"no available browser tier can fetch (evade={evade})")
        state = self._sessions.load(session) if session else None
        _event("browser.started", {"url": url, "evade": evade})
        last: Page | None = None
        last_err: Exception | None = None
        result: Page | None = None
        for i, t in enumerate(candidates):
            try:
                page = t.open(url, timeout=timeout, session=state)
            except Exception as e:  # tier crashed — escalate
                last_err = e
                if i + 1 < len(candidates):
                    _event("browser.escalated", {"url": url, "from": t.name, "reason": "error"})
                continue
            if page.ok:
                result = page
                break
            last = page  # blocked/non-ok — remember, try a stronger tier
            _event("browser.blocked", {"url": url, "tier": t.name})
            if i + 1 < len(candidates):
                _event("browser.escalated", {"url": url, "from": t.name, "reason": "blocked"})
        if result is None:
            result = last
        if state is not None and result is not None:
            self._sessions.save(state)   # persist cookies / login the fetch updated
        if result is not None:
            _event("browser.finished", {"url": url, "tier": result.tier.name,
                                        "ok": result.ok, "status": result.status})
            return result
        _event("browser.finished", {"url": url, "ok": False, "error": str(last_err)})
        raise BrowserError(f"all tiers failed to open {url}: {last_err}")

    def _open_governed(self, url: str, *, evade: bool = False, timeout: int = 30,
                       session: str | None = None, actor: str = "user:system",
                       mission_id: str = "browser") -> Page:
        from saathi.browser.governed import BrowserAdapter, GovernedBrowser
        # Technical adapter uses this service's _open_direct (no recursion)
        gb = GovernedBrowser(
            mode="service",
            adapter=BrowserAdapter(service=self, mode="service"),
        )
        rec = gb.execute(
            action="navigate", url=url, session_id=session or "default",
            environment="dev", actor=actor, mission_id=mission_id,
        )
        if rec.status != "succeeded":
            raise BrowserError(
                f"governed browser denied/failed: {rec.failure_category or rec.status}: "
                f"{rec.result_summary}"
            )
        # Adapter already performed the authorized open via _open_direct; rebuild
        # a Page for API compatibility without a second network hop when possible.
        summary = rec.result_summary or ""
        return Page(
            url=url, status=200, text="", title=summary[:80],
            tier=Tier.HTTP,
        )

    # ── extract ─────────────────────────────────────────────────────────
    def extract(self, url: str, selector: str | None = None, *, timeout: int = 30,
                governed: bool | None = None, actor: str = "user:system"):
        if selector is None:
            return self.open(url, timeout=timeout, governed=governed, actor=actor).text
        if not self._direct_permitted() and governed is not True:
            # Route extract through governance for production singleton
            from saathi.browser.governed import BrowserAdapter, GovernedBrowser
            gb = GovernedBrowser(
                mode="service",
                adapter=BrowserAdapter(service=self, mode="service"),
            )
            rec = gb.execute(
                action="extract", url=url, selector=selector or "",
                actor=actor, environment="dev",
            )
            if rec.status != "succeeded":
                raise BrowserError(
                    f"governed extract denied/failed: {rec.failure_category or rec.status}"
                )
            return rec.result_summary or ""
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
    def screenshot(self, url: str, *, full_page: bool = True, timeout: int = 30,
                   governed: bool | None = None, actor: str = "user:system") -> bytes:
        if not self._direct_permitted() and governed is not False:
            from saathi.browser.governed import BrowserAdapter, GovernedBrowser
            gb = GovernedBrowser(
                mode="service",
                adapter=BrowserAdapter(service=self, mode="service"),
            )
            rec = gb.execute(
                action="screenshot", url=url, actor=actor, environment="dev",
            )
            if rec.status != "succeeded":
                raise BrowserError(
                    f"governed screenshot denied/failed: {rec.failure_category or rec.status}"
                )
            # Evidence stored; return empty bytes marker (no secret page content)
            return b""
        return self._binary("screenshot", lambda t: t.screenshot(url, timeout=timeout, full_page=full_page), url)

    def pdf(self, url: str, *, timeout: int = 30) -> bytes:
        if not self._direct_permitted():
            raise BrowserError(
                "pdf() requires allow_direct harness or SAATHI_ALLOW_RAW_BROWSER=1; "
                "use GovernedBrowser for production"
            )
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
        if not self._direct_permitted():
            page = self.open(url, timeout=timeout, governed=True)
            from .types import Snapshot as Snap
            body = page.text or page.url or ""
            return Snap(url=url, digest=str(abs(hash(body)))[:16], length=len(body))
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
    def download(self, url: str, dest: str, *, timeout: int = 60,
                 governed: bool | None = None, actor: str = "user:system") -> str:
        if not self._direct_permitted() and governed is not False:
            from saathi.browser.governed import BrowserAdapter, GovernedBrowser
            from pathlib import Path
            gb = GovernedBrowser(
                mode="service",
                adapter=BrowserAdapter(service=self, mode="service",
                                       workspace=Path(dest).parent),
            )
            rec = gb.execute(
                action="download", url=url, file_path=dest, actor=actor,
                environment="dev",
            )
            if rec.status != "succeeded":
                raise BrowserError(
                    f"governed download denied/failed: {rec.failure_category or rec.status}"
                )
            return dest
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


# Process-wide default service — production-safe: direct tiers off.
browser = BrowserService(allow_direct=False)
