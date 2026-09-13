"""M — RESEARCH_INTELLIGENCE_SURFACE — read-only synthesis over existing evidence.

Projects existing ExtractedFacts + ingested documents into a normalized event
model and a snapshot/daily-brief consumed by Central Command, chat, and voice.
Deterministic first (works with no model). ZERO write authority: no gateway,
Trading Guardian, broker, portfolio, market_data, or orders. Reuses source
tiering, freshness, reconciliation, and evidence — no second research system.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum

from saathi.browser_research.contract import ExtractedFact, FactGroup
from saathi.browser_research.freshness import Freshness
from saathi.browser_research.reconciliation import (
    ArbitrationOutcome, Observation, arbitrate_event,
)
from saathi.browser_research.tiers import SourceTier

SNAPSHOT_SCHEMA = "research_intelligence.v1"


class ResearchEventType(str, Enum):
    DIVIDEND = "DIVIDEND"
    BONUS_SHARE = "BONUS_SHARE"
    RIGHTS_ISSUE = "RIGHTS_ISSUE"
    AGM = "AGM"
    BOOK_CLOSURE = "BOOK_CLOSURE"
    RESULT = "RESULT"
    LISTING = "LISTING"
    DELISTING = "DELISTING"
    SUSPENSION = "SUSPENSION"
    REGULATORY = "REGULATORY"
    MONETARY_POLICY = "MONETARY_POLICY"
    MARKET_NOTICE = "MARKET_NOTICE"
    COMPANY_ANNOUNCEMENT = "COMPANY_ANNOUNCEMENT"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    MACRO_EVENT = "MACRO_EVENT"
    OTHER = "OTHER"


class ContradictionState(str, Enum):
    NONE = "NONE"
    OFFICIAL_SOURCE_WINS = "OFFICIAL_SOURCE_WINS"
    UNCONFIRMED_MULTI_SOURCE = "UNCONFIRMED_MULTI_SOURCE"


# (event type, keyword) routing within a fact group — only classify with evidence.
_TYPE_KEYWORDS: tuple[tuple[ResearchEventType, tuple[str, ...]], ...] = (
    (ResearchEventType.DIVIDEND, ("dividend",)),
    (ResearchEventType.BONUS_SHARE, ("bonus",)),
    (ResearchEventType.RIGHTS_ISSUE, ("right share", "rights", "right issue")),
    (ResearchEventType.BOOK_CLOSURE, ("book close", "book closure")),
    (ResearchEventType.AGM, ("agm", "annual general meeting", "sgm")),
    (ResearchEventType.RESULT, ("quarterly", "annual report", "financial result", "audited", "unaudited")),
    (ResearchEventType.DELISTING, ("delist",)),
    (ResearchEventType.LISTING, ("listing",)),
    (ResearchEventType.SUSPENSION, ("suspension", "suspend", "halt", "shut down", "shutdown")),
    (ResearchEventType.MONETARY_POLICY, ("monetary policy",)),
    (ResearchEventType.SECURITY_INCIDENT, ("breach", "hack", "exploit", "incident")),
)

_FRESH_RANK = {Freshness.REALTIME: 0, Freshness.NEAR_REALTIME: 1, Freshness.TODAY: 2,
               Freshness.RECENT: 3, Freshness.STALE: 4, Freshness.UNKNOWN: 5}


def classify_event_type(fact: ExtractedFact) -> ResearchEventType:
    low = fact.statement.lower()
    for et, keys in _TYPE_KEYWORDS:
        if any(k in low for k in keys):
            return et
    # fall back to the group (still evidence-backed, never guessed beyond group)
    return {
        FactGroup.CORPORATE_ACTIONS: ResearchEventType.COMPANY_ANNOUNCEMENT,
        FactGroup.COMPANY_EVENTS: ResearchEventType.COMPANY_ANNOUNCEMENT,
        FactGroup.REGULATORY: ResearchEventType.REGULATORY,
        FactGroup.MARKET_CONTEXT: ResearchEventType.MARKET_NOTICE,
        FactGroup.OFFICIAL_NOTICES: ResearchEventType.MARKET_NOTICE,
    }.get(fact.group, ResearchEventType.OTHER)


@dataclass
class ResearchEvent:
    event_id: str
    event_type: ResearchEventType
    market: str
    headline: str
    symbol: str = ""
    issuer: str = ""
    summary: str = ""
    event_date_raw: str = ""
    event_date_normalized: float | None = None
    source_tier: SourceTier = SourceTier.TIER_6_UNKNOWN
    freshness: Freshness = Freshness.UNKNOWN
    confidence: float = 0.0
    contradiction_state: ContradictionState = ContradictionState.NONE
    contradiction_note: str = ""
    evidence_refs: list = field(default_factory=list)
    document_refs: list = field(default_factory=list)
    research_priority: float = 0.0
    portfolio_relevant: bool = False
    status: str = "OK"

    def as_dict(self) -> dict:
        return {
            "event_id": self.event_id, "event_type": self.event_type.value,
            "market": self.market, "headline": self.headline, "symbol": self.symbol,
            "issuer": self.issuer, "summary": self.summary,
            "event_date_raw": self.event_date_raw,
            "event_date_normalized": self.event_date_normalized,
            "source_tier": self.source_tier.name, "freshness": self.freshness.value,
            "confidence": round(self.confidence, 3),
            "contradiction_state": self.contradiction_state.value,
            "contradiction_note": self.contradiction_note,
            "evidence_refs": list(self.evidence_refs), "document_refs": list(self.document_refs),
            "research_priority": round(self.research_priority, 3),
            "portfolio_relevant": self.portfolio_relevant, "status": self.status,
        }


def _cluster_key(f: ExtractedFact) -> str:
    et = classify_event_type(f)
    day = ""
    if f.publication_ts:
        day = time.strftime("%Y-%m-%d", time.gmtime(f.publication_ts))
    ident = (f.value or "").upper()   # symbol when resolved
    if not ident:
        # no symbol → fingerprint the headline so distinct notices stay distinct
        ident = hashlib.sha256(f.statement.lower().strip().encode()).hexdigest()[:10]
    return f"{et.value}|{ident}|{day}"


_PCT = __import__("re").compile(r"(\d+(?:\.\d+)?)\s*%")


def _contradiction(facts: list[ExtractedFact]) -> tuple[ContradictionState, str]:
    """Reuse reconciliation over a cluster's sources (Phase 6)."""
    obs = []
    for f in facts:
        pct = _PCT.findall(f.statement)
        obs.append(Observation(statement=f.statement, source_host=f.source_host,
                               source_tier=f.source_tier,
                               provenance=f.provenance, value=(pct[0] + "%" if pct else "")))
    vals = {o.value for o in obs if o.value}
    if len(vals) < 2:
        return ContradictionState.NONE, ""
    res = arbitrate_event(obs)
    if res.outcome == ArbitrationOutcome.OFFICIAL_CONFIRMS:
        return ContradictionState.OFFICIAL_SOURCE_WINS, (
            f"CONFIRMED {res.canonical_value} ({','.join(res.supporting_hosts)}); conflicting: {sorted(vals)}")
    if res.outcome == ArbitrationOutcome.UNCONFIRMED_MULTI_SOURCE:
        return ContradictionState.UNCONFIRMED_MULTI_SOURCE, f"conflicting values {sorted(vals)}, no official"
    return ContradictionState.NONE, ""


