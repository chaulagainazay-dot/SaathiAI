"""Opportunity Intelligence Department (M5 Phase 2) — universal, not just investing.

Every discovered thing — a crypto IDO, a supplier, an open-source model, an
affiliate program, a trending IELTS topic — becomes ONE standardized
`Opportunity` object that the whole AI-OS consumes (AP-01). Discovery agents
scan; the pipeline normalizes → researches (via the Research Department) →
scores confidence → deduplicates → ranks. Nothing is ever thrown away:
**Opportunity Memory** keeps every opportunity alive so a project rejected in
January can be *resurrected* in March when its evidence improves.

Pipeline (each stage reusable):
    Scan → Normalize → Research → Confidence → Deduplicate → Rank
Downstream (Due Diligence → Simulation → Risk → Recommendation → Human
Approval → Execution → Learning) consumes the same ranked objects.

Deterministic core (AP-17); scanners / research / clock injected (AP-12).
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Callable


class OpportunityCategory(str, Enum):
    INVESTMENT = "investment"      # crypto, stocks, ETF, IPO, ICO, IDO, launchpad
    BUSINESS = "business"          # travel partnership, supplier, franchise, contract
    AI = "ai"                      # open model, renderer, voice, GitHub repo, MCP
    REVENUE = "revenue"            # affiliate, sponsor, client lead, consulting, course
    EDUCATION = "education"        # trending IELTS/blockchain topic, YT keyword


class OpportunityStatus(str, Enum):
    NEW = "new"
    RESEARCHED = "researched"
    RANKED = "ranked"
    REJECTED = "rejected"          # not actionable now — but never forgotten
    ARCHIVED = "archived"
    MONITORING = "monitoring"      # rejected but watched for improvement
    RESURRECTED = "resurrected"    # evidence improved → back in the running
    PROMOTED = "promoted"          # handed to a downstream department


# ── The raw signal a discovery agent emits ─────────────────────────────────
@dataclass
class RawSignal:
    title: str
    category: OpportunityCategory
    source: str
    asset_type: str = ""
    expected_roi: float = 0.0          # return multiple (0.5 = +50%)
    risk: float = 0.3                  # 0..1
    strategic_fit: float = 0.5         # 0..1 (Dream Engine can later tune this)
    urgency: float = 0.5               # 0..1 (how time-sensitive)
    time_horizon_months: float = 12.0
    capital_required_usd: float = 0.0


_STOP = {"released", "announced", "available", "launches", "launched", "new",
         "the", "a", "an", "is", "now", "out", "for", "to", "of", "on"}


def dedupe_key(title: str) -> str:
    """Canonical entity key so 'GPT-X released', 'GPT-X announced', and
    'GPT-X available' collapse to one opportunity."""
    tokens = [t for t in re.split(r"[^a-z0-9]+", title.lower())
              if t and t not in _STOP and len(t) >= 2]
    return "-".join(sorted(set(tokens))) or title.lower().strip()


@dataclass
class Opportunity:
    title: str
    category: OpportunityCategory
    source: str
    asset_type: str
    expected_roi: float
    risk: float
    strategic_fit: float
    urgency: float
    time_horizon_months: float
    capital_required_usd: float
    confidence: float = 0.0            # 0..1, from Research Confidence Framework
    evidence_quality: float = 0.0      # 0..1, independent-source depth
    actionable: bool = False
    sources: list[str] = field(default_factory=list)
    status: OpportunityStatus = OpportunityStatus.NEW
    owner_department: str = "investment"
    research_report: object | None = None   # ResearchConfidence, if researched
    first_seen: float = 0.0
    last_seen: float = 0.0

    @property
    def key(self) -> str:
        return dedupe_key(self.title)

    @property
    def score(self) -> float:
        """ROI × Confidence × Strategic Fit × Urgency × Evidence Quality / Risk.
        The Dream Engine can later modulate `strategic_fit` as goals evolve."""
        return round(
            self.expected_roi * max(self.confidence, 1e-3) * self.strategic_fit
            * self.urgency * max(self.evidence_quality, 1e-3)
            / max(self.risk, 0.05), 4)


def _merge(into: Opportunity, other: Opportunity) -> None:
    """Fold a duplicate's sources in; keep the strongest estimates."""
    for s in [other.source, *other.sources]:
        if s and s not in into.sources:
            into.sources.append(s)
    into.expected_roi = max(into.expected_roi, other.expected_roi)
    into.strategic_fit = max(into.strategic_fit, other.strategic_fit)
    into.urgency = max(into.urgency, other.urgency)
    into.risk = min(into.risk, other.risk)


