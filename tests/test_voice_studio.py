"""Voice Studio — Voice Director (Voice Package) + Voice Experiments."""
import tempfile, os
from saathi.missions.brand import BrandStore
from saathi.missions.voice_director import package, available_providers, pick_provider, _PROVIDERS


def _s():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return BrandStore(p)


def test_voice_package_reads_active_voice_provider_agnostic():
    s = _s()
    v = s.register_voice("M1", "Ajay", {"style": "teacher", "emotion": "encouraging",
                                        "provider": "kokoro", "speed": 1.05, "accent": "Nepali"})
    s.set_active_voice("M1", v["id"])
    pkg = package("M1", scene_emotion="excited", objective="hook", store=s)
    assert pkg["voice_name"] == "Ajay" and pkg["has_active_voice"]
    assert pkg["scene_emotion"] == "excited"                # scene overrides base
    assert pkg["base_emotion"] == "encouraging"
    assert pkg["delivery"]["rate"] == 1.1                   # excited hint
    assert pkg["provider"] in _PROVIDERS                    # resolved to an available provider


def test_voice_package_no_active_voice_is_honest():
    s = _s()
    pkg = package("EMPTY", store=s)
    assert pkg["has_active_voice"] is False
    assert "No active voice" in pkg["note"] and pkg["provider"] == pick_provider()


def test_provider_selection_prefers_available_then_falls_back():
    avail = available_providers()
    assert "silent" in avail                                # always available fallback
    assert pick_provider("elevenlabs") in avail             # unkeyed premium → falls back, never crashes


def test_experiments_lifecycle():
    s = _s()
    e = s.create_experiment("M1", episode="EP-21", voice_a="Ajay", voice_b="Rachel", split=50)
    assert e["status"] == "running" and e["split"] == 50
    assert s.resolve_experiment(e["id"], "Ajay", {"retention": "+14%"}) is True
    got = s.get_experiment(e["id"])
    assert got["status"] == "done" and got["winner"] == "Ajay"
    assert got["metrics"]["retention"] == "+14%"
    assert len(s.experiments("M1")) == 1


def test_experiments_scoped_per_mission():
    s = _s()
    s.create_experiment("M1", episode="a", voice_a="x", voice_b="y")
    s.create_experiment("M2", episode="b", voice_a="x", voice_b="y")
    assert len(s.experiments("M1")) == 1 and len(s.experiments("M2")) == 1
