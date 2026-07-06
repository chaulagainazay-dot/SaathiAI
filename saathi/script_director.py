"""Script Director — the department that writes a complete episode.

Consumes a structured Script Brief (lesson, CEFR, character, episode #, avoid
list, objective, SEO, platform, duration, hook style, CTA, brand voice) and
produces a structured Episode document (hook, learning goal, scenes with
narration/visual/camera/animation/duration, CTA, thumbnail ideas, SEO, captions)
that every downstream Director (Storyboard, Voice, Render, Publishing) consumes —
structured artifacts, not free-form prompts.

Prompt lives in the AI Lab (`mr-yeti.script-director`); runs on the Model Router
(Gemini 3.5 default). Deterministic fallback so it never hard-fails.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class ScriptDoc:
    episode: str
    topic: str
    hook: str
    learning_goal: str
    scenes: list = field(default_factory=list)      # {n,narration,visual,camera,animation,seconds}
    cta: str = ""
    thumbnail_ideas: list = field(default_factory=list)
    seo: dict = field(default_factory=dict)          # {title,description,tags}
    captions: str = ""
    est_seconds: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()

    def to_pipeline_script(self) -> dict:
        """The shape AIStudio's pipeline expects (hook/teaching/examples/cta)."""
        teaching = [s.get("narration", "") for s in self.scenes if s.get("narration")]
        return {"hook": self.hook, "teaching": teaching[:-1] or teaching,
                "examples": teaching[-1] if teaching else "", "cta": self.cta}


def build_brief(plan: dict, *, platform: str = "youtube", target_seconds: int = 75,
                hook_style: str = "question", cta: str = "Practice free on pielts.web.app") -> dict:
    """Assemble the Script Brief from a Studio plan (plan_today) + defaults."""
    ch = plan.get("character") or {}
    cefr = {"grammar": "B1", "vocabulary": "B2", "speaking": "B2",
            "writing-task1": "B2", "exam-strategy": "C1"}.get(plan.get("skill", ""), "B2")
    return {
        "topic": plan.get("topic", ""), "skill": plan.get("skill", ""),
        "phase": plan.get("phase", ""), "day": plan.get("day", 0),
        "episode": plan.get("episode", ""), "objective": plan.get("objective", ""),
        "audience": "IELTS learners (self-study, mobile)", "cefr": cefr,
        "character": ch, "avoid": plan.get("avoid", []),
        "platform": platform, "target_seconds": target_seconds,
        "hook_style": hook_style, "cta": cta,
        "brand_voice": plan.get("voice_tone", "friendly"),
    }


def write_script(brief: dict) -> ScriptDoc:
    topic = brief.get("topic", "this lesson")
    try:
        from saathi.infrastructure.llm import generate
        from saathi.infrastructure.model_router import ModelLabel
        try:
            from saathi.ai_lab import default_registry
            prompt = default_registry().render("mr-yeti.script-director", brief=json.dumps(brief)[:1400])
        except Exception:
            prompt = _inline_prompt(brief)
        out = generate(ModelLabel.STANDARD, prompt, "Reply with ONLY JSON.", max_tokens=1200).text
        obj = json.loads(out.strip().strip("`").replace("json", "", 1))
        if obj.get("scenes"):
            return _shape(obj, brief)
    except Exception:
        pass
    return _fallback(brief)


def _inline_prompt(brief: dict) -> str:
    return ("You are the Script Director for a Mr. Yeti IELTS explainer. Write a complete "
            f"~{brief.get('target_seconds',75)}s episode from this brief:\n{json.dumps(brief)[:1400]}\n"
            "Mr. Yeti is warm, encouraging, gently funny. Reply ONLY as JSON: "
            '{"hook","learning_goal","scenes":[{"narration","visual","camera","animation","seconds"}],'
            '"cta","thumbnail_ideas":[],"seo":{"title","description","tags":[]},"captions"}. '
            "4-6 scenes; one clear idea per scene; a real IELTS example; end with the CTA.")


def _shape(o: dict, brief: dict) -> ScriptDoc:
    scenes = []
    for i, s in enumerate(o.get("scenes", []), 1):
        scenes.append({"n": i, "narration": s.get("narration", ""), "visual": s.get("visual", ""),
                       "camera": s.get("camera", "slow zoom"), "animation": s.get("animation", ""),
                       "seconds": int(s.get("seconds", 12) or 12)})
    seo = o.get("seo") or {}
    est = sum(s["seconds"] for s in scenes)
    return ScriptDoc(
        episode=brief.get("episode", ""), topic=brief.get("topic", ""),
        hook=o.get("hook", ""), learning_goal=o.get("learning_goal", brief.get("objective", "")),
        scenes=scenes, cta=o.get("cta", brief.get("cta", "")),
        thumbnail_ideas=o.get("thumbnail_ideas", []) if isinstance(o.get("thumbnail_ideas"), list) else [],
        seo={"title": seo.get("title", f"Mr. Yeti: {brief.get('topic','')}"),
             "description": seo.get("description", ""),
             "tags": seo.get("tags", []) if isinstance(seo.get("tags"), list) else []},
        captions=o.get("captions", ""), est_seconds=est)


def _fallback(brief: dict) -> ScriptDoc:
    topic = brief.get("topic", "this lesson")
    scenes = [
        {"n": 1, "narration": f"Struggling with {topic} in your IELTS test? Let's make it simple.",
         "visual": "Mr. Yeti greets at the chalkboard", "camera": "slow zoom", "animation": "warm fade-in", "seconds": 8},
        {"n": 2, "narration": brief.get("objective", f"Here's the key idea behind {topic}."),
         "visual": f"whiteboard explaining {topic}", "camera": "gentle pan", "animation": "highlight text", "seconds": 18},
        {"n": 3, "narration": "Here's a real example you can use in the exam.",
         "visual": "example sentence on screen, Mr. Yeti points", "camera": "medium shot", "animation": "word pop", "seconds": 14},
        {"n": 4, "narration": brief.get("cta", "Practice free on pielts.web.app."),
         "visual": "Mr. Yeti waves, pielts.web.app CTA", "camera": "slow zoom", "animation": "logo reveal", "seconds": 8},
    ]
    return ScriptDoc(
        episode=brief.get("episode", ""), topic=topic,
        hook=scenes[0]["narration"], learning_goal=brief.get("objective", ""),
        scenes=scenes, cta=brief.get("cta", ""),
        thumbnail_ideas=[f"Mr. Yeti + '{topic}' bold text", "surprised student face", "before/after example"],
        seo={"title": f"Mr. Yeti #{brief.get('day','')}: {topic} | IELTS {brief.get('phase','')}",
             "description": f"A friendly Mr. Yeti IELTS lesson on {topic}. Practice on pielts.web.app.",
             "tags": ["ielts", "mr yeti", topic, brief.get("skill", "")]},
        captions="", est_seconds=sum(s["seconds"] for s in scenes))
