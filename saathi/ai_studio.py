"""AI Studio — the autonomous flagship, wiring EXISTING pieces into one run.

The orchestrator (`ContentFactoryPipeline`) and generation (`content_studio`)
already exist; this binds them and instruments the run: operating MODE (manual /
assisted / autonomous), per-stage CONFIDENCE + REASONS, COST + TIME tracking, and
STRUCTURED FAILURES (reason + recommendation) — so `/studio` explains itself and
autonomy is gated on confidence. Side-effects injectable → tested with no
LLM/browser/network.
"""
from __future__ import annotations

import os
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
    "voice": ("voice not produced", "Configure a TTS provider (saathi.tools.voice) or supply narration"),
    "assets": ("scene images not produced", "Configure an image provider (saathi.tools.images)"),
    "render": ("video not rendered", "Configure the renderer (saathi.tools.render) or pass a clip"),
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
    run_id: str = ""
    stage_flags: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"topic": self.topic, "mode": self.mode, "status": self.status,
                "overall_confidence": self.overall_confidence, "cost_total": round(self.cost_total, 3),
                "duration_ms": self.duration_ms, "video_url": self.video_url, "failure": self.failure,
                "run_id": self.run_id, "stage_flags": self.stage_flags,
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


# generation hooks (provider-gated) — each returns a path or None. None means the
# provider is not configured yet, and the PAT reveals that stage as ✗ honestly.
def default_voice(*, script: dict, run, brief: dict | None = None) -> str | None:
    try:
        from saathi.tools.voice import synthesize  # Kokoro → OpenAI → ElevenLabs → say
    except Exception:
        return None
    try:
        if brief and brief.get("scenes"):
            text = " ".join(s.get("narration", "") for s in brief["scenes"]).strip()
        else:
            text = " ".join([script.get("hook", ""), *script.get("teaching", []),
                             script.get("examples", ""), script.get("cta", "")]).strip()
        data = synthesize(text)
        return str(run.save_bytes("narration.wav", data)) if data else None
    except Exception:
        return None


def default_images(*, script: dict, run, brief: dict | None = None) -> list | None:
    try:
        from saathi.tools.images import generate_scene_images  # Flux → branded PIL card
    except Exception:
        return None
    try:
        paths = generate_scene_images(script, out_dir=str(run.subdir("assets")), brief=brief)
        return paths or None
    except Exception:
        return None


def default_render(*, run, voice: str | None, images: list | None,
                   video_path: str | None = None, brief: dict | None = None) -> str | None:
    """Produce video.mp4 (FFmpeg: Ken Burns + narration + ducked music + logo).
    Falls back to an externally-supplied clip ONLY when the caller passed one —
    keeps the publish half certifiable if render inputs are missing."""
    try:
        from saathi.tools.render import render_video
        from saathi.tools import music as _music
        if images:
            mood = (brief or {}).get("music_mood")
            track = _music.select(mood)
            logo = os.path.expanduser("~/SaathiAI/assets/logo.png")
            out = render_video(voice=voice, images=images, out=str(run.path("video.mp4")),
                               music=track, logo=logo if os.path.exists(logo) else None)
            if out:
                return str(out)
    except Exception:
        pass
    if video_path:
        try:
            return str(run.adopt("video.mp4", video_path))
        except Exception:
            return video_path
    return None


