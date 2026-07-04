"""Re-export shim — canonical home for the Browser Service.

Implementation currently lives in the `saathi.browser` package. New code imports
from here: `from saathi.infrastructure.browser import browser, BrowserService`.
"""
from saathi.browser import *  # noqa: F401,F403
from saathi.browser import BrowserService, Page, SearchResult, Tier, BrowserError, browser

__all__ = ["BrowserService", "Page", "SearchResult", "Tier", "BrowserError", "browser"]
