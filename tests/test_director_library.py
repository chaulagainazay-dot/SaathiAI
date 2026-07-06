"""Director Importer + Library — agency prompts → SaathiAI Directors."""
from saathi.production import agency_importer as imp
from saathi.production import director_library as dl
from saathi.ai_lab import PromptRegistry


def test_catalog_lists_curated_directors():
    cat = imp.catalog()
    assert len(cat) >= 8
    slugs = {c["slug"] for c in cat}
    assert "business-strategist" in slugs and "content-creator" in slugs
    for c in cat:
        assert c["name"] and c["slug"]


def test_import_registers_directors(tmp_path):
    reg = PromptRegistry(db_path=str(tmp_path / "lab.db"))
    n = imp.import_directors(registry=reg)
    assert n >= 8
    pv = reg.active("director.business-strategist")
    assert pv is not None and pv.project == "director-library"
    # template is render-safe (literal braces escaped) + has the {task} slot
    out = reg.render("director.business-strategist", task="Assess Surmount Travels")
    assert "Assess Surmount Travels" in out
    # idempotent — re-import bumps nothing
    assert imp.import_directors(registry=reg) == 0


def test_run_handles_missing_director(monkeypatch, tmp_path):
    reg = PromptRegistry(db_path=str(tmp_path / "lab.db"))
    monkeypatch.setattr("saathi.ai_lab.default_registry", lambda: reg)
    r = dl.run("nonexistent-director", "do something")
    assert r["ok"] is False and "unknown" in r["error"]


def test_list_directors_matches_catalog():
    assert len(dl.list_directors()) == len(imp.catalog())