def _research_priority(ev: ResearchEvent, evidence_count: int, has_official_doc: bool) -> float:
    """Deterministic, NON-trading. Named RESEARCH_PRIORITY on purpose."""
    tier_w = {SourceTier.TIER_1_OFFICIAL: 1.0, SourceTier.TIER_2_PRIMARY_DATA: 0.7,
              SourceTier.TIER_3_REPUTABLE_NEWS: 0.5}.get(ev.source_tier, 0.2)
    fresh_w = {Freshness.REALTIME: 1.0, Freshness.NEAR_REALTIME: 0.9, Freshness.TODAY: 0.8,
               Freshness.RECENT: 0.6, Freshness.STALE: 0.2, Freshness.UNKNOWN: 0.3}[ev.freshness]
    cat_w = {ResearchEventType.DIVIDEND: 0.9, ResearchEventType.RIGHTS_ISSUE: 0.9,
             ResearchEventType.BONUS_SHARE: 0.85, ResearchEventType.RESULT: 0.8,
             ResearchEventType.MONETARY_POLICY: 0.85, ResearchEventType.DELISTING: 0.8,
             ResearchEventType.SUSPENSION: 0.8, ResearchEventType.REGULATORY: 0.7,
             ResearchEventType.AGM: 0.6}.get(ev.event_type, 0.5)
    score = 0.35 * tier_w + 0.25 * fresh_w + 0.20 * cat_w + 0.10 * min(1.0, evidence_count / 3)
    if has_official_doc:
        score += 0.05
    if ev.contradiction_state == ContradictionState.UNCONFIRMED_MULTI_SOURCE:
        score += 0.05      # needs review = worth surfacing
    if ev.portfolio_relevant:
        score += 0.05
    return round(min(1.0, score), 3)


