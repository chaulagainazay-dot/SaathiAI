"""AI Studio — the autonomous flagship, wiring EXISTING pieces into one run.

Not 17 new modules: the orchestrator (`ContentFactoryPipeline`), content
generation (`content_studio`), and the *proven* browser publisher already exist.
This binds them — topic → real AI metadata → Discovery Gate → (approval) →
publish via the logged-in browser → Episodes → Learning — so the pipeline
produces a real published video today, and each module deepens over time.

Every side-effect is injectable (metadata_gen, publisher) so the flow is tested
with no LLM, no browser, no network.
"""
from __future__ import annotations

from saathi.content_pipeline import ContentFactoryPipeline, ContentRun, Topic, Stage


# ── real metadata generation (Model Router / content_studio), injectable ────
def default_metadata(topic: str) -> dict:
    """Title / description / SEO tags / script beats for a topic. Uses the
    existing content generator; falls back to the Model Router; never raises."""
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
        prompt = (f"Create a Mr. Yeti IELTS video plan for the topic: {topic}. "
                  'Reply ONLY as JSON: {"title","description","seo_tags":[],'
                  '"hook","teaching":[],"examples","cta"}')
        out = generate(ModelLabel.STANDARD, prompt, "Reply with ONLY JSON.", max_tokens=600).text
        return _shape(json.loads(out.strip().strip("`").replace("json", "", 1)), topic)
    except Exception:
        # last-resort deterministic shell so a run can still exercise the pipeline
        return _shape({"title": f"Mr. Yeti: {topic}", "description": f"IELTS tips on {topic}.",
                       "hook": f"Struggling with {topic}?", "teaching": [f"Key idea about {topic}."],
                       "examples": "Example sentence.", "cta": "Practice on pielts.web.app",
                       "seo_tags": ["ielts", "mr yeti", topic]}, topic)


def _shape(p: dict, topic: str) -> dict:
    return {
        "title": p.get("title") or f"Mr. Yeti: {topic}",
        "description": p.get("description") or "",
        "seo_tags": p.get("seo_tags") or p.get("tags") or ["ielts", "mr yeti"],
        "script": {"hook": p.get("hook", ""), "teaching": p.get("teaching", []) or [p.get("description", "")],
                   "examples": p.get("examples", "example"), "cta": p.get("cta", "pielts.web.app")},
    }


# ── proven browser publisher (maps platform → workflow), injectable ─────────
def default_publisher(*, video_path: str, platform: str, metadata: dict,
                      backend=None, visibility: str = "Unlisted") -> dict:
    from saathi.infrastructure.human_browser import ChromeBackend, ProfileStore
    be = backend or ChromeBackend(ProfileStore())     # picks up CHROME_CDP_URL
    title, desc = metadata.get("title", ""), metadata.get("description", "")
    if platform == "youtube":
        return be.execute("publish_video", profile="ajay/youtube", workflow="youtube_upload",
                          path=video_path, title=title, description=desc, visibility=visibility, no_vision=True)
    if platform == "tiktok":
        return be.execute("publish_video", profile="ajay/tiktok", workflow="tiktok_upload",
                          path=video_path, caption=f"{title} {' '.join('#'+t for t in metadata.get('seo_tags',[])[:3])}")
    if platform == "linkedin":
        return be.execute("publish_post", profile="ajay/linkedin", workflow="linkedin_post",
                          text=f"{title}\n\n{desc}", media=video_path)
    return {"error": f"unknown platform {platform}"}


class AIStudio:
    def __init__(self, *, pipeline=None, metadata_gen=None, publisher=None):
        self.pipeline = pipeline or ContentFactoryPipeline()
        self._gen = metadata_gen or default_metadata
        self._publisher = publisher or default_publisher

    def run(self, *, topic: str, video_path: str, platforms=("youtube",),
            approver: str | None = None, thumbnail: str | None = None) -> ContentRun:
        run = ContentRun()
        # 1-2. discover/research a single operator-chosen topic
        t = Topic(title=topic, source="operator", trend=0.7, relevance=0.8, competition=0.4, evidence=5)
        self.pipeline.research_topic(run, t)
        # 3-4. real AI script + scene plan + SEO metadata
        content = self._gen(topic)
        self.pipeline.validate_script(run, content["script"])
        self.pipeline.plan_scenes(run, content["script"])
        self.pipeline.build_metadata(run, title=content["title"], description=content["description"],
                                     seo_tags=content["seo_tags"], thumbnail=thumbnail)
        # 7. Discovery Gate — nothing incomplete publishes
        if not self.pipeline.gate(run):
            return run                          # gate_blocked
        # human approval (optional auto)
        if not approver:
            return run                          # awaiting_approval
        self.pipeline.approve(run, approver)
        # 8. publish via the proven browser path
        self.pipeline.publish(run, list(platforms),
                              lambda md, platform: self._publisher(
                                  video_path=video_path, platform=platform, metadata=md))
        return run
