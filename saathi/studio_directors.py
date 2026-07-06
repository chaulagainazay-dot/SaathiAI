"""AI Studio — Departments & Directors (the Digital Media Company model).

Each Director owns one responsibility and communicates through STRUCTURED
ARTIFACTS, not free-form prompts:

  Planner → StudioBrief → Research Director → Research Report
          → Creative Director → Creative Brief → Script Director → Episode Script

The Studio Executive coordinates (does not create): runs the chain, tracks cost/
status, decides ready-vs-revision, reports up. Brand-swappable — change the
Character Bible / Curriculum / brand package, same departments produce any channel.

Prompts live in the AI Lab; runs on the Model Router (Gemini 3.5). Deterministic
fallbacks so no stage hard-fails.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from saathi.infrastructure.model_router import ModelLabel


def _gen_json(prompt_name: str, brief: str, inline: str) -> dict | None:
    try:
        from saathi.infrastructure.llm import generate
        try:
            from saathi.ai_lab import default_registry
            prompt = default_registry().render(prompt_name, brief=brief)
        except Exception:
            prompt = inline
        out = generate(ModelLabel.STANDARD, prompt, "Reply with ONLY JSON.", max_tokens=1000).text
        return json.loads(out.strip().strip("`").replace("json", "", 1))
    except Exception:
        return None


def _L(d, k):
    v = (d or {}).get(k)
    return v if isinstance(v, list) else ([v] if v else [])


# ── Research Department ───────────────────────────────────────────────────────
def research_report(plan: dict) -> dict:
    """Research Director → Research Report (facts, mistakes, examples, angle)."""
    topic = plan.get("topic", "")
    obj = _gen_json("mr-yeti.research-director", json.dumps(plan)[:900],
                    f"You are the Research Director for a Mr. Yeti IELTS episode on '{topic}'. "
                    'Reply ONLY as JSON: {"summary","key_facts":[],"common_mistakes":[],'
                    '"examples":[],"competitor_angle","audience_questions":[]}.')
    if obj:
        return {"topic": topic, "summary": obj.get("summary", ""),
                "key_facts": _L(obj, "key_facts"), "common_mistakes": _L(obj, "common_mistakes"),
                "examples": _L(obj, "examples"), "competitor_angle": obj.get("competitor_angle", ""),
                "audience_questions": _L(obj, "audience_questions")}
    return {"topic": topic, "summary": plan.get("objective", f"Core facts about {topic}."),
            "key_facts": [f"Definition and form of {topic}", "When to use it in IELTS"],
            "common_mistakes": ["Overusing it", "Wrong form", "Confusing with a similar structure"],
            "examples": ["A model IELTS sentence using it correctly"],
            "competitor_angle": "Most channels explain the rule; we lead with the mistake.",
            "audience_questions": [f"When do I use {topic}?", f"Is {topic} needed for Band 7?"]}


# ── Creative Department ───────────────────────────────────────────────────────
def creative_brief(plan: dict, research: dict) -> dict:
    """Creative Director → Creative Brief (audience, arc, tone, hook, visual dir)."""
    topic = plan.get("topic", "")
    ctx = json.dumps({"plan": plan, "research_summary": research.get("summary", "")})[:900]
    obj = _gen_json("mr-yeti.creative-brief", ctx,
                    f"You are the Creative Director for a Mr. Yeti IELTS episode on '{topic}'. "
                    'Reply ONLY as JSON: {"target_audience","teaching_style","story_arc","energy",'
                    '"emotion","humor","hook_style","cta","visual_direction","music_mood"}.')
    ch = plan.get("character") or {}
    base = {"target_audience": "IELTS self-study learners on mobile",
            "teaching_style": "one clear idea → real example → tiny action",
            "story_arc": "mistake → fix → confidence", "energy": "warm, upbeat",
            "emotion": "reassuring", "humor": "gentle", "hook_style": "question",
            "cta": "Practice free on pielts.web.app", "visual_direction": ch.get("style", "Pixar classroom"),
            "music_mood": "curious"}
    if obj:
        base.update({k: v for k, v in obj.items() if v})
    base["character_consistency"] = ch.get("name", "Mr. Yeti")
    return base


# ── Studio Executive (coordination, not creation) ─────────────────────────────
@dataclass
class Production:
    day: int
    episode: str
    topic: str
    status: str = "planned"          # planned→researched→briefed→scripted→ready|revision
    plan: dict = field(default_factory=dict)
    research: dict = field(default_factory=dict)
    creative: dict = field(default_factory=dict)
    script: dict = field(default_factory=dict)
    scene_package: dict = field(default_factory=dict)
    plan_check: dict = field(default_factory=dict)
    render_plan: dict = field(default_factory=dict)
    est_seconds: int = 0
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class StudioExecutive:
    """Runs the department pipeline; decides ready vs revision."""

    def produce(self, now: float | None = None) -> Production:
        from saathi.studio import plan_today
        from saathi.script_director import build_brief, write_script

        plan = plan_today(now).as_dict()
        p = Production(day=plan["day"], episode=plan["episode"], topic=plan["topic"], plan=plan)

        p.research = research_report(plan); p.status = "researched"
        p.creative = creative_brief(plan, p.research); p.status = "briefed"

        # Script Director consumes the enriched brief (plan + research + creative)
        brief = build_brief(plan, hook_style=p.creative.get("hook_style", "question"),
                            cta=p.creative.get("cta", "Practice free on pielts.web.app"))
        brief["research"] = {"key_facts": p.research.get("key_facts", []),
                             "common_mistakes": p.research.get("common_mistakes", []),
                             "examples": p.research.get("examples", [])}
        brief["creative"] = {k: p.creative.get(k) for k in
                             ("teaching_style", "story_arc", "energy", "emotion", "humor")}
        doc = write_script(brief)
        p.script = doc.as_dict(); p.est_seconds = doc.est_seconds; p.status = "scripted"

        # Visual Department — Scene Package (image prompts, camera, motion, character)
        try:
            from saathi.studio_visual import scene_package
            p.scene_package = scene_package(p.script); p.status = "storyboarded"
        except Exception:
            p.scene_package = {}

        # Production Planner (gate) → Render Director (how-to-render manifest)
        try:
            from saathi.production_planner import validate
            from saathi.render_director import plan as render_plan
            p.plan_check = validate(p.scene_package)
            if p.plan_check.get("ok"):
                p.render_plan = render_plan(p.scene_package, episode=p.episode); p.status = "planned"
        except Exception:
            p.plan_check = {"ok": False, "issues": ["planner error"]}

        # ready-vs-revision gate
        ok = (bool(doc.hook) and len(doc.scenes) >= 3 and bool(doc.cta)
              and 20 <= doc.est_seconds <= 400 and bool(p.scene_package.get("scenes"))
              and p.plan_check.get("ok"))
        p.status = "ready" if ok else "revision"
        if not ok:
            p.notes.append("Needs revision: missing hook/CTA, too few scenes, or bad duration.")
        return p


def default_executive() -> StudioExecutive:
    return StudioExecutive()
