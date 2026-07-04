"""Shared value types for the Browser Service — provider-neutral."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Tier(IntEnum):
    """Escalation order — lower is cheaper/faster, tried first."""
    HTTP = 1        # plain fetch, no JavaScript
    PLAYWRIGHT = 2  # real browser, renders JS, screenshots/PDF
    CAMOFOX = 3     # anti-detect browser for blocked/bot-walled pages
    HUMAN = 4       # your real logged-in Chrome profile via the Mac Agent (last resort)


class BrowserError(Exception):
    """Raised when no tier can satisfy a request."""


@dataclass
class Page:
    url: str
    status: int
    html: str = ""
    text: str = ""
    title: str = ""
    tier: Tier = Tier.HTTP          # which tier actually served it
    blocked: bool = False           # bot-wall / challenge detected

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 400 and not self.blocked


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""


@dataclass
class Snapshot:
    """A content fingerprint for change monitoring."""
    url: str
    digest: str
    length: int
    fetched_ms: float = 0.0


@dataclass
class Capabilities:
    """What a tier can do — the service routes by these, never by class name."""
    fetch: bool = True
    render_js: bool = False
    screenshot: bool = False
    pdf: bool = False
    evade: bool = False
    dom_query: bool = False
    labels: frozenset[str] = field(default_factory=frozenset)
