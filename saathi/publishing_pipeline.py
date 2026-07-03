"""Publishing Pipeline — nothing publishes without passing Discovery (M3 Sprint #2).

The gate that ties AI Studio, Discovery Engine, Governance, and the Learning
Runtime into one value-producing workflow:

    content → Discovery pre-publish gate → Governance → publish
            → record Episode → Learning Runtime → better future content

"Nothing is published without passing Discovery" becomes literally enforced:
missing SEO/GEO/thumbnail metadata blocks the publish. Every publish (and every
block) becomes a platform Episode, so the Learning Engine can see which content
choices actually perform and propose improvements.

Testable in isolation (AP-12): the Discovery checks, the publisher, and the
episode recorder are all injected; no network, no real posting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class PrePublishCheck:
    name: str
    passed: bool
    blocking: bool
    detail: str = ""


@dataclass
class PrePublishReport:
    checks: list[PrePublishCheck] = field(default_factory=list)

    @property
    def blocking_failures(self) -> list[PrePublishCheck]:
        return [c for c in self.checks if c.blocking and not c.passed]

    @property
    def passed(self) -> bool:
        return not self.blocking_failures


def default_discovery_checks(content: dict) -> PrePublishReport:
    """Deterministic Discovery gate. A publish must carry the metadata that makes
    it discoverable across search, AI search (GEO), and social."""
    title = (content.get("title") or "").strip()
    desc = (content.get("description") or "").strip()
    seo_tags = content.get("seo_tags") or content.get("tags") or []
    thumbnail = content.get("thumbnail")
    geo = content.get("geo") or content.get("schema") or content.get("og")

    return PrePublishReport(checks=[
        PrePublishCheck("title", len(title) >= 10, blocking=True,
                        detail="title < 10 chars" if len(title) < 10 else ""),
        PrePublishCheck("description", len(desc) >= 20, blocking=True,
                        detail="description < 20 chars" if len(desc) < 20 else ""),
        PrePublishCheck("seo_tags", bool(seo_tags), blocking=True,
                        detail="no SEO tags/keywords" if not seo_tags else ""),
        PrePublishCheck("thumbnail", bool(thumbnail), blocking=True,
                        detail="no thumbnail" if not thumbnail else ""),
        PrePublishCheck("geo_metadata", bool(geo), blocking=False,   # recommended, not blocking
                        detail="no schema.org/OpenGraph metadata" if not geo else ""),
    ])


@dataclass
class PublishResult:
    published: bool
    report: PrePublishReport
    platform: str
    episode_id: int | None = None
    detail: str = ""
    raw: dict | None = None


def _noop_recorder(**kw) -> int:
    return 0


class PublishingPipeline:
    def __init__(
        self,
        publisher: Callable[[dict, str], dict],                 # (content, platform) -> raw result
        discovery: Callable[[dict], PrePublishReport] = default_discovery_checks,
        record_episode: Callable[..., int] = _noop_recorder,    # default: saathi.integration.ingest_episode
        publish_event: "Callable[[str, dict], None] | None" = None,
    ):
        self._publisher = publisher
        self._discovery = discovery
        self._record = record_episode
        self._publish_event = publish_event

    def _emit(self, name: str, payload: dict) -> None:
        if self._publish_event is not None:
            self._publish_event(name, payload)

    def publish(self, content: dict, platform: str, product: str = "ai_studio") -> PublishResult:
        report = self._discovery(content)

        if not report.passed:
            reasons = "; ".join(f"{c.name}: {c.detail}" for c in report.blocking_failures)
            eid = self._record(
                agent="publishing_pipeline", department="Discovery", product=product,
                intent="publish", action=content.get("title", "")[:200],
                result=f"blocked by Discovery: {reasons}", outcome="failure",
                quality_score=0.0,
                metadata={"platform": platform, "failed_checks":
                          [c.name for c in report.blocking_failures]})
            self._emit("publish.blocked",
                       {"platform": platform, "reasons": reasons, "episode_id": eid})
            return PublishResult(False, report, platform, episode_id=eid,
                                 detail=f"Discovery gate failed: {reasons}")

        # Passed Discovery → publish, then record the execution for learning.
        raw = self._publisher(content, platform)
        ok = not (isinstance(raw, dict) and raw.get("error"))
        eid = self._record(
            agent="publishing_pipeline", department="Discovery", product=product,
            intent="publish", action=content.get("title", "")[:200],
            result=str(raw)[:300], outcome="success" if ok else "failure",
            quality_score=1.0 if ok else 0.0,
            metadata={"platform": platform,
                      "seo_tags": content.get("seo_tags") or content.get("tags") or [],
                      "has_geo": bool(content.get("geo") or content.get("schema"))})
        self._emit("publish.completed" if ok else "publish.failed",
                   {"platform": platform, "episode_id": eid})
        return PublishResult(ok, report, platform, episode_id=eid, raw=raw,
                             detail="" if ok else "publisher error")

    @staticmethod
    def production(publisher: Callable[[dict, str], dict],
                   discovery: "Callable[[dict], PrePublishReport] | None" = None) -> "PublishingPipeline":
        """Wire the pipeline to the live platform: episodes → shared Learning
        Runtime, events → Event Fabric. Caller supplies only the publisher
        (the actual platform poster)."""
        from saathi.integration import ingest_episode
        from saathi.events import bus
        return PublishingPipeline(
            publisher=publisher,
            discovery=discovery or default_discovery_checks,
            record_episode=ingest_episode,
            publish_event=bus.publish_sync,
        )

    def record_performance(self, *, product: str, platform: str, content_id: str,
                           views: int, likes: int) -> int:
        """Analytics feedback → a platform Episode, closing the loop so the
        Learning Engine can learn which content actually performs."""
        engagement = (likes / views) if views else 0.0
        eid = self._record(
            agent="analytics", department="Discovery", product=product,
            intent="content_performance", action=content_id,
            result=f"{views} views, {likes} likes", outcome="success",
            quality_score=min(1.0, engagement * 10),
            metadata={"platform": platform, "views": views, "likes": likes,
                      "engagement_rate": engagement})
        self._emit("analytics.recorded",
                   {"platform": platform, "views": views, "episode_id": eid})
        return eid
