"""Visual Department (Scene Package) + Director Registry."""
from saathi.studio_visual import scene_package, character_block
from saathi.production.director_registry import DirectorRegistry, default_registry


def _script():
    return {"scenes": [
        {"n": 1, "narration": "Hook line", "visual": "Mr. Yeti greets", "camera": "slow zoom", "seconds": 8},
        {"n": 2, "narration": "Teach point", "visual": "whiteboard", "seconds": 16},
        {"n": 3, "narration": "Example", "visual": "example on screen", "seconds": 12},
        {"n": 4, "narration": "CTA", "visual": "Mr. Yeti waves", "seconds": 8}]}


def test_scene_package_is_fully_specified():
    pkg = scene_package(_script())
    assert pkg["scene_count"] == 4 and pkg["est_seconds"] == 44
    s = pkg["scenes"][0]
    for k in ("scene", "purpose", "duration", "narration", "character", "camera",
              "motion", "image_prompt", "transition", "subtitle_style", "image_providers"):
        assert k in s
    assert pkg["scenes"][0]["purpose"] == "Hook" and pkg["scenes"][-1]["purpose"] == "CTA"
    assert s["character"]["name"] == "Mr. Yeti"          # Character Director injected
    assert s["camera"]["shot"] and s["image_providers"][0] == "flux"


def test_character_block_from_bible():
    ch = character_block()
    assert ch["name"] == "Mr. Yeti" and ch["style"]


def test_director_registry_capability_routing():
    reg = default_registry()
    caps = reg.capabilities()
    assert "storyboard_generation" in caps and "research" in caps and "business_strategy" in caps
    best = reg.best("storyboard_generation")
    assert best is not None and best.name == "storyboard"
    # agency director reachable by capability
    assert reg.best("business_strategy").source == "agency"
    # premium quality prefers tier-1 builtins for research
    assert reg.best("research", quality="premium").quality_tier == 1


def test_registry_best_is_runnable():
    reg = default_registry()
    spec = reg.best("storyboard_generation")
    out = spec.run(script={"scenes": [{"n": 1, "narration": "x", "visual": "y", "seconds": 10}]})
    assert out["scene_count"] == 1
