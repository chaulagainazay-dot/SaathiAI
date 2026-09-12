"""Phase 5 — web vs API / official-vs-secondary arbitration (pure, deterministic).

Never overwrites stronger evidence with weaker. Authority order for a numeric
market value: canonical point-in-time API  >  everything browser-derived. For a
corporate/regulatory event: TIER_1 official filing  >  reputable news. Multiple
reputable sources with no official confirmation -> UNCONFIRMED_MULTI_SOURCE.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from saathi.browser_research.contract import DataDomain, Provenance
from saathi.browser_research.tiers import SourceTier


class ArbitrationOutcome(str, Enum):
    API_CANONICAL_WINS = "API_CANONICAL_WINS"          # market value: API beats browser
    OFFICIAL_CONFIRMS = "OFFICIAL_CONFIRMS"            # official filing confirms the event
    UNCONFIRMED_MULTI_SOURCE = "UNCONFIRMED_MULTI_SOURCE"
    SINGLE_SOURCE_UNCONFIRMED = "SINGLE_SOURCE_UNCONFIRMED"
    CONTRADICTION = "CONTRADICTION"


@dataclass(frozen=True)
class Observation:
    """One claim from one source. ``is_market_value`` marks a numeric quote."""
    statement: str
    source_host: str
    source_tier: SourceTier
    provenance: Provenance
    value: str = ""
    is_market_value: bool = False


@dataclass(frozen=True)
class CanonicalDatum:
    """A valid canonical point-in-time market_data value (from the API plane)."""
    value: str
    available: bool = True


@dataclass(frozen=True)
class ArbitrationResult:
    outcome: ArbitrationOutcome
    canonical_value: str          # the value SaathiOS should treat as canonical
    canonical_domain: DataDomain
    canonical_provenance: Provenance
    rule: str
    supporting_hosts: tuple[str, ...] = ()


def arbitrate_market_value(
    web_obs: Observation, canonical: CanonicalDatum | None
) -> ArbitrationResult:
    """A browser-reported market value never becomes canonical when the API has one."""
    if canonical is not None and canonical.available and str(canonical.value) != "":
        return ArbitrationResult(
            outcome=ArbitrationOutcome.API_CANONICAL_WINS,
            canonical_value=str(canonical.value),
            canonical_domain=DataDomain.MARKET_DATA,
            canonical_provenance=Provenance.API_CANONICAL,
            rule="canonical point-in-time market_data API outranks browser-derived value",
            supporting_hosts=(web_obs.source_host,),
        )
    # No canonical API value: the browser value stays WEB_INTELLIGENCE context —
    # it is NOT promoted to canonical market data (that needs a separate cert).
    return ArbitrationResult(
        outcome=ArbitrationOutcome.SINGLE_SOURCE_UNCONFIRMED,
        canonical_value="",
        canonical_domain=DataDomain.WEB_INTELLIGENCE,
        canonical_provenance=Provenance.BROWSER_DERIVED,
        rule="no canonical API value; browser value kept as web-intelligence only, not canonical",
        supporting_hosts=(web_obs.source_host,),
    )


def arbitrate_event(observations: list[Observation]) -> ArbitrationResult:
    """Corporate action / regulatory / company event across sources."""
    if not observations:
        return ArbitrationResult(
            ArbitrationOutcome.SINGLE_SOURCE_UNCONFIRMED, "",
            DataDomain.WEB_INTELLIGENCE, Provenance.BROWSER_DERIVED,
            "no observations", (),
        )
    officials = [o for o in observations if o.source_tier == SourceTier.TIER_1_OFFICIAL]
    hosts = tuple(sorted({o.source_host for o in observations}))
    if officials:
        return ArbitrationResult(
            outcome=ArbitrationOutcome.OFFICIAL_CONFIRMS,
            canonical_value=officials[0].value,
            canonical_domain=DataDomain.WEB_INTELLIGENCE,   # still not MARKET_DATA
            canonical_provenance=Provenance.BROWSER_DERIVED,
            rule="TIER_1 official filing outranks secondary sources",
            supporting_hosts=tuple(sorted({o.source_host for o in officials})),
        )
    reputable = [o for o in observations
                 if o.source_tier <= SourceTier.TIER_3_REPUTABLE_NEWS]
    distinct = {o.source_host for o in reputable}
    if len(distinct) >= 2:
        return ArbitrationResult(
            outcome=ArbitrationOutcome.UNCONFIRMED_MULTI_SOURCE,
            canonical_value="",
            canonical_domain=DataDomain.WEB_INTELLIGENCE,
            canonical_provenance=Provenance.BROWSER_DERIVED,
            rule="multiple reputable sources, no official confirmation",
            supporting_hosts=hosts,
        )
    return ArbitrationResult(
        outcome=ArbitrationOutcome.SINGLE_SOURCE_UNCONFIRMED,
        canonical_value="",
        canonical_domain=DataDomain.WEB_INTELLIGENCE,
        canonical_provenance=Provenance.BROWSER_DERIVED,
        rule="single unofficial source; not confirmed",
        supporting_hosts=hosts,
    )
