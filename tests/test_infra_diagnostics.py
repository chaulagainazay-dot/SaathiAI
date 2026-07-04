"""Unified infrastructure diagnostics + health score (Audit 11 / Step 5)."""
from saathi.infrastructure.diagnostics import health_score, snapshot
from saathi.infrastructure.connectors import ConnectorRegistry, install_defaults


def test_health_score_all_green():
    models = [{"id": "a", "available": True}, {"id": "b", "available": True}]
    browser = [{"id": "http", "available": True}, {"id": "playwright", "available": True},
               {"id": "camofox", "available": True}]
    connectors = [{"status": "ok"}, {"status": "degraded"}]
    conversation = {"voice": {"available": True}}
    s = health_score(models, browser, connectors, conversation)
    assert s == {"overall": 100, "models": 100, "browser": 100, "connectors": 100, "voice": 100}


def test_browser_weighting_http_only():
    s = health_score([], [{"id": "http", "available": True},
                          {"id": "playwright", "available": False},
                          {"id": "camofox", "available": False}], [], {})
    assert s["browser"] == 60          # HTTP essential (0.6), JS tiers optional


def test_connectors_percentage():
    s = health_score([], [], [{"status": "ok"}, {"status": "auth"}, {"status": "down"},
                              {"status": "degraded"}], {})
    assert s["connectors"] == 50       # 2 usable of 4


def test_snapshot_structure_and_score():
    snap = snapshot(registry=install_defaults(ConnectorRegistry()))
    assert set(snap) == {"models", "browser", "connectors", "conversation", "score"}
    assert {"overall", "models", "browser", "connectors", "voice"} <= set(snap["score"])
    ids = {c["id"] for c in snap["connectors"]}
    assert {"telegram", "github", "n8n", "browser", "youtube", "filesystem"} <= ids
    assert 0 <= snap["score"]["overall"] <= 100