class AIStudio:
    def __init__(self, *, pipeline=None, metadata_gen=None, publisher=None, store=None,
                 run_manager=None, voice_gen=None, image_gen=None, renderer=None):
        self.pipeline = pipeline or ContentFactoryPipeline()
        self._gen = metadata_gen or default_metadata
        self._publisher = publisher or default_publisher
        self._rm = run_manager
        self._voice = voice_gen or default_voice
        self._images = image_gen or default_images
        self._render = renderer or default_render
        if store is None:
            try:
                from saathi.studio_store import default_store
                store = default_store()
            except Exception:
                store = None
        self._store = store

    def run(self, *, topic: str, video_path: str | None = None, platforms=("youtube",),
            mode: str = Mode.ASSISTED, approver: str | None = None,
            confidence_threshold: float = 0.9, thumbnail: str | None = None,
            generate: bool = False, run_prefix: str = "YETI",
            quality: str = "draft") -> StudioRun:
        sr = StudioRun(topic=topic, mode=str(mode))
        run = ContentRun()
        t_start = time.time()

        # Run Manager owns the workspace; subsystems only touch `arun`. When no
        # RunManager is injected, arun stays None and workspace steps are skipped.
        arun = None
        if self._rm is not None:
            try:
                arun = self._rm.new_run(prefix=run_prefix)
                sr.run_id = arun.id
            except Exception:
                arun = None

        def stage(name, fn, artifact=None):
            if arun:
                arun.stage_start(name)
            t0 = time.time()
            conf, reasons, ok = fn()
            rep = StageReport(stage=name, confidence=round(conf, 2), reasons=reasons,
                              duration_ms=round((time.time() - t0) * 1000),
                              cost=_STAGE_COST.get(name, 0.0), ok=ok)
            sr.stages.append(rep); sr.cost_total += rep.cost
            if arun:
                verified = arun.verify(artifact) if artifact else True
                arun.stage_end(name, ok=(ok and verified), artifact=artifact,
                               note="; ".join(reasons)[:120])
            return rep

        # 1-2 research → research.md
        def _research():
            conf = self.pipeline.research_topic(
                run, Topic(title=topic, source="operator", trend=0.7, relevance=0.8,
                           competition=0.4, evidence=5))
            if arun:
                arun.save_text("research.md", f"# {topic}\n\nconfidence {conf:.0%}\n"
                               "evidence gathered from operator brief\n")
            return conf, ["evidence gathered", f"confidence {conf:.0%}"], conf >= 0.4
        stage("research", _research, artifact="research.md")

        # 3 script + scenes → script.md
        content = self._gen(topic)
        script = content["script"]
        def _script():
            ok = self.pipeline.validate_script(run, script)
            self.pipeline.plan_scenes(run, script)
            if arun:
                body = "\n\n".join([f"# {content['title']}", f"**Hook:** {script.get('hook','')}",
                                    "## Teaching\n" + "\n".join(f"- {t}" for t in script.get("teaching", [])),
                                    f"**Examples:** {script.get('examples','')}",
                                    f"**CTA:** {script.get('cta','')}"])
                arun.save_text("script.md", body)
            reasons = ["hook/teaching/examples/cta present"] if ok else run.script_issues
            return (1.0 if ok else 0.0), reasons, ok
        srep = stage("script", _script, artifact="script.md")
        if not srep.ok:
            return self._finish(sr, run, t_start, "script", "script_blocked", arun)

        # 4-9 generation chain (opt-in). Creative Director first (direction lifts
        # quality without changing renderers), then voice/assets SOFT, render HARD.
        thumb = thumbnail
        brief = None
        if generate:
            def _direct():
                nonlocal brief
                from saathi.creative_director import direct
                brief = direct(topic, script, quality=quality)
                if arun:
                    arun.save_json("brief.json", brief)
                n = len(brief.get("scenes", []))
                return 1.0, [f"{brief.get('style','')}, {n} scenes, {brief.get('music_mood','')}"], n > 0
            stage("direct", _direct, artifact="brief.json" if arun else None)

            stage("voice", lambda: (
                (1.0, ["narration synthesized"], True)
                if self._voice(script=script, run=arun, brief=brief)
                else (0.0, ["no TTS provider configured"], False)), artifact="narration.wav")
            stage("assets", lambda: (
                (1.0, ["scene images generated"], True)
                if self._images(script=script, run=arun, brief=brief)
                else (0.0, ["no image provider configured"], False)), artifact="assets")

            def _render():
                voice = arun.path("narration.wav") if (arun and arun.verify("narration.wav")) else None
                imgs = sorted(arun.subdir("assets").iterdir()) if (arun and arun.verify("assets")) else None
                out = self._render(run=arun, voice=str(voice) if voice else None,
                                   images=[str(i) for i in imgs] if imgs else None,
                                   video_path=video_path, brief=brief)
                return (1.0, ["video rendered"], True) if out else (0.0, ["no renderer / no clip"], False)
            rrep = stage("render", _render, artifact="video.mp4")
            if not rrep.ok:
                return self._finish(sr, run, t_start, "render", "render_failed", arun)
            video_path = str(arun.path("video.mp4")) if (arun and arun.verify("video.mp4")) else video_path
            if arun and arun.verify("video.mp4") and not thumb:
                thumb = video_path  # first-frame thumbnail stand-in until a thumbnailer is wired

        # 7 metadata + SEO → metadata.json
        def _meta():
            self.pipeline.build_metadata(run, title=content["title"], description=content["description"],
                                         seo_tags=content["seo_tags"], thumbnail=thumb)
            if arun:
                arun.save_json("metadata.json", {"title": content["title"],
                               "description": content["description"], "seo_tags": content["seo_tags"],
                               "thumbnail": thumb})
            return 1.0, ["title/description/SEO built"], True
        stage("metadata", _meta, artifact="metadata.json" if arun else None)

        # 8 discovery gate
        grep = stage("gate", lambda: (
            (1.0, ["title/description/SEO/thumbnail ok"], True) if self.pipeline.gate(run)
            else (0.0, run.gate_blockers, False)))
        if not grep.ok:
            return self._finish(sr, run, t_start, "gate", "gate_blocked", arun)

        sr.overall_confidence = round(sum(s.confidence for s in sr.stages) / len(sr.stages), 2)

        # approval gating by MODE
        auto = (mode == Mode.AUTONOMOUS and sr.overall_confidence >= confidence_threshold)
        if not (approver or auto):
            return self._finish(sr, run, t_start, None, "awaiting_approval", arun)
        self.pipeline.approve(run, approver or "autonomous")

        # 9 publish (proven browser path) → publish.json
        def _pub():
            self.pipeline.publish(run, list(platforms),
                                  lambda md, platform: self._publisher(
                                      video_path=video_path, platform=platform, metadata=md))
            ok = all(p["ok"] for p in run.published) if run.published else False
            urls = [(p.get("result") or {}).get("video_url") for p in run.published]
            sr.video_url = next((u for u in urls if u), "")
            if arun:
                arun.save_json("publish.json", {"platforms": list(platforms), "ok": ok,
                               "video_url": sr.video_url, "results": run.published})
            return (1.0 if ok else 0.0), (["published"] if ok else ["publish error"]), ok
        prep = stage("publish", _pub, artifact="publish.json" if arun else None)
        sr.published = run.published
        if not prep.ok:
            return self._finish(sr, run, t_start, "publish", "publish_failed", arun)

        # 10-11 analytics + learning (workspace-recorded)
        if arun:
            stage("analytics", lambda: (arun.save_json("analytics.json",
                  {"video_url": sr.video_url, "recorded": True}),
                  (1.0, ["analytics recorded"], True))[1], artifact="analytics.json")
            stage("learning", lambda: (1.0, ["episode recorded for learning runtime"], True))
        return self._finish(sr, run, t_start, None, "published", arun)

    def _finish(self, sr: StudioRun, run: ContentRun, t_start: float,
                fail_stage: str | None, status: str, arun=None) -> StudioRun:
        sr.status = status
        sr.duration_ms = round((time.time() - t_start) * 1000)
        if not sr.overall_confidence and sr.stages:
            sr.overall_confidence = round(sum(s.confidence for s in sr.stages) / len(sr.stages), 2)
        if fail_stage:
            reason, rec = _FIX.get(fail_stage, ("stage failed", "review"))
            detail = "; ".join(run.gate_blockers) if fail_stage == "gate" and run.gate_blockers else reason
            sr.failure = {"stage": fail_stage, "reason": detail, "recommendation": rec}
        if arun is not None:
            try:
                sr.stage_flags = arun.stage_flags()
                arun.finalize(status)
            except Exception:
                pass
        if self._store is not None:
            try:
                self._store.record(sr)
            except Exception:
                pass
        return sr
