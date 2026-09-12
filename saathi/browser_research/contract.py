"""M — BROWSER_RESEARCH_CONTRACT_AND_ISOLATED_ACQUISITION_V1.

The narrow governed web-research contract. RESEARCH ONLY / READ ONLY.

This module defines the *shape* of a bounded public-web research mission and its
result. It is deterministic and dependency-free: no network, no browser, no
clock inside a value type, no ExecutionGateway, no market-data authority. The
provider (``provider.py``) executes requests over the EXISTING SaathiOS
``GovernedBrowser`` + Playwright tier; the mission (``nepse.py``) fills the
result; the bridges feed the EXISTING evidence store and research-confidence
framework.

Authority (enforced by test): data only. No execution, approval, risk, ledger,
trade, broker, or market_data-write authority. Browser-derived facts are
``WEB_INTELLIGENCE`` / ``BROWSER_DERIVED`` and never canonical ``MARKET_DATA``.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from saathi.browser_research.freshness import Freshness
from saathi.browser_research.tiers import SourceTier

SCHEMA_VERSION = "browser_research.v1"

# Authority locks — mirror tg/research_orchestrator semantics. RESEARCH ONLY.
AUTHORITY = {
    "research_only": True,
    "read_only": True,
    "offline_capable": True,
    "no_broker_connection": True,
    "no_order_submission": True,
    "no_live_trading": True,
    "no_market_data_write": True,
    "no_execution_gateway_trade": True,
    "no_credentials": True,
    "no_captcha_solving": True,
    "max_authority": "GOVERNED_PUBLIC_WEB_RESEARCH_ONLY",
}


class MissionType(str, Enum):
    NEPSE_DAILY_INTELLIGENCE = "NEPSE_DAILY_INTELLIGENCE"


class ResearchStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    BLOCKED = "BLOCKED"


class DataDomain(str, Enum):
    """The MARKET_DATA vs WEB_INTELLIGENCE authority boundary (Phase 3)."""
    WEB_INTELLIGENCE = "WEB_INTELLIGENCE"
    MARKET_DATA = "MARKET_DATA"


class Provenance(str, Enum):
    BROWSER_DERIVED = "BROWSER_DERIVED"
    API_CANONICAL = "API_CANONICAL"


class FactGroup(str, Enum):
    OFFICIAL_NOTICES = "OFFICIAL_NOTICES"
    CORPORATE_ACTIONS = "CORPORATE_ACTIONS"
    REGULATORY = "REGULATORY"
    COMPANY_EVENTS = "COMPANY_EVENTS"
    MARKET_CONTEXT = "MARKET_CONTEXT"


class ContractError(ValueError):
    """Raised when a request/result violates the contract (fail-closed)."""


# ── request ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ResearchRequest:
    mission_id: str
    mission_type: MissionType
    query: str = ""
    market: str = "NEPSE"
    symbols: tuple[str, ...] = ()
    allowed_domains: tuple[str, ...] = ()
    max_pages: int = 6
    max_runtime_sec: float = 90.0
    freshness_requirement: Freshness = Freshness.RECENT
    extraction_schema: dict = field(default_factory=dict)
    evidence_required: bool = True
    actor: str = "user:owner"

    def validate(self) -> "ResearchRequest":
        if not self.mission_id or not str(self.mission_id).strip():
            raise ContractError("mission_id required")
        if not isinstance(self.mission_type, MissionType):
            raise ContractError("mission_type must be a MissionType")
        if self.max_pages < 1 or self.max_pages > 25:
            raise ContractError("max_pages out of bounds (1..25)")
        if self.max_runtime_sec <= 0 or self.max_runtime_sec > 600:
            raise ContractError("max_runtime_sec out of bounds (0..600]")
        if not isinstance(self.freshness_requirement, Freshness):
            raise ContractError("freshness_requirement must be a Freshness")
        return self


# ── result parts ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Citation:
    url: str
    host: str
    title: str
    source_tier: SourceTier
    retrieval_ts: float
    publication_ts: float | None = None

    def as_dict(self) -> dict:
        return {
            "url": self.url, "host": self.host, "title": self.title,
            "source_tier": self.source_tier.name,
            "retrieval_ts": self.retrieval_ts, "publication_ts": self.publication_ts,
        }


@dataclass(frozen=True)
class ExtractedFact:
    statement: str
    group: FactGroup
    source_url: str
    source_host: str
    source_tier: SourceTier
    retrieval_ts: float
    publication_ts: float | None = None
    value: str = ""                      # optional structured value (never a canonical price)
    provenance: Provenance = Provenance.BROWSER_DERIVED
    data_domain: DataDomain = DataDomain.WEB_INTELLIGENCE
    confidence: float = 0.0
    freshness: Freshness = Freshness.UNKNOWN
    evidence_ref: str = ""
    independently_confirmed: bool = False

    def validate(self) -> "ExtractedFact":
        # Fail-closed authority invariant: a browser-derived fact can NEVER be
        # canonical market data. This is the guard that keeps a scraped number
        # out of the point-in-time market_data plane.
        if self.provenance == Provenance.BROWSER_DERIVED and self.data_domain == DataDomain.MARKET_DATA:
            raise ContractError("browser-derived fact cannot be MARKET_DATA (authority boundary)")
        if not self.source_url or not self.source_host:
            raise ContractError("every fact requires a source URL + host")
        if not isinstance(self.source_tier, SourceTier):
            raise ContractError("source_tier must be a SourceTier")
        return self

    def as_dict(self) -> dict:
        return {
            "statement": self.statement, "group": self.group.value, "value": self.value,
            "source_url": self.source_url, "source_host": self.source_host,
            "source_tier": self.source_tier.name, "publication_ts": self.publication_ts,
            "retrieval_ts": self.retrieval_ts, "provenance": self.provenance.value,
            "data_domain": self.data_domain.value, "confidence": round(self.confidence, 3),
            "freshness": self.freshness.value, "evidence_ref": self.evidence_ref,
            "independently_confirmed": self.independently_confirmed,
        }


@dataclass
class ResearchResult:
    mission_id: str
    mission_type: MissionType
    status: ResearchStatus
    started_at: float
    completed_at: float = 0.0
    sources: list[Citation] = field(default_factory=list)
    extracted_facts: list[ExtractedFact] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0
    browser_trace_id: str = ""
    resource: dict = field(default_factory=dict)   # runtime_sec, pages_fetched, peak_rss_mb, cleanup

    def grouped(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {g.value: [] for g in FactGroup}
        for f in self.extracted_facts:
            out[f.group.value].append(f.as_dict())
        out["CONTRADICTIONS"] = list(self.contradictions)
        out["FRESHNESS_WARNINGS"] = [w for w in self.warnings if "stale" in w.lower() or "fresh" in w.lower()]
        return out

    def validate(self) -> "ResearchResult":
        if not self.mission_id:
            raise ContractError("result.mission_id required")
        for f in self.extracted_facts:
            f.validate()
        return self

    def as_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "mission_id": self.mission_id, "mission_type": self.mission_type.value,
            "status": self.status.value, "started_at": self.started_at,
            "completed_at": self.completed_at,
            "sources": [c.as_dict() for c in self.sources],
            "extracted_facts": [f.as_dict() for f in self.extracted_facts],
            "contradictions": list(self.contradictions), "warnings": list(self.warnings),
            "confidence": round(self.confidence, 3), "browser_trace_id": self.browser_trace_id,
            "resource": dict(self.resource), "grouped": self.grouped(),
            "authority": dict(AUTHORITY),
        }


# ── provider interface ───────────────────────────────────────────────────────
@dataclass(frozen=True)
class FetchedPage:
    """What the governed browser hands back — safe, redacted, read-only."""
    url: str
    final_origin: str
    title: str
    content: str
    status: str                      # succeeded | failed | denied | blocked
    injection_hits: tuple[str, ...] = ()
    retrieval_ts: float = field(default_factory=time.time)
    error_category: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "succeeded"


class BrowserResearchProvider(ABC):
    """Narrow read-only acquisition surface over the governed browser.

    Implementations MUST route through ``saathi.browser.GovernedBrowser`` (which
    enforces domain policy, SSRF blocking, prompt-injection detection, and the
    ExecutionGateway browser boundary). They MUST NOT construct trade/broker
    intents, call ExecutionGateway.execute, or write canonical market_data.
    """

    @abstractmethod
    def fetch(self, url: str, *, mission_id: str, actor: str = "user:owner",
              selector: str = "", timeout: int = 30) -> FetchedPage:
        ...

    @abstractmethod
    def cleanup(self) -> dict:
        """Shut the browser down after a mission; return cleanup evidence."""
        ...
