"""Phase 7/8 — NEPSE_DAILY_INTELLIGENCE mission (Tier-1 official only, read-only).

Collects official NEPSE / SEBON / NRB / CDSC notices and listed-company
announcements, extracts them as grouped ``ExtractedFact`` (OFFICIAL_NOTICES,
CORPORATE_ACTIONS, REGULATORY, COMPANY_EVENTS, MARKET_CONTEXT) with provenance
``BROWSER_DERIVED`` and per-fact freshness. No secondary news in v1. No numeric
value is ever promoted to canonical MARKET_DATA.
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Callable

from saathi.browser_research.contract import (
    Citation, ExtractedFact, FactGroup, FetchedPage, MissionType,
    Provenance, ResearchRequest, ResearchResult, ResearchStatus,
)
from saathi.browser_research.freshness import Freshness, classify_freshness, meets_requirement
from saathi.browser_research.provider import BrowserResearchProvider
from saathi.browser_research.tiers import SourceTier, classify_source, host_of

# Tier-1 official seed URLs for a daily sweep (public, read-only).
NEPSE_SEED_URLS: tuple[str, ...] = (
    "https://www.nepalstock.com/",
    "https://www.sebon.gov.np/",
    "https://www.nrb.org.np/",
    "https://www.cdsc.com.np/",
)

_MAX_FACTS_PER_PAGE = 40
_MIN_LINE = 12          # ignore nav/label fragments shorter than this

# group keyword routing (checked in order; first match wins)
_GROUP_KEYWORDS: tuple[tuple[FactGroup, tuple[str, ...]], ...] = (
    (FactGroup.CORPORATE_ACTIONS,
     ("dividend", "bonus share", "bonus shares", "right share", "rights share",
      "rights issue", "right issue", "book close", "auction", "buyback")),
    (FactGroup.COMPANY_EVENTS,
     ("agm", "annual general meeting", "sgm", "quarterly report", "quarterly result",
      "annual report", "financial result", "unaudited", "audited financial")),
    (FactGroup.REGULATORY,
     ("sebon", "nrb", "nepal rastra bank", "directive", "circular", "regulation",
      "guideline", "monetary policy", "amendment", "bylaw", "policy")),
    (FactGroup.MARKET_CONTEXT,
     ("nepse index", "turnover", "market summary", "index closed", "market capitalization",
      "trading halt", "floorsheet")),
    (FactGroup.OFFICIAL_NOTICES,
     ("notice", "notification", "announcement", "press release", "publication")),
)

# AD date patterns only. Nepali BS dates are NOT converted (kept UNKNOWN) to
# avoid publishing a wrong publication time.
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_ISO_RE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
_DMY_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(20\d{2})\b")
_MDY_RE = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(20\d{2})\b")


def _parse_ad_date(text: str) -> float | None:
    """Best-effort AD publication timestamp; None if not confidently AD-dated."""
    m = _ISO_RE.search(text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = _DMY_RE.search(text)
        if m:
            d, mon, y = int(m.group(1)), m.group(2)[:3].lower(), int(m.group(3))
            mo = _MONTHS.get(mon, 0)
        else:
            m = _MDY_RE.search(text)
            if not m:
                return None
            mon, d, y = m.group(1)[:3].lower(), int(m.group(2)), int(m.group(3))
            mo = _MONTHS.get(mon, 0)
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    try:
        import datetime as _dt
        return _dt.datetime(y, mo, d, tzinfo=_dt.timezone.utc).timestamp()
    except (ValueError, OverflowError):
        return None


def _route_group(line_low: str) -> FactGroup | None:
    for group, keys in _GROUP_KEYWORDS:
        if any(k in line_low for k in keys):
            return group
    return None


def _tier_confidence(tier: SourceTier, fresh: Freshness) -> float:
    base = {SourceTier.TIER_1_OFFICIAL: 0.85, SourceTier.TIER_2_PRIMARY_DATA: 0.65,
            SourceTier.TIER_3_REPUTABLE_NEWS: 0.45}.get(tier, 0.2)
    penalty = {Freshness.STALE: 0.25, Freshness.UNKNOWN: 0.15}.get(fresh, 0.0)
    return max(0.05, round(base - penalty, 3))


def extract_facts(page: FetchedPage, *, now: float) -> list[ExtractedFact]:
    """Pure extraction from one fetched page. No network, no side effects."""
    if not page.ok or not page.content:
        return []
    host = page.final_origin.split("://")[-1] if page.final_origin else host_of(page.url)
    tier = classify_source(page.url)
    facts: list[ExtractedFact] = []
    seen: set[str] = set()
    for raw in page.content.splitlines():
        line = raw.strip()
        if len(line) < _MIN_LINE:
            continue
        # Nav menus / footers dump long unpunctuated blobs — real notices are
        # short. And a corporate action / result / market line without a single
        # digit is almost always a navigation label, not a notice.
        if len(line) > 220:
            continue
        low = line.lower()
        group = _route_group(low)
        if group is None:
            continue
        if group in (FactGroup.CORPORATE_ACTIONS, FactGroup.COMPANY_EVENTS,
                     FactGroup.MARKET_CONTEXT) and not any(ch.isdigit() for ch in line):
            continue
        key = low[:120]
        if key in seen:
            continue
        seen.add(key)
        pub = _parse_ad_date(line)
        fresh = classify_freshness(pub, now=now)
        facts.append(ExtractedFact(
            statement=line[:280],
            group=group,
            source_url=page.url,
            source_host=host,
            source_tier=tier,
            retrieval_ts=page.retrieval_ts,
            publication_ts=pub,
            provenance=Provenance.BROWSER_DERIVED,
            confidence=_tier_confidence(tier, fresh),
            freshness=fresh,
        ).validate())
        if len(facts) >= _MAX_FACTS_PER_PAGE:
            break
    return facts


_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_SYMBOL_RE = re.compile(r"\b([A-Z]{3,10})\b")
_ACTIONS = ("dividend", "bonus", "right")


def _contradictions(facts: list[ExtractedFact]) -> list[str]:
    """Same (symbol, action) reported with conflicting percentages across sources."""
    buckets: dict[tuple[str, str], dict[str, set[str]]] = {}
    for f in facts:
        if f.group != FactGroup.CORPORATE_ACTIONS:
            continue
        low = f.statement.lower()
        action = next((a for a in _ACTIONS if a in low), "")
        sym_m = _SYMBOL_RE.search(f.statement)
        pcts = _PCT_RE.findall(f.statement)
        if not action or not sym_m or not pcts:
            continue
        key = (sym_m.group(1), action)
        for p in pcts:
            buckets.setdefault(key, {}).setdefault(p, set()).add(f.source_host)
    out: list[str] = []
    for (sym, action), by_pct in buckets.items():
        if len(by_pct) >= 2:
            detail = "; ".join(f"{pct}% ({', '.join(sorted(hosts))})"
                               for pct, hosts in sorted(by_pct.items()))
            out.append(f"{sym} {action}: conflicting values — {detail}")
    return out


def run_nepse_mission(
    provider: BrowserResearchProvider,
    request: ResearchRequest,
    *,
    seed_urls: tuple[str, ...] | None = None,
    now: Callable[[], float] | float = time.time,
) -> ResearchResult:
    """Execute the bounded Tier-1 NEPSE sweep and build a validated result."""
    request.validate()
    now_fn = now if callable(now) else (lambda: now)
    started = now_fn()
    trace = uuid.uuid4().hex[:16]
    urls = seed_urls or NEPSE_SEED_URLS

    result = ResearchResult(
        mission_id=request.mission_id,
        mission_type=MissionType.NEPSE_DAILY_INTELLIGENCE,
        status=ResearchStatus.RUNNING,
        started_at=started,
        browser_trace_id=trace,
    )

    fetched = 0
    for url in urls:
        if fetched >= request.max_pages:
            result.warnings.append(f"max_pages reached ({request.max_pages}); some sources skipped")
            break
        # Official-only gate (Phase 7): never fetch a non-Tier-1 host in v1.
        if classify_source(url) != SourceTier.TIER_1_OFFICIAL:
            result.warnings.append(f"skipped non-official source: {host_of(url)}")
            continue
        page = provider.fetch(url, mission_id=request.mission_id, actor=request.actor)
        fetched += 1
        if page.status == "denied":
            result.warnings.append(f"domain denied by policy: {host_of(url)}")
            continue
        if page.status == "blocked":
            result.warnings.append(f"resource bound hit fetching {host_of(url)}: {page.error_category}")
            break
        if not page.ok:
            result.warnings.append(f"fetch failed: {host_of(url)} ({page.error_category})")
            continue
        if page.injection_hits:
            # Page text is data; injection markers are recorded, never executed.
            result.warnings.append(
                f"prompt-injection markers ignored on {host_of(url)}: {','.join(page.injection_hits)}")
        result.sources.append(Citation(
            url=page.url, host=page.final_origin.split('://')[-1] or host_of(page.url),
            title=page.title, source_tier=classify_source(page.url),
            retrieval_ts=page.retrieval_ts,
        ))
        result.extracted_facts.extend(extract_facts(page, now=now_fn()))

    # Freshness warnings
    stale = [f for f in result.extracted_facts if f.freshness == Freshness.STALE]
    if stale:
        result.warnings.append(f"{len(stale)} facts are STALE (>=7d)")
    if request.freshness_requirement != Freshness.UNKNOWN:
        unmet = [f for f in result.extracted_facts
                 if not meets_requirement(f.freshness, request.freshness_requirement)]
        if unmet:
            result.warnings.append(
                f"{len(unmet)} facts do not meet freshness requirement "
                f"{request.freshness_requirement.value}")

    result.contradictions = _contradictions(result.extracted_facts)
    result.completed_at = now_fn()
    if result.extracted_facts:
        result.confidence = round(
            sum(f.confidence for f in result.extracted_facts) / len(result.extracted_facts), 3)
        result.status = ResearchStatus.COMPLETE if result.sources else ResearchStatus.PARTIAL
    else:
        result.status = ResearchStatus.PARTIAL if result.sources else ResearchStatus.FAILED
    return result.validate()
