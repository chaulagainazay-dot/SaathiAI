"""Phase 2-8 — NEPSE public-endpoint acquisition + JSON extraction.

NEPSE (nepalstock.com) is an Angular SPA whose public JSON endpoints return 401
to a plain HTTP client (a browser-issued token gates them). We do NOT replay or
forge that token (that would defeat a bot control). Instead the governed
Playwright engine loads the official page normally — the site's own JS makes the
calls — and we capture the PUBLIC JSON responses it receives. Legitimate, no
bypass, read-only.

The captured JSON is structured (heading, AD date, document link, issuer), so
extraction is deterministic and far cleaner than DOM/text scraping. Provenance
stays BROWSER_DERIVED / WEB_INTELLIGENCE; numeric market fields (prices) are
NEVER promoted to canonical market_data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from saathi.browser_research.bs_date import parse_date
from saathi.browser_research.records import (
    ExtractedRecord, ExtractionMethod, SymbolResolution,
)
from saathi.browser_research.tiers import SourceTier

NEPSE_ORIGIN = "https://www.nepalstock.com"

# Research endpoints we capture (WEB_INTELLIGENCE). Market/quote endpoints are
# intentionally NOT here — this milestone does not make browser research a quote
# authority.
NEPSE_RESEARCH_ENDPOINTS = (
    "/api/web/notice/",
    "/api/nots/news/companies/disclosure",
)
NEPSE_SECURITY_ENDPOINT = "/api/nots/security"


class EndpointClass(str, Enum):
    OFFICIAL_PUBLIC_WEB_ENDPOINT = "OFFICIAL_PUBLIC_WEB_ENDPOINT"
    OFFICIAL_PUBLIC_BUT_UNSTABLE = "OFFICIAL_PUBLIC_BUT_UNSTABLE"
    INTERNAL_FRONTEND_ENDPOINT = "INTERNAL_FRONTEND_ENDPOINT"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    UNSUITABLE = "UNSUITABLE"
    UNKNOWN = "UNKNOWN"


def classify_endpoint(url: str, *, direct_status: int | None = None,
                      in_browser_status: int | None = None,
                      requires_cookie: bool = False) -> EndpointClass:
    """Classify a discovered endpoint from observed behavior (never assume safe)."""
    from saathi.browser_research.tiers import host_of
    host = host_of(url)
    official = host == "nepalstock.com" or host.endswith(".nepalstock.com")
    if not official:
        return EndpointClass.UNSUITABLE
    # 200 only inside the browser context but 401 to a plain client → the site's
    # own token gates it; usable ONLY via in-browser capture, and unstable.
    if in_browser_status == 200 and direct_status in (401, 403):
        return EndpointClass.OFFICIAL_PUBLIC_BUT_UNSTABLE
    if direct_status == 200 and not requires_cookie:
        return EndpointClass.OFFICIAL_PUBLIC_WEB_ENDPOINT
    if in_browser_status in (401, 403) or direct_status in (401, 403):
        return EndpointClass.AUTH_REQUIRED
    if in_browser_status == 200:
        return EndpointClass.INTERNAL_FRONTEND_ENDPOINT
    return EndpointClass.UNKNOWN


# adoption gate (Phase 4)
def is_adoptable(cls: EndpointClass) -> bool:
    return cls in (EndpointClass.OFFICIAL_PUBLIC_WEB_ENDPOINT,
                   EndpointClass.OFFICIAL_PUBLIC_BUT_UNSTABLE)


# ── symbol / issuer index from NEPSE's own security list (not a 2nd registry) ──
@dataclass
class SecurityIndex:
    by_symbol: dict[str, str] = field(default_factory=dict)     # SYMBOL -> securityName
    names: list[tuple[str, str]] = field(default_factory=list)  # (lower name, SYMBOL)

    @classmethod
    def from_json(cls, securities: list[dict]) -> "SecurityIndex":
        idx = cls()
        for s in securities or []:
            sym = str(s.get("symbol") or "").strip().upper()
            name = str(s.get("securityName") or "").strip()
            if sym:
                idx.by_symbol[sym] = name
                if name:
                    idx.names.append((name.lower(), sym))
        return idx

    def resolve(self, text: str) -> tuple[str, SymbolResolution]:
        up = text.upper()
        hits = {sym for sym in self.by_symbol if re.search(rf"\b{re.escape(sym)}\b", up)}
        # also match by full company name
        low = text.lower()
        for name, sym in self.names:
            if len(name) >= 6 and name in low:
                hits.add(sym)
        if len(hits) == 1:
            return next(iter(hits)), SymbolResolution.RESOLVED
        if len(hits) >= 2:
            return "", SymbolResolution.AMBIGUOUS
        return "", SymbolResolution.UNRESOLVED


_CA = ("dividend", "bonus", "right share", "rights", "book close", "book closure",
       "auction", "buyback", "merger", "acquisition")
_CE = ("agm", "annual general meeting", "sgm", "quarterly", "annual report",
       "financial result", "audited", "unaudited", "board", "listing", "delist",
       "suspension", "resume")
_REG = ("directive", "circular", "regulation", "guideline", "bylaw", "policy",
        "amend", "sebon")


def _category(text: str) -> str:
    low = text.lower()
    if any(k in low for k in _CA):
        return "CORPORATE_ACTIONS"
    if any(k in low for k in _CE):
        return "COMPANY_EVENTS"
    if any(k in low for k in _REG):
        return "REGULATORY"
    return "OFFICIAL_NOTICES"


def _doc_url(path: str) -> str:
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return f"{NEPSE_ORIGIN}/api/nots/notice/file/{path.lstrip('/')}"


class NEPSEJsonExtractor:
    """Maps captured NEPSE JSON (notice + companyNews) → ExtractedRecord."""

    def __init__(self, security_index: SecurityIndex | None = None):
        self.securities = security_index or SecurityIndex()

    def _resolve(self, text: str) -> tuple[str, SymbolResolution]:
        if self.securities.by_symbol:
            return self.securities.resolve(text)
        return "", SymbolResolution.UNRESOLVED

    def from_notices(self, notices: list[dict]) -> list[ExtractedRecord]:
        out = []
        for n in notices or []:
            heading = str(n.get("noticeHeading") or "").strip()
            if not heading:
                continue
            raw = str(n.get("modifiedDate") or "")   # expiry is a future date, never used as pub
            dres = parse_date(raw, calendar_hint="AD")   # NEPSE API dates are AD ISO
            sym, sres = self._resolve(heading + " " + str(n.get("noticeBody") or ""))
            out.append(ExtractedRecord(
                title=heading[:240], category=_category(heading),
                source_url=f"{NEPSE_ORIGIN}/notice", source_host="nepalstock.com",
                source_tier=SourceTier.TIER_1_OFFICIAL,
                extraction_method=ExtractionMethod.OFFICIAL_ENDPOINT,
                published_at_raw=raw, published_at_normalized=dres.ad_ts,
                date_calendar=dres.calendar, issuer="", symbol=sym,
                symbol_resolution=sres,
                document_url=_doc_url(str(n.get("noticeFilePath") or "")),
                summary=str(n.get("noticeBody") or heading)[:240],
                confidence=0.9,
            ))
        return out

    def from_disclosures(self, payload: dict | list) -> list[ExtractedRecord]:
        items = payload.get("companyNews", []) if isinstance(payload, dict) else (payload or [])
        out = []
        for c in items:
            head = str(c.get("newsHeadline") or "").strip()
            if not head:
                continue
            raw = str(c.get("addedDate") or c.get("approvedDate") or "")
            dres = parse_date(raw, calendar_hint="AD")
            docs = c.get("applicationDocumentDetailsList") or []
            doc = ""
            if docs and isinstance(docs, list):
                doc = _doc_url(str(docs[0].get("filePath") or ""))
            sym, sres = self._resolve(head + " " + str(c.get("newsBody") or ""))
            out.append(ExtractedRecord(
                title=head[:240], category=_category(head),
                source_url=f"{NEPSE_ORIGIN}/company-disclosure", source_host="nepalstock.com",
                source_tier=SourceTier.TIER_1_OFFICIAL,
                extraction_method=ExtractionMethod.OFFICIAL_ENDPOINT,
                published_at_raw=raw, published_at_normalized=dres.ad_ts,
                date_calendar=dres.calendar, issuer="", symbol=sym,
                symbol_resolution=sres, document_url=doc,
                summary=str(c.get("newsBody") or head)[:240], confidence=0.9,
            ))
        return out
