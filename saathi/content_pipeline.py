"""Autonomous Content Factory (M6 · Stabilization) — the decision layer.

Produces Mr. Yeti videos end to end. The hard rule of this whole design:
    n8n orchestrates and schedules · external services generate (LLM/voice/image/
    render) · SaathiAI decides, scores, gates, learns — and EVERY action becomes
    an Episode. Nothing smart lives in n8n.

So this module is pure intelligence: rank topics, score research, validate the
script, generate scene prompts, build discovery-ready metadata, run the Discovery
Gate, publish only after the gate passes AND a human approves, then turn analytics
into lessons. External artifacts (script text, audio, video) are handed IN by n8n;
provider keys never live here.

Deterministic core (AP-17); episode recorder / publisher / clock injected (AP-12).
Every stage records an Episode → Learning Runtime → Knowledge → Executive Intelligence.
"""
from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from saathi.publishing_pipeline import default_discovery_checks


class Stage(str, Enum):
    DISCOVER = "discover"
    RESEARCH = "research"
    SCRIPT = "script"
    ASSETS = "assets"
    VOICE = "voice"
    RENDER = "render"
    GATE = "gate"
    PUBLISH = "publish"
    ANALYTICS = "analytics"
    LEARN = "learn"


@dataclass
class Topic:
    title: str
    source: str                    # reddit / google_trends / youtube / x / …
    trend: float = 0.5             # 0..1 momentum
    relevance: float = 0.5         # 0..1 fit to Mr. Yeti pillars
    competition: float = 0.5       # 0..1 (higher = more saturated)
    evidence: int = 0

    @property
    def score(self) -> float:
        """Rank by momentum × relevance, discounted by saturation. Explainable."""
        return round(self.trend * self.relevance * (1.0 - 0.5 * self.competition), 4)


@dataclass
class Scene:
    text: str
    image_prompt: str


@dataclass
class ContentRun:
    topic: Topic | None = None
    research_confidence: float = 0.0
    script_ok: bool = False
    script_issues: list[str] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    gate_passed: bool = False
    gate_blockers: list[str] = field(default_factory=list)
    approved_by: str | None = None
    published: list[dict] = field(default_factory=list)
    status: str = "new"
    episodes: list[int] = field(default_factory=list)


