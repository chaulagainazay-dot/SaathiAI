"""Director Registry — provider-agnostic Directors, like the Model Router.

The Studio Executive never calls a specific implementation; it asks:

    reg.best(capability="storyboard_generation", quality="premium", cost="low")

Same flexibility SaathiAI has for models and connectors, now at the level of AI
expertise. Registers built-in Directors (research/creative/script/storyboard) and
the imported agency Directors, each with capabilities + quality/cost tiers.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DirectorSpec:
    name: str
    capabilities: frozenset
    quality_tier: int = 2          # 1 best … 3
    cost: float = 0.0
    source: str = "builtin"        # builtin | agency
    run: object = field(default=None, compare=False, repr=False)

    def info(self) -> dict:
        return {"name": self.name, "capabilities": sorted(self.capabilities),
                "quality_tier": self.quality_tier, "cost": self.cost, "source": self.source}


# capabilities inferred for imported agency Directors, by slug keyword
_AGENCY_CAPS = {
    "business-strategist": {"business_strategy", "strategy"},
    "growth-hacker": {"growth", "marketing"}, "content-creator": {"content", "marketing"},
    "email-strategist": {"email", "marketing"}, "linkedin-director": {"linkedin", "social", "marketing"},
    "instagram-director": {"instagram", "social", "marketing"}, "customer-success": {"customer_success"},
    "technical-writer": {"technical_writing", "docs"}, "ux-researcher": {"ux_research", "research"},
    "sales-discovery": {"sales"}, "experiment-tracker": {"experiment_tracking", "analytics"},
}


class DirectorRegistry:
    def __init__(self, specs: list[DirectorSpec] | None = None):
        self.specs = specs if specs is not None else _build_specs()

    def route(self, capability: str, *, quality: str = "balanced", cost: str = "any") -> list[DirectorSpec]:
        cands = [s for s in self.specs if capability in s.capabilities]
        if cost == "low":
            cands = [s for s in cands if s.cost <= 0.5]
        if quality == "premium":
            cands.sort(key=lambda s: (s.quality_tier, s.cost))
        elif quality == "cost":
            cands.sort(key=lambda s: (s.cost, s.quality_tier))
        else:  # balanced — cheap-first on quality tie
            cands.sort(key=lambda s: (s.cost, s.quality_tier))
        return cands

    def best(self, capability: str, **kw) -> DirectorSpec | None:
        chain = self.route(capability, **kw)
        return chain[0] if chain else None

    def capabilities(self) -> list[str]:
        c = set()
        for s in self.specs:
            c |= set(s.capabilities)
        return sorted(c)

    def catalog(self) -> list[dict]:
        return [s.info() for s in self.specs]


def _build_specs() -> list[DirectorSpec]:
    specs: list[DirectorSpec] = []
    # built-in department Directors (free — run on the Model Router / Gemini)
    try:
        from saathi.studio_directors import research_report, creative_brief
        from saathi.script_director import build_brief, write_script
        from saathi.studio_visual import scene_package
        specs += [
            DirectorSpec("research", frozenset({"research"}), 1, 0.0, "builtin",
                         run=lambda plan=None, **_: research_report(plan or {})),
            DirectorSpec("creative", frozenset({"creative_brief", "creative_direction"}), 1, 0.0, "builtin",
                         run=lambda plan=None, research=None, **_: creative_brief(plan or {}, research or {})),
            DirectorSpec("script", frozenset({"script_generation"}), 1, 0.0, "builtin",
                         run=lambda plan=None, brief=None, **_: write_script(brief or build_brief(plan or {})).as_dict()),
            DirectorSpec("storyboard", frozenset({"storyboard_generation", "visual_direction"}), 1, 0.0, "builtin",
                         run=lambda script=None, **_: scene_package(script or {})),
        ]
        from saathi.render_director import plan as _render_plan
        specs.append(DirectorSpec("render", frozenset({"render_planning", "render"}), 1, 0.0, "builtin",
                     run=lambda scene_package=None, episode="", **_: _render_plan(scene_package or {}, episode=episode)))
    except Exception:
        pass
    # imported agency Directors
    try:
        from saathi.production.agency_importer import catalog
        from saathi.production import director_library
        for d in catalog():
            slug = d["slug"]
            caps = _AGENCY_CAPS.get(slug, {slug.replace("-", "_")})
            specs.append(DirectorSpec(f"agency:{slug}", frozenset(caps), 2, 0.0, "agency",
                         run=(lambda s: lambda task="", **ctx: director_library.run(s, task, **ctx))(slug)))
    except Exception:
        pass
    return specs


_default = None
def default_registry() -> DirectorRegistry:
    global _default
    if _default is None:
        _default = DirectorRegistry()
    return _default
