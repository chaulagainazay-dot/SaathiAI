"""Phase 2/4/14/15/16 — source-aware extractors → canonical ExtractedRecord.

DOM/selector-scoped where the tier supports it (Playwright); noise-filtered text
otherwise (HTTP tier). Source-aware extractors know their site publishes BS dates
and pass that hint. The smallest set of specialized extractors: Generic + the
official Nepal sources. Each returns the SAME ExtractedRecord shape.
"""
from __future__ import annotations

import re

from saathi.browser_research.bs_date import Calendar, parse_date
from saathi.browser_research.contract import FetchedPage
from saathi.browser_research.noise import filter_lines
from saathi.browser_research.records import (
    ExtractedRecord, ExtractionMethod, SymbolResolution,
)
from saathi.browser_research.tiers import classify_source, host_of

# category routing (title keywords → FactGroup value)
_ROUTES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("CORPORATE_ACTIONS", ("dividend", "bonus share", "bonus shares", "right share",
                           "rights share", "rights issue", "right issue", "book close",
                           "book closure", "auction", "buyback", "merger", "acquisition")),
    ("COMPANY_EVENTS", ("agm", "annual general meeting", "sgm", "special general meeting",
                        "quarterly report", "quarterly result", "annual report",
                        "financial result", "unaudited", "audited financial",
                        "board decision", "listing", "delisting", "suspension")),
    ("REGULATORY", ("directive", "circular", "regulation", "guideline", "monetary policy",
                    "amendment", "bylaw", "policy", "sebon", "nrb", "nepal rastra bank",
                    "supervision", "enforcement")),
    ("MARKET_CONTEXT", ("nepse index", "turnover", "market summary", "index closed",
                        "market capitalization", "trading halt", "floorsheet")),
    ("OFFICIAL_NOTICES", ("notice", "notification", "announcement", "press release",
                          "publication", "bulletin")),
)

_URL_RE = re.compile(r"https?://[^\s'\"<>]+")
_SYMBOL_RE = re.compile(r"\b([A-Z]{3,10})\b")
_DATEISH = re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")

_METHOD_CONF = {
    ExtractionMethod.TABLE: 0.85,
    ExtractionMethod.PLAYWRIGHT_DOM: 0.8,
    ExtractionMethod.HTTP_DOM: 0.7,
    ExtractionMethod.DOCUMENT_LINK: 0.6,
    ExtractionMethod.FALLBACK_TEXT: 0.45,
}

# tokens that are English words, not NEPSE symbols (reduce false symbol hits)
_STOP_SYMBOLS = {"THE", "AND", "FOR", "AGM", "SGM", "NEW", "NRB", "IPO", "FPO", "PDF",
                 "SEBON", "NEPSE", "CDSC", "LTD", "CEO", "USD", "NPR", "GDP"}


def _route(title_low: str) -> str | None:
    for group, keys in _ROUTES:
        if any(k in title_low for k in keys):
            return group
    return None


def _resolve_symbol(text: str) -> tuple[str, SymbolResolution]:
    from saathi.platform.nepse.instruments import normalize_symbol
    cands = [t for t in _SYMBOL_RE.findall(text) if t not in _STOP_SYMBOLS]
    valid = []
    for c in cands:
        try:
            valid.append(normalize_symbol(c))
        except Exception:
            continue
    distinct = sorted(set(valid))
    if len(distinct) == 1:
        return distinct[0], SymbolResolution.RESOLVED
    if len(distinct) >= 2:
        return "", SymbolResolution.AMBIGUOUS   # never guess between candidates
    return "", SymbolResolution.UNRESOLVED


class GenericExtractor:
    calendar_hint: str | None = None      # subclasses set "BS" for Nepali gov sites
    default_method = ExtractionMethod.FALLBACK_TEXT

    def extract(self, page: FetchedPage) -> list[ExtractedRecord]:
        if not page.ok or not page.content:
            return []
        host = host_of(page.final_origin) or host_of(page.url)
        tier = classify_source(page.url)
        method = self.default_method
        records: list[ExtractedRecord] = []
        for line in filter_lines(page.content.splitlines()):
            low = line.lower()
            group = _route(low)
            if group is None:
                continue
            if group in ("CORPORATE_ACTIONS", "COMPANY_EVENTS", "MARKET_CONTEXT") \
                    and not any(ch.isdigit() for ch in line):
                continue
            dres = parse_date(line, calendar_hint=self.calendar_hint)
            urls = _URL_RE.findall(line)
            doc = next((u for u in urls if u.lower().endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx"))), "")
            detail = next((u for u in urls if u != doc), "")
            m = ExtractionMethod.DOCUMENT_LINK if doc else method
            sym, sres = _resolve_symbol(line)
            conf = _METHOD_CONF[m]
            if dres.calendar in (Calendar.BS, Calendar.AD):
                conf = min(0.95, conf + 0.1)
            records.append(ExtractedRecord(
                title=re.sub(r"\s+", " ", line)[:240],
                category=group,
                source_url=page.url,
                source_host=host,
                source_tier=tier,
                extraction_method=m,
                published_at_raw=(_DATEISH.search(line).group(0) if _DATEISH.search(line) else ""),
                published_at_normalized=dres.ad_ts,
                date_calendar=dres.calendar,
                issuer="",
                symbol=sym,
                symbol_resolution=sres,
                detail_url=detail,
                document_url=doc,
                summary=line[:240],
                confidence=round(conf, 3),
            ))
        return records


class _BSGovExtractor(GenericExtractor):
    calendar_hint = "BS"
    default_method = ExtractionMethod.HTTP_DOM


class SEBONExtractor(_BSGovExtractor):
    pass


class NRBExtractor(_BSGovExtractor):
    pass


class CDSCExtractor(_BSGovExtractor):
    pass


class NEPSEExtractor(_BSGovExtractor):
    # NEPSE is a JS SPA — content usually arrives via the Playwright tier.
    default_method = ExtractionMethod.PLAYWRIGHT_DOM


class CompanyDisclosureExtractor(GenericExtractor):
    calendar_hint = "BS"                # listed companies publish BS notices
    default_method = ExtractionMethod.HTTP_DOM


_BY_HOST: tuple[tuple[str, type[GenericExtractor]], ...] = (
    ("sebon.gov.np", SEBONExtractor),
    ("nrb.org.np", NRBExtractor),
    ("cdsc.com.np", CDSCExtractor),
    ("cdscnp.com", CDSCExtractor),
    ("nepalstock.com", NEPSEExtractor),
)


def extractor_for(url_or_host: str) -> GenericExtractor:
    host = host_of(url_or_host) or (url_or_host or "").lower()
    for root, cls in _BY_HOST:
        if host == root or host.endswith("." + root):
            return cls()
    return GenericExtractor()
