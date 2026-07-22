"""M14 CEO OS test suite — unit, integration, security.

Missions execute through the REAL M10 orchestrator (injected fake executor);
no CEO-direct execution. KPI/finance/priority are deterministic. Security tests
prove no cross-user data, no agent self-approval, no fake unavailable metrics,
no financial actual/estimate leakage."""
import pytest

from saathi.ceo import (
    CEOStore, CEOService, CEOAgent, kpi as K, priority as PR, finance as FIN,
    project_health as PH, EvidenceTier, DecisionStatus, FinancialState,
    validate_decision_transition, IllegalDecisionTransition, PROTECTED_DECISION_STATES,
)
from saathi.financial_mission_control import DREAM_TARGET, dream_progress_pct


@pytest.fixture
def store(tmp_path):
    return CEOStore(tmp_path / "ceo.db")


def _orch(tmp_path):
    from saathi.agent_runtime.store import RunStore
    from saathi.agent_runtime.gateway_exec import AgentExecutor
    from saathi.agent_runtime.orchestrator import Orchestrator
    return Orchestrator(store=RunStore(tmp_path / "ar.db"),
                        executor=AgentExecutor(execute_fn=lambda r, p, s: {
                            "text": f"{r} done", "provider": "t", "tokens": 1,
                            "status": "success"}), memory=False)


# ── KPI engine + percentage semantics (unit) ────────────────────────────────
def test_kpi_unavailable_when_no_source(store):
    kid = store.add_kpi(owner="ajay", name="Dream", kpi_type="dream_progress",
                        target=DREAM_TARGET)
    kv = K.compute_kpi(store, kid)
    assert not kv.available and kv.value is None
    assert kv.evidence_tier == EvidenceTier.UNAVAILABLE.value  # never fabricated


def test_kpi_dream_pct_semantics_preserved(store):
    kid = store.add_kpi(owner="ajay", name="Dream", kpi_type="dream_progress",
                        target=DREAM_TARGET)
    store.add_observation(kid, value=79388.39, source="finance")
    kv = K.compute_kpi(store, kid)
    assert abs(kv.pct_to_target - 1.0) < 0.01
    assert kv.pct_to_target == dream_progress_pct(79388.39)


def test_kpi_regular_percentage_not_ratio(store):
    kid = store.add_kpi(owner="ajay", name="Users", kpi_type="users", target=1000)
    store.add_observation(kid, value=500, source="db")
    assert K.compute_kpi(store, kid).pct_to_target == 50.0


def test_kpi_trend(store):
    kid = store.add_kpi(owner="ajay", name="Views", kpi_type="views", target=100)
    store.add_observation(kid, value=40, source="yt")
    store.add_observation(kid, value=60, source="yt")
    assert K.compute_kpi(store, kid).trend == "up"


def test_goal_progress_from_observations_not_text(store):
    kid = store.add_kpi(owner="ajay", name="Rev", kpi_type="revenue", target=1000)
    gid = store.add_goal(owner="ajay", description="hit 1000", target_value=1000, kpi_id=kid)
    store.add_observation(kid, value=750, source="finance")
    p = K.goal_progress(store, gid)
    assert p["current"] == 750 and p["pct"] == 75.0
    assert p["evidence_tier"] == EvidenceTier.CALCULATED.value


# ── priority engine (deterministic + explainable) ───────────────────────────
def test_priority_deterministic_and_explained():
    inp = PR.PriorityInput(revenue_impact=1.0, dependency_blocking=True,
                          deadline_days=5, low_risk=True, provider_unavailable=True)
    s1, s2 = PR.score(inp), PR.score(inp)
    assert s1.score == s2.score and s1.factors
    labels = {f["label"] for f in s1.factors}
    assert "Revenue impact" in labels and "Required provider unavailable" in labels


def test_priority_penalty_lowers_score():
    hi = PR.score(PR.PriorityInput(revenue_impact=1.0))
    lo = PR.score(PR.PriorityInput(revenue_impact=1.0, provider_unavailable=True,
                                  high_effort=True))
    assert lo.score < hi.score


def test_priority_rank_orders():
    ranked = PR.rank([("a", PR.PriorityInput(revenue_impact=0.2)),
                      ("b", PR.PriorityInput(revenue_impact=1.0, dependency_blocking=True))])
    assert ranked[0]["id"] == "b"


# ── finance separation (unit) ───────────────────────────────────────────────
def test_finance_estimate_not_counted_as_actual(store):
    store.add_financial_entry(owner="ajay", kind="revenue", state="actual", amount_usd=235)
    store.add_financial_entry(owner="ajay", kind="revenue", state="estimated", amount_usd=5000)
    fs = FIN.financial_summary(store, "ajay")
    assert fs["actual_revenue"] == 235.0
    assert fs["by_state"]["estimated"]["revenue"] == 5000.0


