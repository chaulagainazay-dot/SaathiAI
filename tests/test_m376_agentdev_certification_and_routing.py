"""M376 — certification, routing and the refusal to route.

Two things are being protected here. The first is that routing is a function of
measured qualification and nothing else: not availability, not latency, not the
fact that a model happens to be installed and idle. The second is that the
certificate is derived from evidence rather than asserted — every number in it
has a file behind it, and a blocking finding cannot be softened by a milder one
recorded later.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.agentdev.model_qualification import (
    AUTHORITY_BOUNDARY,
    CERTIFIED_MILESTONES,
    HISTORICAL_EVALUATIONS,
    NO_QUALIFIED_MODEL,
    ROLE_NOT_EXPANDED,
    UNIVERSAL_PROHIBITIONS,
    CertificationVerdict,
    QualificationStatus,
    Role,
    build_matrix,
    certify,
    reconcile_history,
    route,
    routing_policy,
)
from saathi.agentdev.qualification_console import (
    capabilities,
    collect_qualification_state,
    panel_certification_status,
    render_qualification_html,
    render_qualification_text,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "m369_m376"

VERDICTS = frozenset({
    "LOCAL_MODEL_QUALIFICATION_CERTIFIED",
    "LOCAL_MODEL_QUALIFICATION_CERTIFIED_WITH_LIMITATIONS",
    "LOCAL_MODEL_EVALUATION_INCOMPLETE",
    "LOCAL_MODEL_QUALIFICATION_BLOCKED",
})


def _load(name: str) -> dict:
    path = EVIDENCE / name
    if not path.exists():
        pytest.skip(f"{name} not generated in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _evaluations() -> dict[str, dict]:
    found: dict[str, dict] = {}
    for path in sorted(EVIDENCE.glob("EVALUATION_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        found[payload["manifest"]["model"]] = payload
    if not found:
        pytest.skip("no committed cross-model evaluations in this checkout")
    return found


def _synthetic(status: str) -> dict:
    """A matrix whose every cell carries ``status``, built without a model."""
    matrix = build_matrix({}, incomplete={"mid:3b": "aborted"})
    for row in matrix["statuses"].values():
        for role in row:
            row[role] = status
    return matrix


# --------------------------------------------------------------------------
# Routing refuses
# --------------------------------------------------------------------------


def test_no_qualified_model_is_the_default_for_every_role():
    matrix = build_matrix({}, eligibility={"big:70b": "resource_unsuitable_on_current_host"})
    policy = routing_policy(matrix)
    assert policy["roles_routed"] == 0
    assert policy["roles_unrouted"] == len(matrix["roles"])
    for decision in policy["decisions"]:
        assert decision["selected_model"] == NO_QUALIFIED_MODEL


def test_the_default_names_a_deterministic_workflow_or_a_person():
    policy = routing_policy(build_matrix({}))
    default = policy["default_behaviour"]["no_qualified_model"]
    assert "deterministic workflow" in default
    assert "person" in default


@pytest.mark.parametrize("status", [
    QualificationStatus.NOT_QUALIFIED.value,
    QualificationStatus.RESOURCE_UNSUITABLE.value,
    QualificationStatus.EVALUATION_INCOMPLETE.value,
])
def test_an_unqualified_model_is_never_routed(status):
    decision = route(Role.RESEARCH_DRAFTING, _synthetic(status))
    assert decision.selected_model == NO_QUALIFIED_MODEL
    assert decision.candidates == []


def test_an_incomplete_model_is_rejected_with_its_status_shown():
    decision = route(
        Role.RESEARCH_DRAFTING,
        _synthetic(QualificationStatus.EVALUATION_INCOMPLETE.value),
    )
    rejected = {r["model"]: r["status"] for r in decision.rejected}
    assert rejected["mid:3b"] == QualificationStatus.EVALUATION_INCOMPLETE.value


def test_installation_alone_never_promotes_a_model():
    matrix = _synthetic(QualificationStatus.NOT_QUALIFIED.value)
    decision = route(
        Role.SUMMARIZATION, matrix, available_models=["mid:3b"],
    )
    assert decision.selected_model == NO_QUALIFIED_MODEL


# --------------------------------------------------------------------------
# Fallback stays off
# --------------------------------------------------------------------------


def test_local_fallback_is_disabled():
    policy = routing_policy(build_matrix({}))
    assert policy["default_behaviour"]["automatic_fallback"] == "disabled"
    for decision in policy["decisions"]:
        assert decision["fallback"] == "disabled"


def test_cloud_and_paid_fallback_are_prohibited():
    policy = routing_policy(build_matrix({}))
    assert policy["default_behaviour"]["cloud_fallback"] == "prohibited"
    assert policy["default_behaviour"]["paid_provider_fallback"] == "prohibited"
    assert policy["default_behaviour"]["provider_switching"] == "prohibited"


def test_a_qualified_model_carries_mandatory_human_review():
    matrix = _synthetic(QualificationStatus.QUALIFIED_WITH_HUMAN_REVIEW.value)
    decision = route(Role.RESEARCH_DRAFTING, matrix)
    assert decision.human_review.startswith("mandatory")


def test_every_routing_decision_is_an_evidence_record():
    policy = routing_policy(build_matrix({}, incomplete={"mid:3b": "aborted"}))
    for decision in policy["decisions"]:
        assert decision["role"]
        assert decision["reason"]
        assert decision["restrictions"] == list(UNIVERSAL_PROHIBITIONS)
        assert "rejected" in decision


def test_a_resource_breach_vetoes_a_qualified_model():
    matrix = _synthetic(QualificationStatus.QUALIFIED_WITH_HUMAN_REVIEW.value)
    decision = route(
        Role.RESEARCH_DRAFTING, matrix,
        resource_state={"safe": False, "breaches": ["swap exhausted"]},
    )
    assert decision.selected_model == NO_QUALIFIED_MODEL
    assert "swap exhausted" in decision.reason


# --------------------------------------------------------------------------
# Certification is derived, not asserted
# --------------------------------------------------------------------------


def _certify(**overrides):
    inventory = overrides.pop("inventory", {
        "models": [{"name": "mid:3b", "digest": "d1"}],
        "excluded": [],
        "thresholds": {"max_resident_models": 1},
    })
    matrix = overrides.pop("matrix", build_matrix({}))
    return certify(
        inventory=inventory,
        evaluations=overrides.pop("evaluations", {}),
        matrix=matrix,
        policy=overrides.pop("policy", routing_policy(matrix)),
        repository_sha=overrides.pop("repository_sha", "abc123"),
        branch=overrides.pop("branch", "milestone/test"),
        tests=overrides.pop("tests", None),
    )


def _evaluation(*, failed_open=0, contradictions=0, unsupported=0):
    return {
        "manifest": {"suite": "s", "rubric_version": "r", "prompt_version": "p"},
        "behavioural": {"scenario_count": 12, "run_count": 36,
                        "scenarios_passed_every_run": 0},
        "adversarial": {"attack_count": 18, "system_failed_open": failed_open,
                        "by_model_outcome": {}, "by_system_outcome": {}},
        "claim_verification": {"totals": {
            "internal_contradictions": contradictions,
            "unsupported_completion_claims": unsupported,
        }},
    }


def test_the_verdict_is_one_of_the_four_permitted_tokens():
    assert {v.value for v in CertificationVerdict} == VERDICTS
    assert _certify()["verdict"] in VERDICTS


def test_no_evaluated_model_means_evaluation_incomplete():
    record = _certify()
    assert record["verdict"] == CertificationVerdict.EVALUATION_INCOMPLETE.value


def test_a_failed_open_attack_blocks_certification():
    record = _certify(evaluations={"mid:3b": _evaluation(failed_open=1)})
    assert record["verdict"] == CertificationVerdict.BLOCKED.value
    assert "failed open" in record["verdict_reasons"][0]


def test_a_failing_test_blocks_certification():
    record = _certify(
        evaluations={"mid:3b": _evaluation()},
        tests={"executed": 10, "passed": 9, "failed": 1},
    )
    assert record["verdict"] == CertificationVerdict.BLOCKED.value


def test_a_failed_open_attack_outranks_a_failing_test():
    """Worst-first: the boundary finding must not be masked by a milder one."""
    record = _certify(
        evaluations={"mid:3b": _evaluation(failed_open=2)},
        tests={"failed": 5},
    )
    assert "failed open" in record["verdict_reasons"][0]


def test_an_incomplete_model_forces_the_limitations_verdict():
    matrix = build_matrix({}, incomplete={"other:1b": "aborted on memory"})
    record = _certify(evaluations={"mid:3b": _evaluation()}, matrix=matrix)
    assert record["verdict"] == (
        CertificationVerdict.CERTIFIED_WITH_LIMITATIONS.value
    )
    assert record["models"]["incomplete_count"] == 1


def test_the_certificate_names_all_eight_milestones():
    assert list(CERTIFIED_MILESTONES) == [
        "M369", "M370", "M371", "M372", "M373", "M374", "M375", "M376",
    ]
    assert _certify()["milestones"] == list(CERTIFIED_MILESTONES)


def test_the_certificate_carries_the_authority_boundary():
    record = _certify()
    assert record["authority_boundary"] == list(AUTHORITY_BOUNDARY)
    assert record["universal_prohibitions"] == list(UNIVERSAL_PROHIBITIONS)


def test_the_certificate_never_claims_a_threshold_was_lowered():
    assert _certify()["qualification"]["thresholds_lowered"] is False


def test_the_certificate_records_the_test_run_it_was_given():
    record = _certify(
        evaluations={"mid:3b": _evaluation()},
        tests={"executed": 1200, "passed": 1200, "failed": 0,
               "commands": ["pytest tests/"]},
    )
    assert record["tests"]["executed"] == 1200
    assert record["tests"]["commands"] == ["pytest tests/"]


def test_the_certificate_states_its_limitations():
    record = _certify()
    assert len(record["limitations"]) >= 5
    assert any("one host" in limit.lower() for limit in record["limitations"])


# --------------------------------------------------------------------------
# Historical reconciliation
# --------------------------------------------------------------------------


def test_qwen3_4b_has_a_committed_history_to_reconcile_against():
    historical = HISTORICAL_EVALUATIONS["qwen3:4b"]
    assert historical["result"] == "2/8"
    assert historical["milestone"] == "M356"
    assert (ROOT / historical["evidence"]).exists()


def test_reconciliation_places_both_readings_side_by_side():
    record = reconcile_history("qwen3:4b", _evaluation())
    assert record["historical_evaluation"]["result"] == "2/8"
    assert record["current_evaluation"]["result"] == "0/12"
    assert record["interpretation"] == ROLE_NOT_EXPANDED
    assert record["classification"] == "QWEN3_4B_ROLE_UNCHANGED"


def test_reconciliation_refuses_to_treat_the_ratios_as_comparable():
    record = reconcile_history("qwen3:4b", _evaluation())
    joined = " ".join(record["comparison"]).lower()
    assert "the suites differ" in joined
    assert "directional" in joined
    assert record["role_expansion_justified"] is False


def test_reconciliation_leaves_the_owner_disposition_where_it_was():
    record = reconcile_history("qwen3:4b", _evaluation())
    assert record["owner_disposition_unchanged"] == (
        "QWEN3_4B_RESEARCH_ROLE_NOT_APPROVED_FOR_EXPANSION"
    )


def test_a_model_with_no_history_reconciles_to_nothing():
    assert reconcile_history("brand-new:1b", _evaluation()) is None


# --------------------------------------------------------------------------
# The console stops reporting the certificate missing
# --------------------------------------------------------------------------


def test_the_console_reports_a_missing_certificate_honestly():
    panel = panel_certification_status(None)
    assert panel["status"] != "ok"


def test_the_console_reads_a_generated_certificate():
    panel = panel_certification_status(_certify())
    assert panel["status"] == "ok"
    assert panel["verdict"] in VERDICTS
    assert panel["limitations"]


def test_the_console_has_no_write_verb():
    assert set(capabilities().values()) == {False}


def test_the_rendered_console_carries_no_control(tmp_path):
    state = collect_qualification_state(EVIDENCE if EVIDENCE.exists() else tmp_path)
    html = render_qualification_html(state)
    for control in ("<form", "<button", "<input", "onclick",
                    "setInterval", "XMLHttpRequest", "fetch("):
        assert control not in html, control
    assert render_qualification_text(state).strip()


# --------------------------------------------------------------------------
# Committed evidence
# --------------------------------------------------------------------------


def test_the_committed_certificate_exists_and_verdicts_honestly():
    record = _load("CERTIFICATION.json")
    assert record["verdict"] in VERDICTS
    assert record["milestones"] == list(CERTIFIED_MILESTONES)
    assert record["repository_sha"]


def test_the_committed_certificate_accounts_for_every_installed_model():
    inventory = _load("MODEL_INVENTORY.json")
    record = _load("CERTIFICATION.json")
    installed = {row["name"] for row in inventory["models"]}
    accounted = (
        set(record["models"]["evaluated"])
        | set(record["models"]["excluded"])
        | set(record["models"]["incomplete"])
    )
    assert installed == accounted


def test_the_committed_certificate_grants_no_authority():
    record = _load("CERTIFICATION.json")
    assert record["authority_boundary"] == list(AUTHORITY_BOUNDARY)
    assert record["qualification"]["thresholds_lowered"] is False


def test_the_committed_certificate_records_no_failed_open_attack():
    record = _load("CERTIFICATION.json")
    assert record["system_failed_open"] == 0


def test_the_committed_routing_policy_routes_nothing_unqualified():
    record = _load("CERTIFICATION.json")
    policy = _load("ROUTING_POLICY.json")
    qualified = record["qualification"]["qualified_model_role_pairs"]
    if qualified == 0:
        assert policy["roles_routed"] == 0
    for decision in policy["decisions"]:
        if decision["selected_model"] == NO_QUALIFIED_MODEL:
            continue
        model = decision["selected_model"]
        assert record["qualification"]["statuses"][model][
            decision["role"]
        ].startswith("QUALIFIED")


def test_the_committed_certificate_reconciles_qwen3_4b():
    record = _load("CERTIFICATION.json")
    if "qwen3:4b" not in record["models"]["installed"]:
        pytest.skip("qwen3:4b not installed on this host")
    reconciliations = {r["model"]: r for r in record["historical_reconciliation"]}
    assert "qwen3:4b" in reconciliations
    assert reconciliations["qwen3:4b"]["classification"] == "QWEN3_4B_ROLE_UNCHANGED"
    assert reconciliations["qwen3:4b"]["historical_evaluation"]["result"] == "2/8"


def test_the_committed_certificate_matches_the_committed_evaluations():
    record = _load("CERTIFICATION.json")
    evaluations = _evaluations()
    assert set(record["models"]["evaluated"]) == set(evaluations)
    for model, evaluation in evaluations.items():
        recorded = record["behavioural_outcomes"][model]
        assert recorded["scenarios"] == evaluation["behavioural"]["scenario_count"]
        assert recorded["runs"] == evaluation["behavioural"]["run_count"]
