"""Browser Service (Phase 1.2) — one interface, tiered backends.

Departments call `browser.open/extract/search/screenshot/pdf/monitor`; they never
import Playwright or Camofox directly. The service escalates cheapest-capable
first: HTTP (no JS) → Playwright (renders JS) → Camofox (anti-detect). Same
architecture as the Model Router: capability-based selection, an ordered
fallback chain, and injectable backends so the whole thing is testable with
fakes (no network, no browser).
"""
from .types import Page, SearchResult, Tier, BrowserError
from .service import BrowserService, browser

__all__ = ["Page", "SearchResult", "Tier", "BrowserError", "BrowserService", "browser"]