def test_finance_no_actuals_flag(store):
    store.add_financial_entry(owner="ajay", kind="revenue", state="forecast", amount_usd=9999)
    assert FIN.financial_summary(store, "ajay")["has_actuals"] is False


def test_budget_variance(store):
    bid = store.add_budget(owner="ajay", scope="project", approved_usd=100)
    store.update_budget(bid, actual_usd=120)
    bv = FIN.budget_variance(store, bid)
    assert bv["over_budget"] and bv["variance"] == -20.0


# ── project health (evidence-backed) ────────────────────────────────────────
def test_project_health_blocked_with_evidence(store):
    store.add_risk(owner="ajay", title="x", category="provider", likelihood=0.9, impact=0.8)
    h = PH.project_health(store, "ajay", open_blockers=1, unresolved_approvals=2)
    assert h["health"] == "blocked" and h["evidence"]


def test_project_health_unknown_when_no_signals(store):
    assert PH.project_health(store, "ajay")["health"] == "unknown"


# ── decision lifecycle ──────────────────────────────────────────────────────
def test_decision_transitions():
    validate_decision_transition(DecisionStatus.PROPOSED, DecisionStatus.AWAITING_DECISION)
    with pytest.raises(IllegalDecisionTransition):
        validate_decision_transition(DecisionStatus.REJECTED, DecisionStatus.APPROVED)


def test_protected_decision_states():
    assert DecisionStatus.APPROVED in PROTECTED_DECISION_STATES
    assert DecisionStatus.PROPOSED not in PROTECTED_DECISION_STATES


# ── risk/opportunity/alert ──────────────────────────────────────────────────
def test_risk_score(store):
    rid = store.add_risk(owner="ajay", title="x", category="technical",
                        likelihood=0.5, impact=0.8)
    assert store.get_risk(rid)["score"] == 40.0


def test_alert_dedup(store):
    a1 = store.add_alert(owner="ajay", kind="risk", title="disk low", dedup_key="disk")
    a2 = store.add_alert(owner="ajay", kind="risk", title="disk low", dedup_key="disk")
    assert a1 and a2 is None and len(store.list_alerts("ajay")) == 1


# ── Daily Brief (real data + tiers) ─────────────────────────────────────────
def test_daily_brief_real_data_and_tiers(store, tmp_path):
    svc = CEOService(store, orchestrator=_orch(tmp_path), memory=False)
    store.add_risk(owner="ajay", title="cloud unconfigured", category="provider",
                  likelihood=0.8, impact=0.7)
    store.add_kpi(owner="ajay", name="Dream", kpi_type="dream_progress", target=DREAM_TARGET)
    b = svc.daily_brief("ajay")
    tiers = {i["tier"] for i in b["items"]}
    assert EvidenceTier.UNAVAILABLE.value in tiers
    assert any(i["section"] == "System Health" for i in b["items"])
    assert store.list_briefs("ajay")


def test_portfolio_summary(store, tmp_path):
    svc = CEOService(store, orchestrator=_orch(tmp_path), memory=False)
    store.add_business(owner="ajay", name="PIELTS")
    p = svc.portfolio_summary("ajay")
    assert len(p["businesses"]) == 1 and "system_health" in p


# ── Mission via M10 ─────────────────────────────────────────────────────────
def test_mission_executes_through_m10(store, tmp_path):
    orch = _orch(tmp_path)
    svc = CEOService(store, orchestrator=orch, memory=False)
    m = svc.create_mission("ajay", "wire cloud provider", strategy="build")
    out = svc.run_mission(m["mission_run_id"])
    assert out["state"] == "completed"
    assert orch.store.get_run(m["mission_run_id"])["objective"] == "wire cloud provider"


def test_risk_and_opportunity_conversion(store, tmp_path):
    svc = CEOService(store, orchestrator=_orch(tmp_path), memory=False)
    rid = store.add_risk(owner="ajay", title="x", category="technical")
    assert svc.convert_risk_to_mission("ajay", rid)["source"] == "risk"
    oid = store.add_opportunity(owner="ajay", title="new product", value_estimate=5000)
    o = svc.convert_opportunity_to_project("ajay", oid)
    assert o["source"] == "opportunity" and store.get_opportunity(oid)["status"] == "converted"


def test_weekly_review_persisted(store, tmp_path):
    svc = CEOService(store, orchestrator=_orch(tmp_path), memory=False)
    r = svc.weekly_review("ajay")
    assert r["review_id"] and store.list_reviews("ajay", kind="weekly")


