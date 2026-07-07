"""Saathi Workspace — modes, GitHub detection, repo-analysis compare, mission context."""
from saathi.workspace import detect_github, MODES, _SAATHI_CAPS, mission_context


def test_github_detection():
    assert detect_github("check https://github.com/openai/openai-agents-python please") \
        == "https://github.com/openai/openai-agents-python"
    assert detect_github("no url here") is None


def test_modes_defined():
    assert set(MODES) == {"research", "planning", "implementation", "cowork"}


def test_capability_map_covers_core_subsystems():
    caps = set(_SAATHI_CAPS)
    assert {"Prompt Registry", "Knowledge Graph", "Evidence Store", "Director Registry",
            "Mission OS", "Workflow Engine"} <= caps


def test_repo_analysis_compare_logic(monkeypatch):
    # stub the importer so no network — feed a known summary/tags
    import saathi.workspace as ws
    def fake_import(url, category="AI Engineering"):
        return {"ok": True, "source": {"title": "OpenHands", "summary": "autonomous coding agent that "
                "edits code, opens PRs, commits to a repository in a sandbox", "tags": ["agent", "code", "sandbox"],
                "related_directors": ["research"]}}
    monkeypatch.setattr("saathi.knowledge_library.importer.import_repo", fake_import)
    a = ws.analyze_repo("https://github.com/All-Hands-AI/OpenHands")
    assert a["kind"] == "repo_analysis" and a["stored_in_library"]
    assert "Director Registry" in a["overlap"]              # 'agent' overlaps our director cap
    assert "Engineering Tool" in a["integration"]           # coding agent → engineering tool, not runtime
    assert "Import as:" in a["recommendation"]


def test_repo_analysis_voice_repo_maps_to_provider(monkeypatch):
    import saathi.workspace as ws
    monkeypatch.setattr("saathi.knowledge_library.importer.import_repo",
                        lambda url, category="AI Engineering": {"ok": True, "source": {
                            "title": "Tiny TTS", "summary": "a small text to speech voice model",
                            "tags": ["tts", "voice"], "related_directors": ["research"]}})
    a = ws.analyze_repo("https://github.com/x/tiny-tts")
    assert "Provider adapter" in a["integration"]


def test_mission_context_no_mission():
    assert "No Mission" in mission_context(None)


def test_extract_steps_from_plan():
    from saathi.workspace import _extract_steps
    txt = "Plan:\n1. Research competitors\n2) Audit the website\n- Fix meta tags\nrandom line\n* Publish"
    steps = _extract_steps(txt)
    assert steps == ["Research competitors", "Audit the website", "Fix meta tags", "Publish"]


def test_decision_hint_triggers_capture(monkeypatch, tmp_path):
    import saathi.workspace as ws
    calls = {"tl": [], "node": []}
    class TL:
        def record(self, mid, kind, title, detail=""): calls["tl"].append((kind, title))
    class G:
        def upsert(self, mid, t, k, label="", data=None, source=""): calls["node"].append(t)
    import saathi.missions.timeline as tlm, saathi.missions.knowledge as kn
    monkeypatch.setattr(tlm, "default_store", lambda: TL())
    monkeypatch.setattr(kn, "default_graph", lambda: G())
    out = ws._capture({"id": "M1"}, "should we use X?", "I recommend importing X as a tool.", "cowork")
    assert "timeline" in out and "decision_node" in out
    assert calls["tl"][0][0] == "decision" and "decision" in calls["node"]