@dataclass
class ResearchIntelligenceSnapshot:
    snapshot_id: str
    generated_at: float
    market: str
    events: list = field(default_factory=list)            # ResearchEvent
    documents: list = field(default_factory=list)         # doc dicts
    source_health: dict = field(default_factory=dict)
    contradictions: list = field(default_factory=list)
    freshness_warnings: list = field(default_factory=list)
    source_distribution: dict = field(default_factory=dict)
    confidence: float = 0.0
    evidence_refs: list = field(default_factory=list)
    limitations: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "schema": SNAPSHOT_SCHEMA, "snapshot_id": self.snapshot_id,
            "generated_at": self.generated_at, "market": self.market,
            "events": [e.as_dict() for e in self.events],
            "documents": list(self.documents), "source_health": dict(self.source_health),
            "contradictions": list(self.contradictions),
            "freshness_warnings": list(self.freshness_warnings),
            "source_distribution": dict(self.source_distribution),
            "confidence": round(self.confidence, 3), "evidence_refs": list(self.evidence_refs),
            "limitations": list(self.limitations),
        }


def build_snapshot(facts, documents=None, *, market: str = "NEPSE", now: float,
                   holdings: set[str] | None = None, source_health: dict | None = None,
                   limitations: list[str] | None = None) -> ResearchIntelligenceSnapshot:
    documents = list(documents or [])
    holdings = {h.upper() for h in (holdings or set())}
    clusters: dict[str, list[ExtractedFact]] = {}
    for f in facts:
        clusters.setdefault(_cluster_key(f), []).append(f)

    docs_by_symbol: dict[str, list[dict]] = {}
    for d in documents:
        sym = str(d.get("symbol") or "").upper()
        if sym:
            docs_by_symbol.setdefault(sym, []).append(d)

    events: list[ResearchEvent] = []
    all_refs: set[str] = set()
    for key, cfacts in clusters.items():
        best = sorted(cfacts, key=lambda f: (f.source_tier, _FRESH_RANK[f.freshness]))[0]
        et = classify_event_type(best)
        cstate, cnote = _contradiction(cfacts)
        refs = [f.evidence_ref for f in cfacts if f.evidence_ref]
        all_refs.update(refs)
        sym = (best.value or "").upper()
        drefs = [dd.get("sha256", "") for dd in docs_by_symbol.get(sym, [])]
        ev = ResearchEvent(
            event_id=hashlib.sha256(key.encode()).hexdigest()[:16], event_type=et,
            market=market, headline=best.statement[:200], symbol=sym,
            summary=best.summary[:240] if hasattr(best, "summary") else best.statement[:240],
            event_date_raw=(time.strftime("%Y-%m-%d", time.gmtime(best.publication_ts)) if best.publication_ts else ""),
            event_date_normalized=best.publication_ts,
            source_tier=min(f.source_tier for f in cfacts),
            freshness=sorted(cfacts, key=lambda f: _FRESH_RANK[f.freshness])[0].freshness,
            confidence=round(sum(f.confidence for f in cfacts) / len(cfacts), 3),
            contradiction_state=cstate, contradiction_note=cnote,
            evidence_refs=refs, document_refs=[r for r in drefs if r],
            portfolio_relevant=bool(sym and sym in holdings),
        )
        ev.research_priority = _research_priority(ev, len(cfacts), bool(ev.document_refs))
        events.append(ev)

    events.sort(key=lambda e: e.research_priority, reverse=True)
    dist: dict[str, int] = {}
    for e in events:
        dist[e.source_tier.name] = dist.get(e.source_tier.name, 0) + 1
    contradictions = [f"{e.headline[:60]}: {e.contradiction_note}"
                      for e in events if e.contradiction_state != ContradictionState.NONE]
    stale = [e.headline[:60] for e in events if e.freshness in (Freshness.STALE, Freshness.UNKNOWN)]
    conf = round(sum(e.confidence for e in events) / len(events), 3) if events else 0.0
    return ResearchIntelligenceSnapshot(
        snapshot_id=hashlib.sha256(f"{market}{now}{len(events)}".encode()).hexdigest()[:16],
        generated_at=now, market=market, events=events, documents=documents,
        source_health=dict(source_health or {}), contradictions=contradictions,
        freshness_warnings=[f"{n}: stale/unknown date" for n in stale],
        source_distribution=dist, confidence=conf, evidence_refs=sorted(all_refs),
        limitations=list(limitations or []),
    )


