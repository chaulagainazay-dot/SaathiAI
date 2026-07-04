"""HTTP tier — plain fetch, no JavaScript. Cheapest; tried first.

Dependency-free (httpx is already a platform dependency). Serves static pages,
plain-text extraction, and keyless DuckDuckGo HTML search. Flags bot-walls /
JS-required pages via `Page.blocked` so the service escalates to Playwright.
"""
from __future__ import annotations

import re

from .base import BrowserTier
from .types import Capabilities, Page, SearchResult, Tier

_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_STRIP = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_BLOCK_MARKERS = (
    "captcha", "are you a robot", "cf-challenge", "cf-browser-verification",
    "access denied", "attention required", "unusual traffic",
)
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


def html_to_text(html: str) -> str:
    no_scripts = _TAG.sub(" ", html)
    text = _STRIP.sub(" ", no_scripts)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
            .replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
            .replace("&quot;", '"'))
    text = _WS.sub(" ", text)
    return "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())


def _title(html: str) -> str:
    m = _TITLE.search(html)
    return html_to_text(m.group(1)).strip() if m else ""


def _looks_blocked(status: int, html: str) -> bool:
    if status in (403, 429, 503):
        return True
    low = html[:4000].lower()
    return any(m in low for m in _BLOCK_MARKERS)


class HttpTier(BrowserTier):
    name = "http"
    tier = Tier.HTTP

    def __init__(self, transport=None):
        # transport injectable for tests (httpx.MockTransport)
        self._transport = transport

    def capabilities(self) -> Capabilities:
        return Capabilities(fetch=True, labels=frozenset({"fetch", "search"}))

    def available(self) -> bool:
        try:
            import httpx  # noqa: F401
            return True
        except Exception:
            return False

    def _client(self, timeout: int):
        import httpx
        return httpx.Client(follow_redirects=True, timeout=timeout,
                            headers={"User-Agent": _UA},
                            transport=self._transport)

    def open(self, url: str, *, timeout: int = 30) -> Page:
        with self._client(timeout) as c:
            r = c.get(url)
        html = r.text or ""
        blocked = _looks_blocked(r.status_code, html)
        return Page(url=str(r.url), status=r.status_code, html=html,
                    text=html_to_text(html), title=_title(html),
                    tier=Tier.HTTP, blocked=blocked)

    def search(self, query: str, *, limit: int = 10, timeout: int = 30) -> list[SearchResult]:
        """Keyless search via DuckDuckGo's HTML endpoint."""
        with self._client(timeout) as c:
            r = c.post("https://html.duckduckgo.com/html/", data={"q": query})
        results: list[SearchResult] = []
        for m in re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            r.text or "", re.I | re.S,
        ):
            href, title = m.group(1), html_to_text(m.group(2))
            if title and href.startswith("http"):
                results.append(SearchResult(title=title, url=href))
            if len(results) >= limit:
                break
        return results
