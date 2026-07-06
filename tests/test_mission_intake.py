"""Mission Intake + document extraction + Mission Health."""
import tempfile, os
from saathi.missions.knowledge import KnowledgeGraph
from saathi.missions.intake import apply_intake, extract_document
from saathi.missions.health import mission_health


def _g():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return KnowledgeGraph(p)


def test_intake_writes_many_nodes_and_raises_coverage():
    g = _g()
    before = g.coverage("M1")["overall"]
    res = apply_intake("M1", {
        "accounts": {"website": "acme.com", "instagram": "@acme", "facebook": "fb/acme"},
        "social_stats": {"instagram_followers": 4200},
        "revenue": {"amount": 150000, "source": "tours", "date": "2026-07"},
        "services": "Nepal Tours, Tibet Tours, Visa",
        "customers": ["Students", "Families"],
        "goals": "double bookings",
    }, graph=g)
    assert res["nodes_added"] >= 8
    assert res["coverage"] > before                      # coverage climbs from manual entry
    assert res["categories"]["revenue"] == 1.0 and res["categories"]["customer"] == 1.0
    assert len(g.nodes("M1", node_type="service")) == 3


def test_intake_split_handles_list_and_string():
    g = _g()
    apply_intake("M1", {"services": ["A", "B"]}, graph=g)
    apply_intake("M2", {"services": "A, B; C"}, graph=g)
    assert len(g.nodes("M1", node_type="service")) == 2
    assert len(g.nodes("M2", node_type="service")) == 3


def test_document_extraction_pulls_prices_and_contacts():
    g = _g()
    txt = "Nepal Tour NPR 45,000. Deluxe Rs. 90,000. Contact sales@acme.com or +977 9812345678."
    res = extract_document("M1", txt, title="Price List", graph=g)
    assert any("45,000" in p for p in res["extracted"]["prices"])
    assert "sales@acme.com" in res["extracted"]["emails"]
    assert res["extracted"]["phones"]
    assert g.nodes("M1", node_type="document")
    assert res["coverage"] > 0                            # document dim now filled


def test_mission_health_scores_functions_and_finds_weakest(monkeypatch):
    g = _g()
    apply_intake("MID", {"accounts": {"instagram": "@x", "facebook": "y"},
                         "revenue": {"amount": 1000, "date": "2026-07"},
                         "services": "A, B"}, graph=g)
    import saathi.missions.knowledge as kn
    monkeypatch.setattr(kn, "_default", g)
    monkeypatch.setattr(kn, "default_graph", lambda: g)
    h = mission_health({"id": "MID", "key": "none_key", "department": "travel"})
    assert 0 <= h["overall"] <= 1
    assert h["dimensions"]["revenue_tracking"] == 1.0    # revenue node present
    assert h["dimensions"]["marketing"] > 0              # social/account nodes present
    assert h["dimensions"]["automation"] == 0.0          # none wired → honest
    assert h["weakest"] in h["dimensions"]
