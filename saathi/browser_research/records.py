"""Phase 3 — canonical ExtractedRecord + deterministic dedup.

The uniform intermediate every extractor returns. Mapped into the FROZEN
ExtractedFact by the mission, so the contract/evidence/confidence pipeline is
unchanged.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum

from saathi.browser_research.bs_date import Calendar
from saathi.browser_research.tiers import SourceTier


class ExtractionMethod(str, Enum):
    OFFICIAL_ENDPOINT = "OFFICIAL_ENDPOINT"   # public JSON captured via governed Playwright
    JINA_READER = "JINA_READER"               # clean webpage text via Agent-Reach / r.jina.ai
    AGENT_REACH_SEARCH = "AGENT_REACH_SEARCH" # web search via Agent-Reach (Exa/DDG)
    HTTP_DOM = "HTTP_DOM"
    PLAYWRIGHT_DOM = "PLAYWRIGHT_DOM"
    TABLE = "TABLE"
    DOCUMENT_LINK = "DOCUMENT_LINK"
    FALLBACK_TEXT = "FALLBACK_TEXT"


class SymbolResolution(str, Enum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


_WS = re.compile(r"\s+")


def _norm_title(title: str) -> str:
    return _WS.sub(" ", (title or "").strip().lower())


@dataclass(frozen=True)
class ExtractedRecord:
    title: str
    category: str                       # maps to FactGroup value
    source_url: str
    source_host: str
    source_tier: SourceTier
    extraction_method: ExtractionMethod
    published_at_raw: str = ""
    published_at_normalized: float | None = None   # AD unix ts
    date_calendar: Calendar = Calendar.UNKNOWN
    issuer: str = ""
    symbol: str = ""
    symbol_resolution: SymbolResolution = SymbolResolution.UNRESOLVED
    detail_url: str = ""
    document_url: str = ""
    summary: str = ""
    confidence: float = 0.0             # EXTRACTION confidence (distinct from tier)
    provenance: str = "BROWSER_DERIVED"

    def dedup_key(self) -> str:
        parts = [
            self.source_host,
            _norm_title(self.title),
            self.published_at_raw or (str(self.published_at_normalized) if self.published_at_normalized else ""),
            self.detail_url or self.document_url or "",
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


def deduplicate(records: list[ExtractedRecord]) -> tuple[list[ExtractedRecord], int]:
    """Return (unique records, duplicate_count). Deterministic, order-preserving."""
    seen: set[str] = set()
    unique: list[ExtractedRecord] = []
    dupes = 0
    for r in records:
        k = r.dedup_key()
        if k in seen:
            dupes += 1
            continue
        seen.add(k)
        unique.append(r)
    return unique, dupes