# ── deterministic synthesis (NO trade directives) ────────────────────────────
_FORBIDDEN = ("buy", "sell", "enter", "exit", "target", "position size", "long ", "short ")


def deterministic_summary(ev: ResearchEvent) -> dict:
    why = {
        ResearchEventType.DIVIDEND: "Cash/again distribution declared by the issuer.",
        ResearchEventType.BONUS_SHARE: "Bonus shares proposed/declared.",
        ResearchEventType.RIGHTS_ISSUE: "Rights issue announced.",
        ResearchEventType.AGM: "Annual general meeting scheduled.",
        ResearchEventType.RESULT: "Financial results published.",
        ResearchEventType.MONETARY_POLICY: "Central-bank monetary policy development.",
        ResearchEventType.REGULATORY: "Regulatory development.",
        ResearchEventType.DELISTING: "Instrument delisting.",
        ResearchEventType.SUSPENSION: "Trading/operations affected per official notice.",
    }.get(ev.event_type, "Official notice/announcement.")
    return {
        "headline": ev.headline, "why_it_matters": why,
        "event_type": ev.event_type.value, "symbol": ev.symbol,
        "source_authority": ev.source_tier.name, "freshness": ev.freshness.value,
        "confidence": ev.confidence, "evidence_count": len(ev.evidence_refs),
        "contradiction": ev.contradiction_state.value,
    }


def daily_brief(snap: ResearchIntelligenceSnapshot) -> dict:
    def by(*types):
        return [deterministic_summary(e) for e in snap.events if e.event_type in types]
    return {
        "market": snap.market, "generated_at": snap.generated_at,
        "what_changed": [deterministic_summary(e) for e in snap.events[:5]],
        "corporate_actions": by(ResearchEventType.DIVIDEND, ResearchEventType.BONUS_SHARE,
                                ResearchEventType.RIGHTS_ISSUE, ResearchEventType.BOOK_CLOSURE),
        "regulatory": by(ResearchEventType.REGULATORY),
        "official_notices": by(ResearchEventType.MARKET_NOTICE, ResearchEventType.COMPANY_ANNOUNCEMENT),
        "company_disclosures": by(ResearchEventType.RESULT, ResearchEventType.AGM,
                                  ResearchEventType.LISTING, ResearchEventType.DELISTING,
                                  ResearchEventType.SUSPENSION),
        "monetary_macro": by(ResearchEventType.MONETARY_POLICY, ResearchEventType.MACRO_EVENT),
        "contradictions_requiring_review": list(snap.contradictions),
        "stale_or_unavailable_sources": list(snap.freshness_warnings)
        + [k for k, v in snap.source_health.items() if isinstance(v, dict)
           and v.get("status") not in ("AVAILABLE", None)],
        "evidence_refs": list(snap.evidence_refs),
    }


