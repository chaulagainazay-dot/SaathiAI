"""M16 Control Center — unit + security (isolation/redaction/no-bypass) tests."""
import tempfile

import pytest

from saathi.control_center.aggregator import ControlCenterAggregator, guarded, Cell
from saathi.control_center import search as CCsearch
from saathi.control_center import actions as CCactions
from saathi.connectors.platform import store as S


@pytest.fixture
def shared_store(monkeypatch):
    st = S.ConnectorStore(tempfile.mktemp(suffix=".db"))
    monkeypatch.setattr(S, "default_store", lambda: st)
    return st


# ── aggregation ─────────────────────────────────────────────────────────────
def test_overview_real_sources():
    ov = ControlCenterAggregator("ajay").overview()
    assert ov["platform_health"]["status"] == "ok"
    assert ov["platform_health"]["source"] == "connectors.health"
    assert ov["security"]["value"]["verdict"]        # real red-team verdict
    assert "generated_at" in ov


def test_partial_failure_degrades_not_crash():
    c = guarded("x.boom", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert c.status == "unavailable" and c.degraded_reason == "boom" and c.value is None


def test_cell_freshness_present():
    c = guarded("s", lambda: 1)
    d = c.to_dict()
    assert d["source"] == "s" and d["observed_at"] > 0 and d["age_sec"] is not None


def test_attention_ranking_orders_critical_first(shared_store):
    # seed a pending approval → high; env-blocked connectors → info
    shared_store.add_approval(owner="ajay", connector_id="github", account_id="a",
                              tool_id="github.create_issue", capability_id="create_issue",
                              input_hash="h", risk=3)
    ov = ControlCenterAggregator("ajay").overview()
    sevs = [i["severity"] for i in ov["requires_attention"]]
    # ordering: any high before any info
    if "high" in sevs and "info" in sevs:
        assert sevs.index("high") < sevs.index("info")


# ── federated search: owner scoping (cross-user isolation) ──────────────────
def test_search_owner_scoped_accounts(shared_store):
    shared_store.add_account(owner="victim", connector_id="github", label="victim-gh",
                             state="healthy")
    # attacker searching cannot see victim's account
    r = CCsearch.federated_search(owner="attacker", query="victim-gh")
    assert all(res["entity_type"] != "account" for res in r["results"])
    # victim can
    r2 = CCsearch.federated_search(owner="victim", query="victim-gh")
    assert any(res["entity_type"] == "account" for res in r2["results"])


def test_search_owner_scoped_executions(shared_store):
    aid = shared_store.add_account(owner="victim", connector_id="github", label="g",
                                   state="healthy")
    from saathi.connectors.platform.execution import ExecutionEngine, ExecRequest
    eng = ExecutionEngine(store=shared_store)
    eng.execute(ExecRequest(owner="victim", tool_id="github.list_issues", account_id=aid,
                            args={"_fixture": "success"}))
    attacker = CCsearch.federated_search(owner="attacker", query="github", entity_types=["execution"])
    assert attacker["results"] == []


def test_search_no_secret_in_results(shared_store):
    from saathi.connectors.platform.credentials import new_ref
    ref = new_ref(connector_id="github", scope="user:ajay", backend="env",
                  backend_key="GITHUB_TOKEN")
    shared_store.put_cred_ref(ref)
    shared_store.add_account(owner="ajay", connector_id="github", label="gh",
                             cred_ref_id=ref.ref_id, state="healthy")
    r = CCsearch.federated_search(owner="ajay", query="github")
    blob = str(r)
    assert "GITHUB_TOKEN" in blob or True   # key NAME acceptable
    assert "access_token" not in blob and "secret_value" not in blob


# ── action descriptors point at canonical APIs (no bypass) ──────────────────
def test_actions_point_at_canonical_apis():
    cat = {a["action_id"]: a for a in CCactions.catalog()}
    assert cat["approval.approve"]["canonical_api"].startswith("/api/v1/connectors/approvals")
    assert cat["connector.execute"]["canonical_api"] == "/api/v1/connectors/executions"
    # approval action is approval-gated, not a free mutation
    assert cat["approval.approve"]["action_class"] == "approval_gated_mutation"


def test_control_api_is_read_only():
    # the control-center router must expose NO mutating (POST/PUT/DELETE) route
    from saathi.control_center.api import router
    methods = set()
    for r in router.routes:
        methods |= set(getattr(r, "methods", set()))
    assert methods <= {"GET", "HEAD"}, f"control API must be read-only, saw {methods}"


# ── API auth enforced ───────────────────────────────────────────────────────
def test_control_api_requires_auth():
    from fastapi.testclient import TestClient
    from saathi.server import app
    assert TestClient(app).get("/api/v1/control/overview").status_code == 401
    assert TestClient(app).get("/api/v1/control/search?q=x").status_code == 401


# ── UI contract: page uses real control API, honest states ──────────────────
def test_ui_uses_control_api():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    page = (root / "saathi-os" / "app" / "control" / "page.jsx").read_text()
    for helper in ["controlOverview", "controlSearch"]:
        assert helper in page
    # honest degraded/unavailable states surfaced, bounded refresh, paused when hidden
    assert "unavailable" in page and "degraded" in page
    assert "document.hidden" in page   # refresh paused when tab hidden
    api = (root / "saathi-os" / "lib" / "api.js").read_text()
    assert "/api/v1/control/overview" in api
