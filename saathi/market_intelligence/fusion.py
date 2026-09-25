"""Phase 10/11/12/13 — deterministic fusion + MarketIntelligenceSnapshot + projections.

ResearchEvent (frozen) + canonical MarketData (point-in-time) + read-only portfolio
exposure + read-only risk context → CatalystEvent → snapshot. Deterministic, traceable,
point-in-time safe, LLM-free, degraded-capable, ZERO trade authority. Consumes the frozen
research surface via its public contract; never modifies it.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from saathi.browser_research.intelligence import ResearchEvent, ResearchIntelligenceSnapshot
from saathi.market_intelligence.catalyst import (
    CatalystEvent, CatalystPriority, MarketContextStatus, PortfolioContext,
    PortfolioContextStatus, RiskContext, RiskContextStatus, compute_priority,
)
from saathi.market_intelligence.market_reaction import compute_market_reaction

SNAPSHOT_SCHEMA = "market_intelligence.snapshot.v1"


def _portfolio_context(symbol: str, holdings, watchlist) -> PortfolioContext:
    if holdings is None and watchlist is None:
        return PortfolioContext(PortfolioContextStatus.PORTFOLIO_CONTEXT_UNAVAILABLE)
    sym = (symbol or "").upper()
    wl = {w.upper() for w in (watchlist or set())}
    h = {k.upper(): v for k, v in (holdings or {}).items()}
    if sym and sym in h:
        pos = h[sym] or {}
        return PortfolioContext(
            PortfolioContextStatus.OK, portfolio_relevant=True,
            watchlist_relevant=sym in wl,
            holding_quantity=str(pos.get("quantity", "")),
            portfolio_weight=str(pos.get("weight", "")),
            exposure_value=str(pos.get("value", "")))
    if sym and sym in wl:
        return PortfolioContext(PortfolioContextStatus.OK, watchlist_relevant=True)
    return PortfolioContext(PortfolioContextStatus.NOT_HELD)


def _risk_context(symbol: str, pctx: PortfolioContext) -> RiskContext:
    # Read-only projection from injected holdings ONLY — never invokes any Trading
    # Guardian executable/optimiser path.
    if not pctx.portfolio_relevant or pctx.status != PortfolioContextStatus.OK:
        return RiskContext(RiskContextStatus.RISK_CONTEXT_UNAVAILABLE)
    note = ""
    w = None
    try:
        w = float(str(pctx.portfolio_weight).rstrip("%")) if pctx.portfolio_weight else None
    except ValueError:
        w = None
    if w is not None and w >= 20.0:
        note = "high single-name concentration (>=20% weight)"
    return RiskContext(RiskContextStatus.OK, single_name_exposure=pctx.portfolio_weight,
                       concentration_note=note, event_proximity="event affects held name")


def fuse(event: ResearchEvent, *, reader=None, holdings=None, watchlist=None) -> CatalystEvent:
    mkt = compute_market_reaction(event.symbol, event.event_date_normalized, reader=reader)
    pctx = _portfolio_context(event.symbol, holdings, watchlist)
    rctx = _risk_context(event.symbol, pctx)
    cat = CatalystEvent(
        catalyst_id=hashlib.sha256(f"cat|{event.event_id}".encode()).hexdigest()[:16],
        research_event_id=event.event_id, event_type=event.event_type, symbol=event.symbol,
        headline=event.headline, event_date_raw=event.event_date_raw,
        publication_ts=event.event_date_normalized, source_tier=event.source_tier,
        freshness=event.freshness, confidence=event.confidence,
        contradiction_state=event.contradiction_state,
        evidence_refs=list(event.evidence_refs), document_refs=list(event.document_refs),
        market_context=mkt, portfolio_context=pctx, risk_context=rctx,
    )
    limits = []
    if mkt.status != MarketContextStatus.OK:
        limits.append(f"market:{mkt.status.value}")
    if pctx.status != PortfolioContextStatus.OK:
        limits.append(f"portfolio:{pctx.status.value}")
    if rctx.status != RiskContextStatus.OK:
        limits.append(f"risk:{rctx.status.value}")
    cat.limitations = limits
    cat.catalyst_priority, cat.priority_reasons = compute_priority(cat)
    return cat


@dataclass
class MarketIntelligenceSnapshot:
    schema: str
    generated_at: float
    market: str
    catalysts: list = field(default_factory=list)
    source_health: dict = field(default_factory=dict)
    market_data_health: dict = field(default_factory=dict)
    contradictions: list = field(default_factory=list)
    freshness_warnings: list = field(default_factory=list)
    evidence_refs: list = field(default_factory=list)
    limitations: list = field(default_factory=list)

    def high_priority(self):
        return [c for c in self.catalysts if c.catalyst_priority == CatalystPriority.HIGH]

    def portfolio_relevant(self):
        return [c for c in self.catalysts if c.portfolio_context.portfolio_relevant]

    def as_dict(self) -> dict:
        return {
            "schema": self.schema, "generated_at": self.generated_at, "market": self.market,
            "catalysts": [c.as_dict() for c in self.catalysts],
            "high_priority_count": len(self.high_priority()),
            "portfolio_relevant_count": len(self.portfolio_relevant()),
            "source_health": dict(self.source_health),
            "market_data_health": dict(self.market_data_health),
            "contradictions": list(self.contradictions),
            "freshness_warnings": list(self.freshness_warnings),
            "evidence_refs": list(self.evidence_refs), "limitations": list(self.limitations),
        }


def build_snapshot(research_snapshot: ResearchIntelligenceSnapshot, *, reader=None,
                   holdings=None, watchlist=None, now: float | None = None) -> MarketIntelligenceSnapshot:
    now = now if now is not None else time.time()
    catalysts = [fuse(e, reader=reader, holdings=holdings, watchlist=watchlist)
                 for e in research_snapshot.events]
    order = {CatalystPriority.HIGH: 0, CatalystPriority.MEDIUM: 1, CatalystPriority.LOW: 2}
    catalysts.sort(key=lambda c: (order[c.catalyst_priority], -(c.confidence or 0)))
    mkt_ok = sum(1 for c in catalysts if c.market_context.status == MarketContextStatus.OK)
    md_health = {
        "status": "AVAILABLE" if mkt_ok else "MARKET_DATA_UNAVAILABLE",
        "reader_present": reader is not None, "catalysts_with_market_context": mkt_ok,
        "note": "no live canonical NEPSE market-data feed" if not mkt_ok else "",
    }
    evidence = sorted({r for c in catalysts for r in c.evidence_refs})
    limitations = list(research_snapshot.limitations)
    if not mkt_ok:
        limitations.append("MARKET_DATA_UNAVAILABLE: catalysts carry event/evidence context only")
    if holdings is None and watchlist is None:
        limitations.append("PORTFOLIO_CONTEXT_UNAVAILABLE: no read-only holdings/watchlist supplied")
    return MarketIntelligenceSnapshot(
        schema=SNAPSHOT_SCHEMA, generated_at=now, market=research_snapshot.market,
        catalysts=catalysts, source_health=dict(research_snapshot.source_health),
        market_data_health=md_health, contradictions=list(research_snapshot.contradictions),
        freshness_warnings=list(research_snapshot.freshness_warnings),
        evidence_refs=evidence, limitations=limitations)


def build_from_store(store, *, market: str = "NEPSE", reader=None, holdings=None,
                     watchlist=None, now: float | None = None) -> MarketIntelligenceSnapshot:
    """Convenience: project over the frozen evidence store (read-only)."""
    from saathi.browser_research.intelligence import build_from_evidence
    now = now if now is not None else time.time()
    rs = build_from_evidence(store, market=market, now=now,
                             holdings={s.upper() for s in (holdings or {})})
    return build_snapshot(rs, reader=reader, holdings=holdings, watchlist=watchlist, now=now)


# ── Central Command / chat / voice projections (read-only, no trade language) ──
def central_command_projection(snap: MarketIntelligenceSnapshot) -> dict:
    return {
        "read_only": True, "market": snap.market, "generated_at": snap.generated_at,
        "overview": {
            "catalysts": len(snap.catalysts), "high_priority": len(snap.high_priority()),
            "portfolio_relevant": len(snap.portfolio_relevant()),
            "contradictions": len(snap.contradictions),
            "market_data": snap.market_data_health.get("status"),
        },
        "high_priority_catalysts": [{
            "catalyst_id": c.catalyst_id, "type": c.event_type.value, "symbol": c.symbol,
            "headline": c.headline[:90], "priority": c.catalyst_priority.value,
            "priority_reasons": c.priority_reasons, "freshness": c.freshness.value,
            "authority": c.source_tier.name, "market_reaction": c.market_context.status.value,
            "evidence_count": len(c.evidence_refs),
        } for c in snap.high_priority()[:12]],
        "source_health": snap.source_health, "market_data_health": snap.market_data_health,
        "limitations": snap.limitations,
    }


def chat_answer(snap: MarketIntelligenceSnapshot, query: str) -> dict:
    import re
    q = (query or "").lower()
    if not snap.catalysts:
        return {"answer": "No market catalysts available for this market yet.", "supported": False, "catalysts": []}
    syms = [s for s in re.findall(r"\b([A-Z]{3,10})\b", query or "") if s != "NEPSE"]
    if syms:
        sym = syms[0]
        m = [c for c in snap.catalysts if c.symbol == sym]
        if not m:
            return {"answer": f"No catalyst evidence found for {sym}.", "supported": False, "catalysts": []}
        c = m[0]
        mr = c.market_context
        reaction = (f"market reaction {mr.percentage_change}" if mr.status == MarketContextStatus.OK and mr.percentage_change
                    else f"market reaction {mr.status.value}")
        return {"answer": f"{len(m)} catalyst(s) for {sym}. Latest: {c.event_type.value} — {reaction}. "
                          f"(fact + evidence only; not investment advice)",
                "supported": True, "catalysts": [x.as_dict() for x in m[:5]]}
    if "portfolio" in q or "my holdings" in q or "affect" in q:
        pr = snap.portfolio_relevant()
        return {"answer": f"{len(pr)} catalyst(s) affect portfolio holdings."
                          + ("" if pr else " (no read-only holdings supplied)"),
                "supported": True, "catalysts": [c.as_dict() for c in pr[:5]]}
    if "why" in q and "priorit" in q:
        hp = snap.high_priority()
        if hp:
            return {"answer": f"Top catalyst is {hp[0].catalyst_priority.value} because: "
                              + "; ".join(hp[0].priority_reasons), "supported": True,
                    "catalysts": [hp[0].as_dict()]}
    hp = snap.high_priority() or snap.catalysts[:5]
    return {"answer": f"{len(snap.catalysts)} market events; {len(snap.high_priority())} high-priority "
                      f"by operator attention (FACT + MARKET REACTION + PORTFOLIO EXPOSURE; no trade advice).",
            "supported": True, "catalysts": [c.as_dict() for c in hp[:5]]}


def voice_answer(snap: MarketIntelligenceSnapshot) -> str:
    if not snap.catalysts:
        return "No new market catalysts."
    hp = snap.high_priority()
    if hp:
        c = hp[0]
        return (f"{len(snap.catalysts)} market events, {len(hp)} high priority. Top: "
                f"{c.event_type.value.replace('_',' ').lower()}"
                + (f" for {c.symbol}" if c.symbol else "") + ". Evidence-backed, not investment advice.")
    return f"{len(snap.catalysts)} market events, none high priority. Evidence-backed, not investment advice."
