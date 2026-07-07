"""Reference Intelligence Department — classify, route, patterns, multi-compare."""
from saathi.missions.reference import classify, analyze_one, _DEFERRED


def test_classify_reference_types():
    assert classify("https://github.com/x/y") == "github"
    assert classify("https://youtube.com/watch?v=1") == "video_youtube"
    assert classify("https://instagram.com/mryeti") == "social_instagram"
    assert classify("https://tiktok.com/@x") == "video_tiktok"
    assert classify("https://linkedin.com/in/ajay") == "social_linkedin"
    assert classify("https://play.google.com/store/apps/x") == "app_store"
    assert classify("https://acme.com/brochure.pdf") == "pdf"
    assert classify("https://acme.com") == "website"


def test_deferred_types_are_honest():
    r = analyze_one("https://play.google.com/store/apps/details?id=x")
    assert r["ok"] is False and "deferred_reason" in r
    assert "pdf" in _DEFERRED and "figma" in _DEFERRED


def test_github_routes_to_importer(monkeypatch):
    import saathi.missions.reference as ref
    monkeypatch.setattr("saathi.knowledge_library.importer.import_repo",
                        lambda url, category="AI Engineering": {"ok": True, "source": {
                            "title": "OpenHands", "tags": ["agent", "code"], "summary": "coding agent",
                            "related_directors": ["research"]}})
    r = analyze_one("https://github.com/All-Hands-AI/OpenHands")
    assert r["kind"] == "github" and r["ok"] and "agent" in r["patterns"]


def test_video_analyzer_reports_measured_and_deferred(monkeypatch):
    import saathi.missions.reference as ref
    monkeypatch.setattr(ref, "_meta", lambda url, timeout=12.0: {"ok": True, "title": "How to score Band 9",
                        "description": "IELTS tips", "image": "thumb.jpg"})
    r = analyze_one("https://youtube.com/watch?v=abc")
    assert r["kind"] == "video_youtube" and r["title"] == "How to score Band 9"
    assert "thumbnail style" in r["patterns"]
    assert any("retention" in d for d in r["deferred"])       # honest about what it can't measure


def test_workspace_routes_multiple_references():
    from saathi.workspace import _all_urls
    urls = _all_urls("analyze these websites https://a.com and https://b.com and compare")
    assert urls == ["https://a.com", "https://b.com"]
