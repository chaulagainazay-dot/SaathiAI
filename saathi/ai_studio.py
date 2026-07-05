"""AI Studio — the autonomous flagship, wiring EXISTING pieces into one run.

The orchestrator (`ContentFactoryPipeline`) and generation (`content_studio`)
already exist; this binds them and instruments the run: operating MODE (manual /
assisted / autonomous), per-stage CONFIDENCE + REASONS, COST + TIME tracking, and
STRUCTURED FAILURES (reason + recommendation) — so `/studio` explains itself and
autonomy is gated on confidence. Side-effects injectable → tested with no
LLM/browser/network.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from saathi.content_pipeline import ContentFactoryPipeline, ContentRun, Topic


class Mode(str, Enum):
    MANUAL = "manual"          # every stage pauses for approval
    ASSISTED = "assisted"      # auto through metadata; publish needs approval
    AUTONOMOUS = "autonomous"  # auto-publish when confidence ≥ threshold, else pause


# rough per-stage cost estimate ($) — real usage fills in as providers report it
_STAGE_COST = {"research": 0.01, "script": 0.03, "storyboard": 0.01, "assets": 0.09,
               "voice": 0.05, "render": 0.22, "seo": 0.01, "publish": 0.0}

# structured failure recommendations
_FIX = {
    "script": ("script incomplete", "Regenerate script (hook/teaching/examples/cta)"),
    "gate": ("Discovery Gate blocked", "Fix missing metadata (title/description/SEO/thumbnail)"),
    "publish": ("publish failed", "Teach the changed selector (Teach Mode) or retry"),
}


@dataclass
class StageReport:
    stage: str
    confidence: float
    reasons: list[str]
    duration_ms: int
    cost: float = 0.0
    ok: bool = True


@dataclass
class StudioRun:
    topic: str
    mode: str
    stages: list[StageReport] = field(default_factory=list)
    status: str = "new"
    overall_confidence: float = 0.0
    cost_total: float = 0.0
    duration_ms: int = 0
    published: list = field(default_factory=list)
    failure: dict | None = None
    video_url: str = ""

    def as_dict(self) -> dict:
        return {"topic": self.topic, "mode": self.mode, "status": self.status,
                "overall_confidence": self.overall_confidence, "cost_total": round(self.cost_total, 3),
                "duration_ms": self.duration_ms, "video_url": self.video_url, "failure": self.failure,
                "stages": [s.__dict__ for s in self.stages],
                "published": self.published}


# metadata generation + browser publisher (unchanged, injectable) ────────────
def default_metadata(topic: str) -> dict:
    try:
        from saathi.tools.content_studio import generate_content_pack
        pack = generate_content_pack(topic) or {}
        if pack.get("title"):
            return _shape(pack, topic)
    except Exception:
        pass
    try:
        from saathi.infrastructure.llm import generate
        from saathi.infrastructure.model_router import ModelLabel
        import json
        prompt = (f"Create a Mr. Yeti IELTS video plan for: {topic}. Reply ONLY as JSON: "
                  '{"title","description","seo_tags":[],"hook","teaching":[],"examples","cta"}')
        out = generate(ModelLabel.STANDARD, prompt, "Reply with ONLY JSON.", max_tokens=600).text
        return _shape(json.loads(out.strip().strip("`").replace("json", "", 1)), topic)
    except Exception:
        return _shape({"title": f"Mr. Yeti: {topic}",
                       "description": f"A friendly Mr. Yeti IELTS lesson about {topic} with examples.",
                       "hook": f"Struggling with {topic}?", "teaching": [f"Key idea about {topic}."],
                       "examples": "Example sentence.", "cta": "Practice on pielts.web.app",
                       "seo_tags": ["ielts", "mr yeti", topic]}, topic)


def _shape(p: dict, topic: str) -> dict:
    return {"title": p.get("title") or f"Mr. Yeti: {topic}",
            "description": p.get("description") or f"A Mr. Yeti IELTS lesson about {topic} with examples.",
            "seo_tags": p.get("seo_tags") or p.get("tags") or ["ielts", "mr yeti"],
            "script": {"hook": p.get("hook", ""),
                       "teaching": p.get("teaching", []) or [p.get("description", "")],
                       "examples": p.get("examples", "example"), "cta": p.get("cta", "pielts.web.app")}}


def default_publisher(*, video_path: str, platform: str, metadata: dict, backend=None,
                      visibility: str = "Unlisted") -> dict:
    from saathi.infrastructure.human_browser import ChromeBackend, ProfileStore
    be = backend or ChromeBackend(ProfileStore())
    title, desc = metadata.get("title", ""), metadata.get("description", "")
    if platform == "youtube":
        return be.execute("publish_video", profile="ajay/youtube", workflow="youtube_upload",
                          path=video_path, title=title, description=desc, visibility=visibility, no_vision=True)
    if platform == "tiktok":
        return be.execute("publish_video", profile="ajay/tiktok", workflow="tiktok_upload",
                          path=video_path, caption=f"{title} " +
                          " ".join("#" + t for t in metadata.get("seo_tags", [])[:3]))
    if platform == "linkedin":
        return be.execute("publish_post", profile="ajay/linkedin", workflow="linkedin_post",
                          text=f"{title}\n\n{desc}", media=video_path)
    return {"error": f"unknown platform {platform}"}


class AIStudio:
    def __init__(self, *, pipeline=None, metadata_gen=None, publisher=None, store=None):
        self.pipeline = pipeline or ContentFactoryPipeline()
        self._gen = metadata_gen or default_metadata
        self._publisher = publisher or default_publisher
        if store is None:
            try:
                from saathi.studio_store import default_store
                store = default_store()
            except Exception:
                store = None
        self._store = store

    def run(self, *, topic: str, video_path: str, platforms=("youtube",),
            mode: str = Mode.ASSISTED, approver: str | None = None,
            confidence_threshold: float = 0.9, thumbnail: str | None = None) -> StudioRun:
        sr = StudioRun(topic=topic, mode=str(mode))
        run = ContentRun()
        t_start = time.time()

        def stage(name, fn):
            t0 = time.time()
            conf, reasons, ok = fn()
            rep = StageReport(stage=name, confidence=round(conf, 2), reasons=reasons,
                              duration_ms=round((time.time() - t0) * 1000),
                              cost=_STAGE_COST.get(name, 0.0), ok=ok)
            sr.stages.append(rep); sr.cost_total += rep.cost
            return rep

        # 1-2 research
        def _research():
            conf = self.pipeline.research_topic(
                run, Topic(title=topic, source="operator", trend=0.7, relevance=0.8,
                           competition=0.4, evidence=5))
            return conf, ["evidence gathered", f"confidence {conf:.0%}"], conf >= 0.4
        stage("research", _research)

        # 3-4 metadata + script + scenes + SEO
        content = self._gen(topic)
        def _script():
            ok = self.pipeline.validate_script(run, content["script"])
            self.pipeline.plan_scenes(run, content["script"])
            self.pipeline.build_metadata(run, title=content["title"], description=content["description"],
                                         seo_tags=content["seo_tags"], thumbnail=thumbnail)
            reasons = ["hook/teaching/examples/cta present"] if ok else run.script_issues
            return (1.0 if ok else 0.0), reasons, ok
        srep = stage("script", _script)
        if not srep.ok:
            return self._finish(sr, run, t_start, "script", "script_blocked")

        # 7 discovery gate
        grep = stage("gate", lambda: (
            (1.0, ["title/description/SEO/thumbnail ok"], True) if self.pipeline.gate(run)
            else (0.0, run.gate_blockers, False)))
        if not grep.ok:
            return self._finish(sr, run, t_start, "gate", "gate_blocked")

        sr.overall_confidence = round(sum(s.confidence for s in sr.stages) / len(sr.stages), 2)

        # approval gating by MODE
        auto = (mode == Mode.AUTONOMOUS and sr.overall_confidence >= confidence_threshold)
        if not (approver or auto):
            return self._finish(sr, run, t_start, None, "awaiting_approval")
        self.pipeline.approve(run, approver or "autonomous")

        # 8 publish (proven browser path)
        def _pub():
            self.pipeline.publish(run, list(platforms),
                                  lambda md, platform: self._publisher(
                                      video_path=video_path, platform=platform, metadata=md))
            ok = all(p["ok"] for p in run.published) if run.published else False
            urls = [(p.get("result") or {}).get("video_url") for p in run.published]
            sr.video_url = next((u for u in urls if u), "")
            return (1.0 if ok else 0.0), (["published"] if ok else ["publish error"]), ok
        prep = stage("publish", _pub)
        sr.published = run.published
        if not prep.ok:
            return self._finish(sr, run, t_start, "publish", "publish_failed")
        return self._finish(sr, run, t_start, None, "published")

    def _finish(self, sr: StudioRun, run: ContentRun, t_start: float,
                fail_stage: str | None, status: str) -> StudioRun:
        sr.status = status
        sr.duration_ms = round((time.time() - t_start) * 1000)
        if not sr.overall_confidence and sr.stages:
            sr.overall_confidence = round(sum(s.confidence for s in sr.stages) / len(sr.stages), 2)
        if fail_stage:
            reason, rec = _FIX.get(fail_stage, ("stage failed", "review"))
            detail = "; ".join(run.gate_blockers) if fail_stage == "gate" and run.gate_blockers else reason
            sr.failure = {"stage": fail_stage, "reason": detail, "recommendation": rec}
        if self._store is not None:
            try:
                self._store.record(sr)
            except Exception:
                pass
        return sr
