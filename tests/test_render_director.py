"""Production Planner (gate) + Render Director (orchestrator + adapters)."""
from saathi.production_planner import validate
from saathi.render_director import plan, pick_adapter, available_adapters, ADAPTERS


def _pkg(ok=True):
    ch = {"name": "Mr. Yeti"}
    scenes = [{"scene": i, "purpose": "Hook" if i == 1 else "Teaching", "duration": 12,
               "narration": "" if (not ok and i == 2) else f"line {i}",
               "image_prompt": f"prompt {i}", "character": ch, "background": "classroom",
               "motion": "ken burns", "transition": "fade", "music": "calm"} for i in range(1, 5)]
    return {"scenes": scenes, "scene_count": 4, "est_seconds": 48}


def test_planner_passes_complete_package():
    r = validate(_pkg(ok=True))
    assert r["ok"] and not r["issues"]
    assert r["total_seconds"] == 48 and r["est_cost"] >= 0


def test_planner_flags_incomplete():
    r = validate(_pkg(ok=False))
    assert r["ok"] is False
    assert any("missing narration" in i for i in r["issues"])


def test_render_director_plans_manifest():
    rp = plan(_pkg(), episode="EP-004")
    assert rp["episode"] == "EP-004" and rp["scene_count"] == 4
    assert rp["adapter"] in ADAPTERS
    s = rp["scenes"][0]
    for k in ("image_engine", "voice_engine", "motion", "subtitle", "transition", "kind"):
        assert k in s
    assert s["kind"] == "character"                    # Hook → character scene
    assert rp["settings"]["fps"] == 25 and rp["engines"]["image"]


def test_adapter_selection_ffmpeg_fallback():
    assert "ffmpeg" in ADAPTERS
    # ffmpeg always the safety net; premium adapters inert without keys
    a = pick_adapter()
    assert a in ADAPTERS
    assert ADAPTERS["runway"].available() is False     # no RUNWAY_API_KEY


def test_render_director_in_registry():
    from saathi.production.director_registry import default_registry
    reg = default_registry()
    assert "render_planning" in reg.capabilities()
    best = reg.best("render_planning")
    assert best and best.name == "render"
    out = best.run(scene_package=_pkg(), episode="EP-1")
    assert out["scene_count"] == 4
