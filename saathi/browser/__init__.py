"""Browser Service (Phase 1.2) — one interface, tiered backends.

Departments call `browser.open/extract/search/screenshot/pdf/monitor`; they never
import Playwright or Camofox directly. The service escalates cheapest-capable
first: HTTP (no JS) → Playwright (renders JS) → Camofox (anti-detect). Same
architecture as the Model Router: capability-based selection, an ordered
fallback chain, and injectable backends so the whole thing is testable with
fakes (no network, no browser).

M17.23/M17.24: production side-effecting browser actions MUST enter through
``saathi.browser.governed.GovernedBrowser`` (ExecutionGateway boundary). The
process-wide ``browser`` singleton has ``allow_direct=False`` and routes open
through governance. Low-level drivers are allowlisted in ``guard.py``.
"""
from .types import Page, SearchResult, Tier, BrowserError
from .service import BrowserService, browser
from .session import SessionManager, SessionState
from .guard import BrowserGovernanceError

__all__ = ["Page", "SearchResult", "Tier", "BrowserError", "BrowserService",
           "browser", "SessionManager", "SessionState", "BrowserGovernanceError"]