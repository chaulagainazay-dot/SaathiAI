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
