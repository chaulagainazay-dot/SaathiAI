"""Brand Identity Department + versioned Voice Registry."""
import tempfile, os
from saathi.missions.brand import (BrandStore, default_brand, recommend, analyze_samples,
                                    SAMPLE_PROMPTS)


def _s():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return BrandStore(p)


def test_sample_prompts_cover_the_spectrum():
    labels = {p["label"] for p in SAMPLE_PROMPTS}
    assert {"Intro", "Grammar Lesson", "Conversation", "Story", "Emotion"} <= labels


def test_default_brand_personality_per_department():
    assert default_brand({"department": "ai_studio"})["voice_defaults"]["style"] == "teacher"
    assert "adventurous" in default_brand({"department": "travel"})["voice_defaults"]["emotion"]
    assert default_brand({"department": "hcg"})["voice_defaults"]["style"] == "analyst"


def test_voice_versions_increment_per_name():
    s = _s()
    v1 = s.register_voice("M1", "Ajay", {"style": "teacher", "provider": "kokoro"})
    v2 = s.register_voice("M1", "Ajay", {"style": "teacher", "provider": "kokoro", "speed": 1.05})
    assert v1["version"] == 1 and v2["version"] == 2
    assert len(s.list_voices("M1")) == 2


def test_recommendation_from_style():
    r = recommend({"style": "teacher"})
    assert "IELTS Teacher" in r["best_for"] and r["not_ideal"]
    assert "Market updates" in recommend({"style": "analyst"})["best_for"]


def test_analysis_is_honest_estimate():
    a = analyze_samples([{"text": "one two three four five", "duration": 2.0}])
    assert a["estimated"] is True and a["wpm"] == 150   # 5 words / (2s/60)
    assert analyze_samples([{"text": "hi"}])["wpm"] is None  # no duration → no fabricated wpm


def test_active_voice_is_what_directors_read():
    s = _s()
    va = s.register_voice("M1", "Ajay", {"style": "teacher"})
    vb = s.register_voice("M1", "MrYeti", {"style": "teacher", "emotion": "encouraging"})
    assert s.set_active_voice("M1", vb["id"]) is True
    assert s.active_voice("M1")["id"] == vb["id"]
    assert s.set_active_voice("M1", "bogus") is False
    # brand carries the pointer
    assert s.get_brand("M1")["active_voice_id"] == vb["id"]
