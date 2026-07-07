"""Production Automation — credits, scheduler/cost-optimizer, character verify, quality, plan."""
import tempfile, os
from saathi.production_automation.credits import CreditManager
from saathi.production_automation.scheduler import assign_scenes, retry_plan
from saathi.production_automation.quality import verify_scene, verify_package, quality_gate
from saathi.production_automation.pipeline import build_plan, ProductionStore


def _cm():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return CreditManager(p)


def test_credit_manager_seeds_and_reserves():
    cm = _cm()
    ff = cm.get("ffmpeg")
    assert ff["unlimited"] and ff["status"] == "active"
    # keyed providers with no env key are inactive (honest — no access it can't prove)
    assert cm.get("heygen")["status"] in ("active", "no_key")
    assert cm.reserve("ffmpeg", 5) is True               # unlimited always ok
    # ffmpeg unlimited never decrements
    assert cm.get("ffmpeg")["remaining"] == -1


def test_available_is_cost_then_quality_ranked():
    cm = _cm()
    av = cm.available()
    assert av and av[0]["cost"] <= av[-1]["cost"]        # cheapest first
    assert any(p["name"] == "ffmpeg" for p in av)        # local always available


def test_assign_scenes_cost_optimises_and_falls_back():
    cm = _cm()
    res = assign_scenes(5, manager=cm, reserve=True)
    assert res["scene_count"] == 5 and len(res["assignments"]) == 5
    # with no API keys set, everything falls to the free local net → cost 0
    assert res["est_cost"] == 0.0
    assert all(a["provider"] for a in res["assignments"])


def test_retry_switches_provider():
    cm = _cm()
    r = retry_plan("ffmpeg", manager=cm)
    assert r["policy"] == "retry_once_then_switch" and r["switch_to"]


def test_character_verify_structural():
    good = {"character": {"name": "Mr. Yeti"}, "image_prompt": "Mr Yeti with white fur, round glasses, "
            "teacher shirt, kind eyes, friendly face", "background": "classroom"}
    bad = {"character": {"name": "Someone"}, "image_prompt": "a person standing"}
    g = verify_scene(good, {"name": "Mr. Yeti"})
    b = verify_scene(bad, {"name": "Mr. Yeti"})
    assert g["score"] > b["score"] and g["method"] == "structural"
    assert "fur" in g["present"] and b["missing"]


def test_quality_gate_checklist():
    q = quality_gate(script={"hook": "h", "cta": "c", "est_seconds": 60, "captions": "x", "seo": {"title": "t"}},
                     render_plan={"engines": {"voice": "kokoro"}, "settings": {"resolution": "1920x1080"}, "logo": None},
                     character={"all_pass": True})
    assert q["checks"]["hook"] and q["checks"]["duration"] and q["passed"]
    bad = quality_gate(script={}, render_plan={}, character={"all_pass": False})
    assert not bad["passed"] and "hook" in bad["failed"]


def test_build_plan_and_approval_modes():
    pkg = {"scenes": [{"character": {"name": "Mr. Yeti"},
                       "image_prompt": "Mr Yeti white fur round glasses shirt eyes face", "background": "classroom"}
                      for _ in range(4)]}
    script = {"hook": "h", "cta": "c", "est_seconds": 60, "captions": "x", "seo": {"t": 1}}
    rp = {"engines": {"voice": "kokoro"}, "settings": {"resolution": "1920x1080"}, "logo": None}
    auto = build_plan(pkg, render_plan=rp, script=script, bible={"name": "Mr. Yeti"}, approval_mode="auto")
    assert auto["scene_count"] == 4 and len(auto["assignments"]) == 4
    assert auto["action"] in ("publish", "retry")
    semi = build_plan(pkg, render_plan=rp, script=script, bible={"name": "Mr. Yeti"}, approval_mode="semi")
    assert semi["approval_mode"] == "semi"
    manual = build_plan(pkg, approval_mode="manual")
    assert manual["action"] == "hold_for_manual"


def test_approval_mode_setting_persists():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    st = ProductionStore(p)
    assert st.approval_mode() == "semi"                  # default
    assert st.set_approval_mode("auto") is True
    assert st.set_approval_mode("bogus") is False
    assert st.approval_mode() == "auto"
