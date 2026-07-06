"""Publishing Director → per-platform Publishing Package."""
from saathi.publishing_director import package, PLATFORMS, SCHEDULE


def _script():
    return {"episode": "EP-007", "topic": "Present Perfect for IELTS",
            "hook": "Most Band 6 writers misuse present perfect — here's the one rule that fixes it.",
            "cta": "Practice free on pielts.web.app",
            "thumbnail_ideas": ["Mr. Yeti holding a giant clock"],
            "seo": {"title": "Present Perfect: the Band 7 rule most learners miss",
                    "description": "A 60-second Mr. Yeti lesson on when to use present perfect in IELTS.",
                    "tags": ["ielts", "grammar", "present perfect", "band 7", "english"]}}


def test_package_covers_every_platform():
    pkg = package(_script(), episode="EP-007")
    assert pkg["ok"] and not pkg["issues"]
    assert pkg["platform_count"] == len(SCHEDULE)
    names = {e["platform"] for e in pkg["platforms"]}
    assert {"youtube", "tiktok", "instagram", "telegram", "blog", "pielts"} <= names


def test_per_platform_caps_and_hashtags():
    pkg = package(_script())
    yt = next(e for e in pkg["platforms"] if e["platform"] == "youtube")
    blog = next(e for e in pkg["platforms"] if e["platform"] == "blog")
    assert len(yt["title"]) <= PLATFORMS["youtube"]["title"]
    assert yt["hashtags"] and yt["hashtags"][0].startswith("#")   # video platform → hashtags
    assert all(not t.startswith("#") for t in blog["hashtags"])    # blog → plain tags
    assert "pielts.web.app" in yt["description"]                   # CTA folded into body


def test_schedule_is_staggered_and_subset_selectable():
    pkg = package(_script(), platforms=["youtube", "telegram"])
    assert pkg["schedule"] == ["youtube", "telegram"]
    assert [e["schedule_slot"] for e in pkg["platforms"]] == [0, 1]


def test_empty_script_falls_back_gracefully():
    pkg = package({"seo": {}}, episode="EP-0")
    # never hard-fails: fallback title keeps the package valid
    assert pkg["ok"] is True
    assert pkg["master"]["title"] == "IELTS lesson"


def test_publishing_in_registry():
    from saathi.production.director_registry import default_registry
    reg = default_registry()
    assert "publishing" in reg.capabilities()
    best = reg.best("publishing")
    assert best and best.name == "publishing"
    out = best.run(script=_script(), episode="EP-9")
    assert out["platform_count"] == len(SCHEDULE)