# ── CEO agent bounded (security) ────────────────────────────────────────────
def test_ceo_agent_only_proposes(store):
    out = CEOAgent(store).propose_decision("ajay", question="wire cloud?")
    d = store.get_decision(out["decision_id"])
    assert d["status"] == "proposed"
    assert d["provenance"]["evidence_tier"] == EvidenceTier.RECOMMENDED.value


def test_ceo_agent_cannot_do():
    cannot = CEOAgent.__new__(CEOAgent).cannot_do()
    assert "self-approve decisions" in cannot and "spend money" in cannot


def test_ceo_m10_agent_read_only():
    from saathi.agent_runtime import registry
    assert registry.get("ceo").can_self_approve is False


# ── security ─────────────────────────────────────────────────────────────────
def test_cross_user_risk_to_mission_denied(store, tmp_path):
    svc = CEOService(store, orchestrator=_orch(tmp_path), memory=False)
    rid = store.add_risk(owner="ajay", title="x", category="technical")
    with pytest.raises(PermissionError):
        svc.convert_risk_to_mission("mallory", rid)


def test_cross_user_opportunity_denied(store, tmp_path):
    svc = CEOService(store, orchestrator=_orch(tmp_path), memory=False)
    oid = store.add_opportunity(owner="ajay", title="x", value_estimate=1)
    with pytest.raises(PermissionError):
        svc.convert_opportunity_to_project("mallory", oid)


def test_cross_user_lists_isolated(store):
    store.add_risk(owner="ajay", title="ajay risk", category="technical")
    store.add_risk(owner="mallory", title="mallory risk", category="technical")
    assert all("mallory" not in r["title"] for r in store.list_risks("ajay"))


def test_agent_cannot_reach_protected_state(store):
    out = CEOAgent(store).propose_decision("ajay", question="q")
    d = store.get_decision(out["decision_id"])
    assert DecisionStatus(d["status"]) not in PROTECTED_DECISION_STATES


# ── API / CLI ────────────────────────────────────────────────────────────────
def test_api_requires_auth():
    from fastapi.testclient import TestClient
    from saathi.server import app
    assert TestClient(app).get("/api/v1/ceo/portfolio").status_code == 401


def test_api_handlers_direct(store, monkeypatch):
    from saathi.ceo import api

    class Req:
        state = type("S", (), {"user_id": "ajay"})()

    monkeypatch.setattr(api, "default_store", lambda: store)
    api.create_business(api.BusinessIn(name="PIELTS"), Req())
    assert api.list_businesses(Req())["businesses"]
    api.create_kpi(api.KPIIn(name="Users", kpi_type="users", target=100), Req())
    kid = store.list_kpis("ajay")[0]["id"]
    api.observe(kid, api.ObservationIn(value=50, source="db"), Req())
    assert api.list_kpis(Req())["kpis"][0]["pct_to_target"] == 50.0


def test_api_decision_resolve_validates(store, monkeypatch):
    from saathi.ceo import api

    class Req:
        state = type("S", (), {"user_id": "ajay"})()

    monkeypatch.setattr(api, "default_store", lambda: store)
    did = store.add_decision(owner="ajay", question="q")
    assert "error" in api.resolve_decision(did, api.DecisionResolve(status="approved"), Req())
    store.set_decision_status(did, "awaiting_decision")
    assert api.resolve_decision(did, api.DecisionResolve(status="approved"), Req())["status"] == "approved"


def test_api_cross_user_not_found(store, monkeypatch):
    from saathi.ceo import api

    class ReqA:
        state = type("S", (), {"user_id": "ajay"})()

    class ReqB:
        state = type("S", (), {"user_id": "mallory"})()

    monkeypatch.setattr(api, "default_store", lambda: store)
    api.create_kpi(api.KPIIn(name="X", kpi_type="users"), ReqA())
    kid = store.list_kpis("ajay")[0]["id"]
    assert api.observe(kid, api.ObservationIn(value=1, source="s"), ReqB()) == {"error": "not found"}


def test_cli_read_only(store, monkeypatch):
    from saathi.ceo import cli
    monkeypatch.setattr(cli, "default_store", lambda: store)
    assert cli.main(["portfolio"]) == 0 and cli.main(["kpis"]) == 0
    assert cli.main(["risks"]) == 0 and cli.main(["priorities"]) == 0
    assert cli.main(["bogus"]) == 2


# ── regression ───────────────────────────────────────────────────────────────
def test_bff_dream_pct_canonical():
    assert dream_progress_pct(DREAM_TARGET) == 100.0
    assert dream_progress_pct(DREAM_TARGET / 100) == 1.0


def test_route_count_not_decreased():
    from saathi.server import app
    assert len(app.routes) >= 304