# ── Discovery agents (thin: category + injected scanner) ────────────────────
@dataclass
class DiscoveryAgent:
    name: str
    scan: Callable[[], list[RawSignal]]

    def discover(self) -> list[RawSignal]:
        return list(self.scan())


def crypto_discovery(scan, name="Crypto Discovery") -> DiscoveryAgent:
    return DiscoveryAgent(name, scan)


def stock_discovery(scan, name="Stock Discovery") -> DiscoveryAgent:
    return DiscoveryAgent(name, scan)


def ai_discovery(scan, name="AI Discovery") -> DiscoveryAgent:
    return DiscoveryAgent(name, scan)


def business_discovery(scan, name="Business Discovery") -> DiscoveryAgent:
    return DiscoveryAgent(name, scan)


def revenue_discovery(scan, name="Revenue Discovery") -> DiscoveryAgent:
    return DiscoveryAgent(name, scan)


# ── Opportunity Memory — never forget; resurrect on improvement ─────────────
class OpportunityMemory:
    """Every opportunity is alive. Rejected ones are monitored; when a
    re-observation scores materially higher they are RESURRECTED."""

    def __init__(self, db_path: "str | Path", now: Callable[[], float] = time.time):
        self.path = str(db_path)
        self.now = now
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS opportunities (
                key TEXT PRIMARY KEY,
                title TEXT, category TEXT, status TEXT,
                score REAL, confidence REAL,
                first_seen REAL, last_seen REAL, updated_at REAL,
                payload TEXT
            );
        """)
        self._db.commit()

    def get(self, key: str) -> Opportunity | None:
        row = self._db.execute(
            "SELECT payload FROM opportunities WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        return _from_payload(json.loads(row[0]))

    def remember(self, opp: Opportunity, *, resurrect_delta: float = 0.25) -> Opportunity:
        """Insert new, or update existing. If the existing one was rejected and
        the new score beats it by `resurrect_delta`, mark RESURRECTED."""
        now = self.now()
        existing = self.get(opp.key)
        if existing is None:
            opp.first_seen = opp.first_seen or now
            opp.last_seen = now
            self._write(opp, now)
            return opp
        # merge sources, keep original first_seen
        opp.first_seen = existing.first_seen
        opp.last_seen = now
        for s in existing.sources:
            if s not in opp.sources:
                opp.sources.append(s)
        if existing.status in (OpportunityStatus.REJECTED, OpportunityStatus.MONITORING) \
                and opp.score >= existing.score + resurrect_delta:
            opp.status = OpportunityStatus.RESURRECTED
        self._write(opp, now)
        return opp

    def monitor_rejected(self, opp: Opportunity) -> Opportunity:
        opp.status = OpportunityStatus.MONITORING
        self._write(opp, self.now())
        return opp

    def all(self, status: OpportunityStatus | None = None) -> list[Opportunity]:
        if status is None:
            rows = self._db.execute("SELECT payload FROM opportunities").fetchall()
        else:
            rows = self._db.execute(
                "SELECT payload FROM opportunities WHERE status=?", (status.value,)).fetchall()
        return [_from_payload(json.loads(r[0])) for r in rows]

    def _write(self, opp: Opportunity, now: float) -> None:
        self._db.execute(
            "INSERT INTO opportunities (key,title,category,status,score,confidence,"
            "first_seen,last_seen,updated_at,payload) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET title=excluded.title,category=excluded.category,"
            "status=excluded.status,score=excluded.score,confidence=excluded.confidence,"
            "last_seen=excluded.last_seen,updated_at=excluded.updated_at,payload=excluded.payload",
            (opp.key, opp.title, opp.category.value, opp.status.value, opp.score,
             opp.confidence, opp.first_seen, opp.last_seen, now, _to_payload(opp)))
        self._db.commit()


def _to_payload(opp: Opportunity) -> str:
    d = asdict(opp)
    d["category"] = opp.category.value
    d["status"] = opp.status.value
    d.pop("research_report", None)      # not JSON-serializable; recomputed on research
    return json.dumps(d)


def _from_payload(d: dict) -> Opportunity:
    d = dict(d)
    d["category"] = OpportunityCategory(d["category"])
    d["status"] = OpportunityStatus(d["status"])
    d.pop("research_report", None)
    return Opportunity(**d)


# ── The Department (orchestrates the pipeline) ──────────────────────────────
class OpportunityIntelligence:
    def __init__(self, agents: list[DiscoveryAgent], *,
                 research: Callable[[str], object] | None = None,
                 memory: OpportunityMemory | None = None,
                 now: Callable[[], float] = time.time,
                 publish: Callable[[str, dict], object] | None = None,
                 record_episode: Callable[..., int] | None = None):
        self.agents = agents
        self.research = research           # (subject) -> ResearchConfidence
        self.memory = memory
        self.now = now
        if publish is None:
            from saathi.events import bus
            publish = bus.publish_sync
        if record_episode is None:
            from saathi.integration import ingest_episode as record_episode
        self._publish = publish
        self._episode = record_episode

    def _normalize(self, sig: RawSignal) -> Opportunity:
        now = self.now()
        return Opportunity(
            title=sig.title, category=sig.category, source=sig.source,
            asset_type=sig.asset_type, expected_roi=sig.expected_roi, risk=sig.risk,
            strategic_fit=sig.strategic_fit, urgency=sig.urgency,
            time_horizon_months=sig.time_horizon_months,
            capital_required_usd=sig.capital_required_usd,
            sources=[sig.source], first_seen=now, last_seen=now)

    def discover(self, *, top: int = 10) -> list[Opportunity]:
        # 1. Scan
        raw: list[RawSignal] = []
        for agent in self.agents:
            raw.extend(agent.discover())
        # 2. Normalize + 5. Deduplicate (merge by canonical key)
        merged: dict[str, Opportunity] = {}
        for sig in raw:
            opp = self._normalize(sig)
            if opp.key in merged:
                _merge(merged[opp.key], opp)
            else:
                merged[opp.key] = opp
        opps = list(merged.values())
        # 3. Research + 4. Confidence
        for opp in opps:
            if self.research is not None:
                conf = self.research(opp.title)
                opp.research_report = conf
                opp.confidence = round(conf.overall / 100.0, 3)
                opp.evidence_quality = round(min(1.0, conf.source_count / 5.0), 3)
                opp.actionable = conf.actionable
                opp.status = (OpportunityStatus.RESEARCHED if conf.actionable
                              else OpportunityStatus.REJECTED)
            # 6/7. persist to memory (may RESURRECT a previously rejected one)
            if self.memory is not None:
                stored = self.memory.remember(opp)
                opp.status = stored.status
                opp.first_seen = stored.first_seen
        # 8. Rank (rejected ranked last; live opportunities by score)
        actionable = [o for o in opps if o.status != OpportunityStatus.REJECTED]
        actionable.sort(key=lambda o: o.score, reverse=True)
        top_opps = actionable[:top]

        self._publish("opportunity.discovered", {
            "scanned": len(raw), "unique": len(opps),
            "actionable": len(actionable), "top": len(top_opps)})
        self._episode(
            agent="opportunity_intelligence", department="investment",
            product="discovery", intent="daily_discovery",
            action=f"scanned {len(raw)} signals across {len(self.agents)} agents",
            result=f"{len(actionable)} actionable of {len(opps)} unique",
            outcome="success", quality_score=round(len(actionable) / max(len(opps), 1), 3),
            metadata={"top": [o.title for o in top_opps]})
        return top_opps
