"""Deterministic read-only financial page observers.

An observer NEVER clicks/types/navigates/submits/downloads. It reads an allowlist of DOM
fields through a ReadOnlyPageReader (which itself exposes only read methods), redacts private
data, and returns typed rows. The authenticated page's raw DOM/HTML/screenshot is NEVER sent
to any model — only the deterministically extracted, allowlisted, redacted fields are.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from saathi.platform.finance.browser_runtime import AuthState
from saathi.platform.finance.policy import classify_field, redact, FieldClass


class ReadOnlyPageReader:
    """Wraps a live page but exposes ONLY read operations. No click/type/goto/fill/press/
    evaluate-for-action. Tests inject a dict-backed fake with the same read surface."""

    def __init__(self, page):
        self._page = page

    def exists(self, selector: str) -> bool:
        try:
            return self._page.locator(selector).count() > 0
        except Exception:
            return False

    def count(self, selector: str) -> int:
        try:
            return self._page.locator(selector).count()
        except Exception:
            return 0

    def text(self, selector: str) -> str | None:
        try:
            loc = self._page.locator(selector).first
            return loc.inner_text().strip() if loc.count() else None
        except Exception:
            return None

    def rows(self, row_selector: str, field_selectors: dict[str, str]) -> list[dict]:
        out = []
        try:
            rl = self._page.locator(row_selector)
            for i in range(rl.count()):
                r = rl.nth(i)
                row = {}
                for fname, cell in field_selectors.items():
                    try:
                        c = r.locator(cell).first
                        row[fname] = c.inner_text().strip() if c.count() else None
                    except Exception:
                        row[fname] = None
                out.append(row)
        except Exception:
            pass
        return out


class FinancialPageObserver:
    """Base observer. Subclasses declare selectors + field allowlist. No interaction methods."""
    provider = ""
    ALLOWED_FIELDS: tuple[str, ...] = ()
    PRIVATE_FIELDS: tuple[str, ...] = ()          # never surfaced (name/account#/email/…)
    PROHIBITED_REGIONS: tuple[str, ...] = ()      # order forms / withdrawal / settings
    AUTH_INDICATOR: str = ""                      # selector proving an authenticated surface
    ROW_SELECTOR: str = ""
    FIELD_SELECTORS: dict[str, str] = {}
    SELECTORS_VERIFIED = False                    # True only after real owner validation

    def authentication_state(self, reader: ReadOnlyPageReader) -> AuthState:
        """Deterministic; never reads credentials. Presence of a known authenticated element."""
        if not self.AUTH_INDICATOR:
            return AuthState.UNKNOWN
        return AuthState.OWNER_AUTHENTICATED if reader.exists(self.AUTH_INDICATOR) else AuthState.UNKNOWN

    def _clean(self, row: dict) -> dict:
        out = {}
        for k, v in row.items():
            if k in self.PRIVATE_FIELDS or classify_field(k) != FieldClass.PUBLIC_READABLE:
                continue                                    # drop private/sensitive fields
            if k not in self.ALLOWED_FIELDS:
                continue                                    # allowlist only
            out[k] = redact(v) if isinstance(v, str) else v
        return out

    def observe_portfolio(self, reader: ReadOnlyPageReader) -> tuple[list[dict], list[str]]:
        if not self.ROW_SELECTOR:
            return [], ["observer has no verified portfolio selectors"]
        raw = reader.rows(self.ROW_SELECTOR, self.FIELD_SELECTORS)
        rows = [self._clean(r) for r in raw if any(r.values())]
        lims = []
        if not self.SELECTORS_VERIFIED:
            lims.append("SELECTORS_PROVISIONAL_UNVERIFIED (validate at owner login)")
        return rows, lims

    def observe_account_summary(self, reader: ReadOnlyPageReader) -> dict:
        return {"provider": self.provider, "verified_selectors": self.SELECTORS_VERIFIED}

    def health(self, reader: ReadOnlyPageReader) -> dict:
        return {"provider": self.provider,
                "authenticated": self.authentication_state(reader).value,
                "selectors_verified": self.SELECTORS_VERIFIED}


class BinanceBrowserPortfolioObserver(FinancialPageObserver):
    """PROVISIONAL — real Binance wallet DOM is verified only at owner login. No API key, no
    token/cookie extraction, no XHR replay: DOM-visible fields only."""
    provider = "BINANCE"
    ALLOWED_FIELDS = ("asset", "quantity", "available", "locked", "displayed_value")
    PRIVATE_FIELDS = ("account_id", "email", "phone", "uid", "name")
    PROHIBITED_REGIONS = ("trade", "withdraw", "deposit", "convert", "transfer", "api-management")
    AUTH_INDICATOR = "[data-bn-type='wallet'], .wallet-balance"      # provisional
    ROW_SELECTOR = "[data-testid='asset-row'], table tbody tr"       # provisional
    FIELD_SELECTORS = {"asset": "td:nth-child(1)", "quantity": "td:nth-child(2)",
                       "available": "td:nth-child(3)", "locked": "td:nth-child(4)"}


class TMSBrowserPortfolioObserver(FinancialPageObserver):
    """PROVISIONAL — per-broker NEPSE TMS DOM differs; verified only at owner login."""
    provider = "TMS"
    ALLOWED_FIELDS = ("symbol", "quantity", "available", "wacc", "displayed_value", "pnl")
    PRIVATE_FIELDS = ("client_code", "boid", "name", "email", "phone", "bank_account")
    PROHIBITED_REGIONS = ("order", "buy", "sell", "purchase", "settings", "transfer")
    AUTH_INDICATOR = ".portfolio, #portfolioTable"                    # provisional
    ROW_SELECTOR = "#portfolioTable tbody tr, table.portfolio tbody tr"
    FIELD_SELECTORS = {"symbol": "td:nth-child(1)", "quantity": "td:nth-child(2)",
                       "available": "td:nth-child(3)", "wacc": "td:nth-child(4)",
                       "displayed_value": "td:nth-child(5)"}


OBSERVERS = {"BINANCE": BinanceBrowserPortfolioObserver, "TMS": TMSBrowserPortfolioObserver}


def get_observer(provider: str) -> FinancialPageObserver | None:
    cls = OBSERVERS.get(str(provider).upper())
    return cls() if cls else None