def optional_model_summary(snap: ResearchIntelligenceSnapshot, *, router=None, summarizer=None) -> dict:
    """Deterministic view is authoritative; model summary is optional/downstream."""
    available = False
    if router is not None:
        try:
            from saathi.model_router import ModelLabel
            available = router.best(getattr(ModelLabel, "SUMMARY", next(iter(ModelLabel)))) is not None
        except Exception:
            available = False
    if summarizer is None or (router is not None and not available):
        return {"status": "MODEL_UNAVAILABLE", "deterministic_brief": daily_brief(snap)}
    try:
        text = summarizer(daily_brief(snap))
        return {"status": "OK", "summary": str(text)[:4000]}
    except Exception as e:
        return {"status": "MODEL_UNAVAILABLE", "error": type(e).__name__,
                "deterministic_brief": daily_brief(snap)}


# ── chat / voice (same evidence model) ───────────────────────────────────────
def chat_answer(snap: ResearchIntelligenceSnapshot, query: str) -> dict:
    q = (query or "").lower()
    if not snap.events:
        return {"answer": "No research evidence available for this market yet.", "events": [], "supported": False}
    # "show <SYMBOL> ..."
    import re as _re
    syms = [s for s in _re.findall(r"\b([A-Z]{3,10})\b", query or "") if s not in ("NEPSE", "SEBON", "NRB")]
    if syms:
        sym = syms[0]
        matches = [e for e in snap.events if e.symbol == sym]
        if not matches:
            return {"answer": f"No official evidence found for {sym}.", "events": [], "supported": False}
        return {"answer": f"{len(matches)} event(s) for {sym}.",
                "events": [e.as_dict() for e in matches], "supported": True}
    if "contradict" in q or "why" in q:
        c = [e.as_dict() for e in snap.events if e.contradiction_state != ContradictionState.NONE]
        return {"answer": f"{len(c)} event(s) have conflicting sources.",
                "events": c, "supported": True}
    if "nrb" in q or "policy" in q or "monetary" in q:
        m = [e.as_dict() for e in snap.events if e.event_type in
             (ResearchEventType.MONETARY_POLICY, ResearchEventType.REGULATORY)]
        return {"answer": f"{len(m)} regulatory/monetary event(s).", "events": m, "supported": bool(m)}
    # default: "what changed"
    top = snap.events[: 5]
    return {"answer": f"{len(snap.events)} official events; showing top {len(top)} by research priority.",
            "events": [e.as_dict() for e in top], "supported": True}


def voice_answer(snap: ResearchIntelligenceSnapshot) -> str:
    if not snap.events:
        return "No new official research events."
    top = snap.events[0]
    return (f"{len(snap.events)} official events. Highest priority: "
            f"{top.event_type.value.replace('_', ' ').lower()}"
            + (f" for {top.symbol}" if top.symbol else "")
            + f", {top.freshness.value.lower()}, from a {top.source_tier.name.replace('_', ' ').lower()} source.")


def central_command_projection(snap: ResearchIntelligenceSnapshot) -> dict:
    new_today = sum(1 for e in snap.events if e.freshness in (Freshness.TODAY, Freshness.REALTIME, Freshness.NEAR_REALTIME))
    return {
        "read_only": True,
        "overview": {
            "market": snap.market, "events": len(snap.events), "new_today": new_today,
            "documents": len(snap.documents), "contradictions": len(snap.contradictions),
            "stale_sources": len(snap.freshness_warnings),
            "official_events": snap.source_distribution.get("TIER_1_OFFICIAL", 0),
            "confidence": snap.confidence,
        },
        "latest_events": [{
            "event_id": e.event_id,
            "headline": e.headline[:80], "type": e.event_type.value, "symbol": e.symbol,
            "date": e.event_date_raw, "authority": e.source_tier.name,
            "confidence": e.confidence, "freshness": e.freshness.value,
            "evidence_count": len(e.evidence_refs), "priority": e.research_priority,
            "portfolio_relevant": e.portfolio_relevant,
        } for e in snap.events[:12]],
        "source_health": snap.source_health,
        "limitations": snap.limitations,
    }


