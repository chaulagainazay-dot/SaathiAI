"""v0.4.1 generation stack — Creative Director, quality, music, images, render."""
import os
import shutil

import pytest


def test_creative_director_deterministic_brief():
    from saathi.creative_director import direct
    script = {"hook": "Struggling with tenses?", "teaching": ["Rule one.", "Rule two."],
              "examples": "I had eaten.", "cta": "pielts.web.app"}
    b = direct("past perfect", script)
    assert b["style"] and b["voice_tone"] and b["music_mood"] and b["camera"]
    assert len(b["scenes"]) >= 4
    assert all(s["narration"] and s["seconds"] > 0 for s in b["scenes"])


def test_quality_policy_levels():
    from saathi.quality import policy, DRAFT, PREMIUM
    assert policy(DRAFT)["est_cost"] == 0.0
    assert policy(PREMIUM)["est_cost"] > 0
    assert policy("nonsense") == policy(DRAFT)          # safe default


def test_music_selector(tmp_path, monkeypatch):
    from saathi.tools import music
    monkeypatch.setenv("SAATHI_MUSIC_DIR", str(tmp_path))
    assert music.select("curious") is None              # empty folder → no music
    (tmp_path / "mystery.mp3").write_bytes(b"x")
    (tmp_path / "calm.mp3").write_bytes(b"x")
    assert music.select("curious").endswith("mystery.mp3")   # mood alias curious→mystery
    assert music.select("unknown").endswith("calm.mp3")      # deterministic first-track fallback


def test_images_card_fallback(tmp_path):
    pytest.importorskip("PIL")
    from saathi.tools.images import generate_scene_images
    script = {"hook": "Intro line.", "teaching": ["Point one."], "examples": "Ex.", "cta": "CTA."}
    paths = generate_scene_images(script, out_dir=str(tmp_path))
    assert len(paths) >= 3 and all(os.path.getsize(p) > 0 for p in paths)


def test_voice_say_fallback(tmp_path):
    if not (shutil.which("say") and shutil.which("ffmpeg")):
        pytest.skip("no say/ffmpeg")
    from saathi.tools.voice import synthesize
    data = synthesize("Hello from Mr Yeti.", chain=("say",))
    assert data and data[:4] == b"RIFF"                 # valid WAV


@pytest.mark.skipif(os.getenv("SAATHI_SLOW") != "1", reason="slow render; set SAATHI_SLOW=1")
def test_ffmpeg_render_end_to_end(tmp_path):
    from saathi.tools.images import generate_scene_images
    from saathi.tools.voice import synthesize
    from saathi.tools.render import render_video
    imgs = generate_scene_images({"hook": "a", "teaching": ["b"], "examples": "c", "cta": "d"},
                                 out_dir=str(tmp_path / "assets"))
    wav = tmp_path / "n.wav"; wav.write_bytes(synthesize("one two three", chain=("say",)))
    out = render_video(voice=str(wav), images=imgs, out=str(tmp_path / "v.mp4"))
    assert out and os.path.getsize(out) > 0
