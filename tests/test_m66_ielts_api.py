from fastapi.testclient import TestClient

from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


def client_and_headers(tmp_path, monkeypatch):
    reset_registry_for_tests()
    svc = reset_platform_for_tests(tmp_path / "ielts-api.db")
    import saathi.platform.api as apimod
    import saathi.platform.service as svcmod
    monkeypatch.setattr(svcmod, "_DEFAULT", svc)
    monkeypatch.setattr(apimod, "default_platform", lambda: svc)
    from saathi.server import app
    client = TestClient(app)
    client.post("/api/v1/platform/bootstrap", json={"email": "ielts@local", "name": "Learner"})
    token = client.post("/api/v1/platform/auth/login", json={"email": "ielts@local"}).json()["token"]
    return client, {"X-Platform-Token": token}


def test_all_ielts_routes_require_authentication(tmp_path, monkeypatch):
    client, _ = client_and_headers(tmp_path, monkeypatch)
    for method, path, payload in (
        ("get", "/dashboard", None),
        ("get", "/records", None),
        ("get", "/health", None),
        ("post", "/profile", {"display_name": "x"}),
        ("post", "/goals", {"exam_type": "academic", "target_band": 7, "planned_test_date": "2030-01-01"}),
        ("post", "/practice", {"skill": "reading", "task_type": "fixture", "prompt": "p", "response": "a"}),
        ("post", "/alerts", {"exam_type": "academic", "preferred_locations": ["Kathmandu"],
                              "date_from": "2030-01-01", "date_to": "2030-02-01", "expires_on": "2030-02-01"}),
        ("post", "/payments", {"product": "p", "amount": "1", "payment_method_label": "bank",
                                "transaction_reference": "r", "evidence_ref": "ev"}),
    ):
        kwargs = {"json": payload} if payload is not None else {}
        response = getattr(client, method)(f"/api/v1/platform/ielts{path}", **kwargs)
        assert response.status_code == 401, path


def test_authenticated_minimum_learner_journey(tmp_path, monkeypatch):
    client, headers = client_and_headers(tmp_path, monkeypatch)
    assert client.post("/api/v1/platform/ielts/profile", headers=headers,
                       json={"display_name": "Local Learner"}).status_code == 200
    goal = client.post(
        "/api/v1/platform/ielts/goals", headers=headers,
        json={"exam_type": "academic", "target_band": 7.0,
              "planned_test_date": "2030-02-01", "idempotency_key": "g1"},
    )
    assert goal.status_code == 200
    writing = client.post(
        "/api/v1/platform/ielts/practice", headers=headers,
        json={"skill": "writing", "task_type": "task_2", "prompt": "Discuss a local park.",
              "response": "A local park matters because it gives people a calm place. "
                          "However, communities should maintain it carefully.",
              "idempotency_key": "w1"},
    ).json()["practice"]
    assert writing["body"]["feedback"]["label"] == "practice estimate"
    assert writing["body"]["feedback"]["official"] is False
    alert = client.post(
        "/api/v1/platform/ielts/alerts", headers=headers,
        json={"exam_type": "academic", "preferred_locations": ["Kathmandu"],
              "date_from": "2030-01-01", "date_to": "2030-02-01",
              "expires_on": "2030-02-01"},
    )
    assert alert.status_code == 200
    match = client.post("/api/v1/platform/ielts/alerts/evaluate", headers=headers).json()
    assert match["live_availability"] is False
    payment = client.post(
        "/api/v1/platform/ielts/payments", headers=headers,
        json={"product": "Local plan", "amount": "1000", "currency": "NPR",
              "payment_method_label": "bank transfer", "transaction_reference": "local-ref",
              "evidence_ref": "evidence://local/ref"},
    )
    assert payment.status_code == 200
    dashboard = client.get("/api/v1/platform/ielts/dashboard", headers=headers).json()["dashboard"]
    assert dashboard["goal"]["body"]["target_band"] == 7.0
    assert dashboard["progress"]["practice_count"] == 1
    assert dashboard["scoring"]["provider_assisted"] is False
    assert dashboard["manual_payment_only"] is True
    evidence = client.get("/api/v1/platform/ielts/evidence", headers=headers).json()["evidence"]
    assert any(x["event_type"] == "feedback.ready" for x in evidence)
    search = client.get("/api/v1/platform/ielts/search?q=writing", headers=headers).json()["results"]
    assert search and search[0]["record_type"] == "submission"


def test_validation_and_safe_404_do_not_leak(tmp_path, monkeypatch):
    client, headers = client_and_headers(tmp_path, monkeypatch)
    invalid = client.post(
        "/api/v1/platform/ielts/goals", headers=headers,
        json={"exam_type": "academic", "target_band": 7.3, "planned_test_date": "2030-01-01"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "VALIDATION_FAILED"
    missing = client.get("/api/v1/platform/ielts/records/not-real", headers=headers)
    assert missing.status_code == 404
    assert "sqlite" not in missing.text.lower()
    assert "/users/" not in missing.text.lower()


def test_logout_revokes_ielts_api_access(tmp_path, monkeypatch):
    client, headers = client_and_headers(tmp_path, monkeypatch)
    assert client.get("/api/v1/platform/ielts/dashboard", headers=headers).status_code == 200
    assert client.post("/api/v1/platform/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/platform/ielts/dashboard", headers=headers).status_code == 401