class ContentFactoryPipeline:
    def __init__(self, *, record_episode: Callable[..., int] | None = None,
                 publish_event: Callable[[str, dict], object] | None = None,
                 now: Callable[[], float] = time.time):
        if record_episode is None:
            from saathi.integration import ingest_episode as record_episode
        if publish_event is None:
            from saathi.events import bus
            publish_event = bus.publish_sync
        self._episode = record_episode
        self._publish = publish_event
        self.now = now

    # every stage funnels through here → an Episode, always (the SaathiAI difference)
    def _ep(self, stage: Stage, action: str, result: str, *, outcome: str = "success",
            quality: float = 0.0, meta: dict | None = None) -> int:
        eid = self._episode(
            agent="content_factory", department="ai_studio", product="mr_yeti",
            intent=f"content_{stage.value}", action=action, result=result,
            outcome=outcome, quality_score=round(quality, 3), metadata=meta or {})
        self._publish(f"content.{stage.value}", {"outcome": outcome, "quality": quality})
        return eid

    # ── 1. Discovery — rank raw trend signals (n8n fetched them) ────────────
    def rank_topics(self, run: ContentRun, signals: list[dict], top: int = 20) -> list[Topic]:
        topics = [Topic(title=s["title"], source=s.get("source", "unknown"),
                        trend=s.get("trend", 0.5), relevance=s.get("relevance", 0.5),
                        competition=s.get("competition", 0.5), evidence=s.get("evidence", 0))
                  for s in signals]
        topics.sort(key=lambda t: t.score, reverse=True)
        ranked = topics[:top]
        run.episodes.append(self._ep(Stage.DISCOVER,
            f"ranked {len(signals)} trend signals", f"top {len(ranked)} selected",
            quality=ranked[0].score if ranked else 0.0,
            meta={"top": [t.title for t in ranked[:5]]}))
        run.status = "discovered"
        return ranked

    # ── 2. Research — confidence for a chosen topic ─────────────────────────
    def research_topic(self, run: ContentRun, topic: Topic) -> float:
        # confidence from evidence depth + relevance; sparse evidence ⇒ low trust
        depth = min(1.0, topic.evidence / 8.0)
        conf = round(0.55 * depth + 0.45 * topic.relevance, 3)
        run.topic, run.research_confidence = topic, conf
        run.episodes.append(self._ep(Stage.RESEARCH,
            f"researched '{topic.title}'", f"confidence {conf:.0%}, {topic.evidence} sources",
            outcome="success" if conf >= 0.5 else "insufficient_evidence",
            quality=conf, meta={"topic": topic.title, "source": topic.source}))
        return conf

    # ── 3. Script — validate structure (n8n's LLM wrote it) ─────────────────
    def validate_script(self, run: ContentRun, script: dict) -> bool:
        issues = []
        for key in ("hook", "teaching", "examples", "cta"):
            if not script.get(key):
                issues.append(f"missing {key}")
        body = " ".join(str(script.get(k, "")) for k in ("hook", "teaching", "examples", "cta"))
        words = len(re.findall(r"\w+", body))
        if words < 25:
            issues.append(f"too short ({words} words)")
        run.script_ok = not issues
        run.script_issues = issues
        run.episodes.append(self._ep(Stage.SCRIPT,
            "validated script structure",
            "passed" if run.script_ok else f"issues: {', '.join(issues)}",
            outcome="success" if run.script_ok else "failure",
            quality=1.0 if run.script_ok else 0.0, meta={"words": words}))
        run.status = "scripted" if run.script_ok else "script_blocked"
        return run.script_ok

    # ── 4. Assets — SaathiAI generates the scene prompts (n8n calls Flux) ───
    def plan_scenes(self, run: ContentRun, script: dict, style: str =
                    "Pixar-quality 3D, friendly yeti teacher, soft studio light") -> list[Scene]:
        beats = [script.get("hook", "")] + list(script.get("teaching", [])) + [script.get("cta", "")]
        scenes = []
        for i, beat in enumerate([b for b in beats if b]):
            prompt = f"Scene {i+1}: {beat.strip()[:120]} — Mr. Yeti, {style}, 9:16, no text"
            scenes.append(Scene(text=beat.strip(), image_prompt=prompt))
        run.scenes = scenes
        run.episodes.append(self._ep(Stage.ASSETS,
            "generated scene prompts", f"{len(scenes)} scenes",
            quality=min(1.0, len(scenes) / 6.0), meta={"scenes": len(scenes)}))
        run.status = "assets_ready"
        return scenes

    # ── 4b. Metadata — SEO/GEO-ready package for the Discovery Gate ─────────
    def build_metadata(self, run: ContentRun, *, title: str, description: str,
                       seo_tags: list[str], thumbnail: str | None,
                       geo: bool = True) -> dict:
        md = {"title": title, "description": description, "seo_tags": seo_tags,
              "thumbnail": thumbnail}
        if geo:
            md["geo"] = {"@type": "VideoObject", "name": title}
        run.metadata = md
        return md

    # ── 7. Discovery Gate — nothing publishes incomplete (reused engine) ────
    def gate(self, run: ContentRun) -> bool:
        report = default_discovery_checks(run.metadata)
        run.gate_passed = report.passed
        run.gate_blockers = [c.name for c in report.blocking_failures]
        run.episodes.append(self._ep(Stage.GATE,
            "discovery gate", "passed" if report.passed else f"blocked: {', '.join(run.gate_blockers)}",
            outcome="success" if report.passed else "failure",
            quality=1.0 if report.passed else 0.0, meta={"blockers": run.gate_blockers}))
        run.status = "gate_passed" if report.passed else "gate_blocked"
        if report.passed:
            run.status = "awaiting_approval"
        return report.passed

    def approve(self, run: ContentRun, approver: str) -> ContentRun:
        if not run.gate_passed:
            raise ValueError("cannot approve — Discovery Gate not passed")
        run.approved_by = approver
        return run

    # ── 8. Publish — only after gate pass AND human approval ────────────────
    def publish(self, run: ContentRun, platforms: list[str],
                publisher: Callable[[dict, str], dict]) -> list[dict]:
        if not run.gate_passed:
            raise PermissionError("Discovery Gate not passed")
        if not run.approved_by:
            raise PermissionError("publishing requires human approval")
        results = []
        for platform in platforms:
            try:
                res = publisher(run.metadata, platform)
                ok = "error" not in res
            except Exception as exc:  # n8n/provider failure — recorded, not fatal
                res, ok = {"error": str(exc)}, False
            results.append({"platform": platform, "ok": ok, "result": res})
            run.episodes.append(self._ep(Stage.PUBLISH,
                f"publish to {platform}", "published" if ok else f"failed: {res.get('error')}",
                outcome="success" if ok else "failure", quality=1.0 if ok else 0.0,
                meta={"platform": platform, "approved_by": run.approved_by}))
        run.published = results
        run.status = "published" if all(r["ok"] for r in results) else "partial"
        return results

    # ── 9/10. Analytics → Learning ──────────────────────────────────────────
    def record_analytics(self, run: ContentRun, *, views: int, ctr: float,
                         watch_time_s: float, revenue_usd: float) -> int:
        quality = round(min(1.0, ctr * 5), 3)   # CTR is the sharpest quality signal
        eid = self._ep(Stage.ANALYTICS,
            "collected performance", f"{views} views · CTR {ctr:.1%} · ${revenue_usd:.0f}",
            quality=quality, meta={"views": views, "ctr": ctr,
                                   "watch_time_s": watch_time_s, "revenue_usd": revenue_usd})
        run.episodes.append(eid)
        return eid

    # error recovery: n8n retries the CALL; on final failure it tells SaathiAI,
    # which records a failure Episode + emits an actionable notification.
    def record_failure(self, stage: Stage, error: str, *, topic: str = "") -> dict:
        eid = self._ep(stage, f"stage failed: {stage.value}", error,
                       outcome="failure", quality=0.0, meta={"topic": topic, "error": error})
        note = {"dept": "AI STUDIO", "title": f"Content pipeline failed at {stage.value}: {error}",
                "action": "Retry", "tone": "critical"}
        self._publish("content.failed", {"stage": stage.value, "error": error, **note})
        return {"episode": eid, "notification": note}