# ── projection over the EXISTING evidence store (no re-collection) ────────────
def _rows_to_facts(rows) -> list[ExtractedFact]:
    from saathi.browser_research.contract import DataDomain, Provenance
    facts = []
    groups = {g.value for g in FactGroup}
    for r in rows:
        m = r.get("metrics", {})
        if r.get("director") not in groups:
            continue
        try:
            facts.append(ExtractedFact(
                statement=m.get("statement", ""), group=FactGroup(r["director"]),
                source_url=m.get("source_url", ""), source_host=m.get("source_host", ""),
                source_tier=SourceTier[m.get("source_tier", "TIER_6_UNKNOWN")],
                retrieval_ts=float(m.get("retrieval_ts") or 0.0),
                publication_ts=m.get("publication_ts"),
                value=m.get("value", ""), provenance=Provenance.BROWSER_DERIVED,
                data_domain=DataDomain.WEB_INTELLIGENCE,
                confidence=float(r.get("confidence") or 0.0),
                freshness=Freshness(m.get("freshness", "UNKNOWN")),
                evidence_ref=r.get("id", ""),
            ))
        except Exception:
            continue
    return facts


def build_from_evidence(store, *, market: str = "NEPSE", now: float | None = None,
                        holdings: set[str] | None = None, source_health: dict | None = None,
                        limit: int = 500) -> ResearchIntelligenceSnapshot:
    now = now if now is not None else time.time()
    fact_rows = store.query(department="browser_research", project=market, limit=limit)
    facts = _rows_to_facts(fact_rows)
    doc_rows = store.query(department="browser_research", project="nepse_document", limit=limit)
    documents = [{
        "sha256": d.get("metrics", {}).get("sha256", ""),
        "title": d.get("metrics", {}).get("title", ""),
        "source_url": d.get("metrics", {}).get("source_url", ""),
        "symbol": (d.get("metrics", {}).get("issuer", "") or "").upper(),
        "page_count": d.get("metrics", {}).get("page_count", 0),
        "status": d.get("status", ""),
    } for d in doc_rows]
    return build_snapshot(facts, documents, market=market, now=now, holdings=holdings,
                          source_health=source_health)


# ── unified source health (reuses endpoint_monitor + document statuses) ──────
def token_gated_documents(documents) -> list[str]:
    """NEPSE attachment host is token-gated; surface, never hide (Phase 23)."""
    out = []
    for d in (documents or []):
        url = str(d.get("source_url") or "")
        if "/api/nots/notice/file/" in url and d.get("status") in ("DOCUMENT_NOT_FOUND", "DOCUMENT_BLOCKED"):
            out.append(url)
    return out


def unify_source_health(*, nepse_capture=None, sebon_status: str = "UNKNOWN",
                        nrb_status: str = "UNKNOWN", documents=None) -> dict:
    health = {}
    if nepse_capture is not None:
        from saathi.browser_research.endpoint_monitor import health_from_capture
        health["nepse"] = health_from_capture(nepse_capture)
    else:
        health["nepse"] = {"status": "UNKNOWN"}
    health["sebon"] = {"status": sebon_status}
    health["nrb"] = {"status": nrb_status}
    tg = token_gated_documents(documents)
    ingested = [d for d in (documents or []) if d.get("status") == "DOCUMENT_OK"]
    health["documents"] = {
        "status": "AVAILABLE" if ingested else ("DEGRADED" if documents else "UNKNOWN"),
        "ingested": len(ingested),
        "token_gated": len(tg),
        "token_gated_note": "DOCUMENT_UNAVAILABLE_TOKEN_GATED" if tg else "",
    }
    return health
