"""Client Intake — Create New Project (capture → research → strategy)."""
from saathi.client_intake import IntakeStore, research_project, STEPS


def _store(tmp_path):
    return IntakeStore(db_path=str(tmp_path / "ci.db"))


def test_create_gives_id_and_share_token(tmp_path):
    s = _store(tmp_path)
    p = s.create({"company": {"name": "WanderOn Travels"}})
    assert p["id"] and p["token"] and p["status"] == "draft"
    assert p["name"] == "WanderOn Travels"
    assert s.get_by_token(p["token"])["id"] == p["id"]


def test_update_merges_steps_and_renames(tmp_path):
    s = _store(tmp_path)
    p = s.create({})
    assert p["name"] == "Untitled Project"
    s.update(p["id"], {"company": {"name": "Acme", "industry": "Travel"}})
    s.update(p["id"], {"goals": "Grow bookings", "audience": "Honeymooners"})
    got = s.get(p["id"])
    assert got["name"] == "Acme"
    assert got["data"]["company"]["industry"] == "Travel"
    assert got["data"]["goals"] == "Grow bookings" and got["data"]["audience"] == "Honeymooners"


def test_public_form_submit_flow(tmp_path):
    s = _store(tmp_path)
    p = s.create({})
    # client opens the link (token) and submits
    s.update(p["id"], {"company": {"name": "Client Co", "website": "x.com"}}, status="submitted")
    got = s.get_by_token(p["token"])
    assert got["status"] == "submitted" and got["data"]["company"]["website"] == "x.com"


def test_research_produces_research_and_strategy(tmp_path):
    s = _store(tmp_path)
    p = s.create({"company": {"name": "WanderOn"}, "goals": "grow", "audience": "travelers"})
    research, strategy = research_project(s.get(p["id"]))          # no LLM → deterministic fallback
    assert research["summary"] and isinstance(research["opportunities"], list)
    assert strategy["direction"] and isinstance(strategy["next_steps"], list)
    out = s.set_output(p["id"], research, strategy)
    assert out["status"] == "ready" and out["research"]["summary"]


def test_seven_capture_steps():
    assert STEPS == ["company", "goals", "audience", "services", "budget", "uploads", "review"]
