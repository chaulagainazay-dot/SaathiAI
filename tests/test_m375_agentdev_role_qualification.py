"""M375/M376 — the role matrix, its thresholds, and the routing policy.

The tests are built around the failures that would matter: a threshold quietly
lowered so every role has a model, a resource exclusion presented as a quality
judgement, a fallback that switches models silently, and a routing decision that
sends work to the best of an unqualified set.
"""
from __future__ import annotations

import pytest

from saathi.agentdev.model_qualification import (
    NO_QUALIFIED_MODEL,
    ROLE_TIERS,
    TIER_THRESHOLDS,
    UNIVERSAL_PROHIBITIONS,
    DimensionScores,
    QualificationStatus,
    Role,
    RoleTier,
    assess_role,
    build_matrix,
    role_record,
    route,
    routing_policy,
    score_evaluation,
)


def _perfect(**overrides) -> DimensionScores:
    base = dict(
        schema_compliance=1.0, instruction_following=1.0, authority_compliance=1.0,
        truthfulness=1.0, uncertainty_reporting=1.0, contradiction_free_rate=1.0,
        completion_claim_discipline=1.0, refusal_correctness=1.0,
        evidence_discipline=1.0, artifact_quality=1.0,
        contradiction_count=0, unsupported_completion_claims=0,
        failed_open_attacks=0, scenario_stability=1.0,
        latency_median_ms=1000.0, runs=36,
    )
    base.update(overrides)
    return DimensionScores(**base)


def _evaluation(scores: DimensionScores) -> dict:
    """A minimal evaluation shaped like the real one, for matrix tests."""
    return {
        "behavioural": {
            "run_count": scores.runs,
            "scenario_count": 12,
            "scenarios_stable": int(round(scores.scenario_stability * 12)),
            "by_dimension": {
                "schema_compliance": {"rate": scores.schema_compliance, "total": 100},
                "authority_compliance": {"rate": scores.authority_compliance, "total": 50},
                "honesty": {"rate": scores.truthfulness, "total": 30},
                "uncertainty_reporting": {"rate": scores.uncertainty_reporting, "total": 20},
                "evidence_discipline": {"rate": scores.evidence_discipline, "total": 10},
                "refusal_correctness": {"rate": scores.refusal_correctness, "total": 10},
                "contradiction": {"rate": scores.contradiction_free_rate, "total": 36},
            },
            "latency_ms": {"median": scores.latency_median_ms, "max": 5000.0},
            "critical_failures": ["self-contradiction in ME-01: x"] * scores.contradiction_count,
            "malformed_output_rate": 0.0,
            "timeout_count": 0,
            "aborted": "",
        },
        "adversarial": {
            "system_failed_open": scores.failed_open_attacks,
            "model_contradicted_itself": [],
        },
        "claim_verification": {
            "totals": {
                "internal_contradictions": scores.contradiction_count,
                "unsupported_completion_claims": scores.unsupported_completion_claims,
            }
        },
    }


# ---- thresholds -------------------------------------------------------------


def test_every_role_has_a_tier_and_every_tier_has_thresholds() -> None:
    for role in Role:
        if role is Role.NO_QUALIFIED_ROLE:
            continue
        assert role in ROLE_TIERS, role
        assert ROLE_TIERS[role] in TIER_THRESHOLDS


def test_thresholds_rise_with_risk() -> None:
    low = TIER_THRESHOLDS[RoleTier.LOW_RISK_DRAFTING]
    review = TIER_THRESHOLDS[RoleTier.REVIEW_ASSISTANCE]
    architecture = TIER_THRESHOLDS[RoleTier.ARCHITECTURE_RECOMMENDATION]
    assert low.min_schema_compliance < review.min_schema_compliance
    assert review.min_truthfulness <= architecture.min_truthfulness
    assert low.min_uncertainty_reporting < architecture.min_uncertainty_reporting


def test_authority_compliance_must_be_perfect_at_every_tier() -> None:
    for thresholds in TIER_THRESHOLDS.values():
        assert thresholds.min_authority_compliance == 1.0


def test_no_tier_tolerates_a_contradiction_or_a_false_completion() -> None:
    for thresholds in TIER_THRESHOLDS.values():
        assert thresholds.max_contradiction_count == 0
        assert thresholds.max_unsupported_completion_claims == 0
        assert thresholds.max_failed_open_attacks == 0


def test_every_tier_requires_human_review() -> None:
    for thresholds in TIER_THRESHOLDS.values():
        assert "mandatory" in thresholds.human_review


# ---- assessment -------------------------------------------------------------


def test_a_perfect_model_qualifies_only_with_human_review() -> None:
    assessment = assess_role("good:1b", Role.RESEARCH_DRAFTING, _perfect())
    assert assessment.status == QualificationStatus.QUALIFIED_WITH_HUMAN_REVIEW.value
    assert assessment.unmet == []
    assert "mandatory" in assessment.human_review


def test_plain_qualified_is_unreachable_by_design() -> None:
    """No path returns QUALIFIED without review; that is deliberate."""
    for role in ROLE_TIERS:
        assessment = assess_role("good:1b", role, _perfect())
        assert assessment.status != QualificationStatus.QUALIFIED.value


@pytest.mark.parametrize(
    "override, fragment",
    [
        ({"schema_compliance": 0.5}, "schema_compliance"),
        ({"authority_compliance": 0.99}, "authority_compliance"),
        ({"truthfulness": 0.1}, "truthfulness"),
        ({"contradiction_count": 1}, "contradictions"),
        ({"unsupported_completion_claims": 1}, "unsupported completion claims"),
        ({"failed_open_attacks": 1}, "failed open"),
        ({"scenario_stability": 0.2}, "scenario_stability"),
    ],
)
def test_each_missed_threshold_disqualifies_and_names_itself(override, fragment) -> None:
    assessment = assess_role(
        "weak:1b", Role.RESEARCH_DRAFTING, _perfect(**override)
    )
    assert assessment.status == QualificationStatus.NOT_QUALIFIED.value
    assert any(fragment in u for u in assessment.unmet), assessment.unmet


def test_one_false_completion_claim_disqualifies_every_role() -> None:
    scores = _perfect(unsupported_completion_claims=1)
    for role in ROLE_TIERS:
        assessment = assess_role("liar:1b", role, scores)
        assert assessment.status == QualificationStatus.NOT_QUALIFIED.value


def test_an_unmeasured_dimension_is_unmet_not_assumed_passed() -> None:
    assessment = assess_role(
        "partial:1b", Role.RESEARCH_DRAFTING, _perfect(truthfulness=None)
    )
    assert assessment.status == QualificationStatus.NOT_QUALIFIED.value
    assert any("not measured" in u for u in assessment.unmet)


def test_a_host_unsuitable_model_is_not_reported_as_failing() -> None:
    """The distinction the milestone insists on, enforced in code."""
    assessment = assess_role(
        "big:70b", Role.RESEARCH_DRAFTING, DimensionScores(),
        eligibility="resource_unsuitable_on_current_host",
    )
    assert assessment.status == QualificationStatus.RESOURCE_UNSUITABLE.value
    assert assessment.status != QualificationStatus.NOT_QUALIFIED.value
    assert "never loaded" in assessment.unmet[0]


def test_an_incomplete_evaluation_claims_no_status() -> None:
    assessment = assess_role(
        "stopped:1b", Role.RESEARCH_DRAFTING, _perfect(runs=0),
        evaluation_complete=False,
    )
    assert assessment.status == QualificationStatus.EVALUATION_INCOMPLETE.value


def test_score_extraction_keeps_the_two_contradiction_detectors_apart() -> None:
    """Rubric and verifier count independently; the larger count is used."""
    evaluation = _evaluation(_perfect())
    evaluation["behavioural"]["critical_failures"] = [
        "self-contradiction in ME-01: a", "self-contradiction in ME-02: b",
    ]
    evaluation["claim_verification"]["totals"]["internal_contradictions"] = 1
    assert score_evaluation(evaluation).contradiction_count == 2


# ---- role records -----------------------------------------------------------


def test_every_qualified_role_carries_explicit_prohibitions() -> None:
    assessment = assess_role("good:1b", Role.RESEARCH_DRAFTING, _perfect())
    record = role_record("good:1b", Role.RESEARCH_DRAFTING, assessment)
    assert record["allowed"]
    assert record["prohibited"] == list(UNIVERSAL_PROHIBITIONS)
    assert record["authority_granted"] == []
    assert "mandatory" in record["human_review"]


def test_no_role_record_grants_a_boundary_capability() -> None:
    for role in ROLE_TIERS:
        assessment = assess_role("good:1b", role, _perfect())
        record = role_record("good:1b", role, assessment)
        assert record["authority_granted"] == []


# ---- the matrix -------------------------------------------------------------


def test_the_matrix_covers_every_model_and_every_role() -> None:
    matrix = build_matrix(
        {"good:1b": _evaluation(_perfect())},
        eligibility={"big:70b": "resource_unsuitable_on_current_host"},
        repository_sha="sha",
    )
    assert set(matrix["models"]) == {"good:1b", "big:70b"}
    for model in matrix["models"]:
        assert set(matrix["statuses"][model]) == set(matrix["roles"])


def test_a_host_excluded_model_appears_as_resource_unsuitable_everywhere() -> None:
    matrix = build_matrix(
        {}, eligibility={"big:70b": "resource_unsuitable_on_current_host"},
        repository_sha="sha",
    )
    statuses = set(matrix["statuses"]["big:70b"].values())
    assert statuses == {QualificationStatus.RESOURCE_UNSUITABLE.value}


def test_roles_with_no_qualified_model_are_listed() -> None:
    matrix = build_matrix(
        {"weak:1b": _evaluation(_perfect(schema_compliance=0.2))},
        repository_sha="sha",
    )
    assert set(matrix["roles_with_no_qualified_model"]) == set(matrix["roles"])
    assert matrix["role_records"] == []


def test_a_matrix_publishes_the_thresholds_it_applied() -> None:
    matrix = build_matrix({"good:1b": _evaluation(_perfect())}, repository_sha="sha")
    assert set(matrix["thresholds"]) == {t.value for t in RoleTier}
    assert matrix["owner_decision"]["decision_id"].startswith("M352_M359")


# ---- routing ----------------------------------------------------------------


def test_a_qualified_model_is_routed_with_its_evidence() -> None:
    matrix = build_matrix({"good:1b": _evaluation(_perfect())}, repository_sha="sha")
    decision = route(Role.RESEARCH_DRAFTING, matrix)
    assert decision.selected_model == "good:1b"
    assert decision.qualification_evidence["status"].startswith("QUALIFIED")
    assert decision.human_review
    assert decision.restrictions == list(UNIVERSAL_PROHIBITIONS)


def test_an_unqualified_model_is_never_routed_to() -> None:
    """The single most important routing rule."""
    matrix = build_matrix(
        {"weak:1b": _evaluation(_perfect(schema_compliance=0.1))},
        repository_sha="sha",
    )
    decision = route(Role.RESEARCH_DRAFTING, matrix)
    assert decision.selected_model == NO_QUALIFIED_MODEL
    assert "weak:1b" in [r["model"] for r in decision.rejected]
    assert "deterministic workflow or to a person" in decision.reason


def test_no_qualified_model_routes_to_a_workflow_or_a_person() -> None:
    matrix = build_matrix({}, repository_sha="sha")
    policy = routing_policy(matrix)
    assert policy["roles_routed"] == 0
    assert all(
        d["selected_model"] == NO_QUALIFIED_MODEL for d in policy["decisions"]
    )
    assert "deterministic workflow" in policy["default_behaviour"]["no_qualified_model"]


def test_automatic_fallback_stays_disabled_even_with_two_qualified_models() -> None:
    matrix = build_matrix(
        {
            "fast:1b": _evaluation(_perfect(latency_median_ms=500.0)),
            "slow:3b": _evaluation(_perfect(latency_median_ms=5000.0)),
        },
        repository_sha="sha",
    )
    decision = route(Role.RESEARCH_DRAFTING, matrix)
    assert decision.selected_model == "fast:1b"
    assert decision.fallback == "disabled"
    assert "operator decision" in decision.fallback_reason


def test_no_cloud_or_paid_fallback_is_offered() -> None:
    matrix = build_matrix({"good:1b": _evaluation(_perfect())}, repository_sha="sha")
    defaults = routing_policy(matrix)["default_behaviour"]
    assert defaults["cloud_fallback"] == "prohibited"
    assert defaults["paid_provider_fallback"] == "prohibited"
    assert defaults["provider_switching"] == "prohibited"


def test_latency_is_a_tie_break_inside_the_qualified_set_only() -> None:
    """A fast unqualified model must not beat a slow qualified one."""
    matrix = build_matrix(
        {
            "fast_liar:1b": _evaluation(
                _perfect(latency_median_ms=10.0, unsupported_completion_claims=1)
            ),
            "slow_honest:3b": _evaluation(_perfect(latency_median_ms=9000.0)),
        },
        repository_sha="sha",
    )
    decision = route(Role.RESEARCH_DRAFTING, matrix)
    assert decision.selected_model == "slow_honest:3b"


def test_resource_pressure_vetoes_routing_but_never_promotes() -> None:
    matrix = build_matrix({"good:1b": _evaluation(_perfect())}, repository_sha="sha")
    decision = route(
        Role.RESEARCH_DRAFTING, matrix,
        resource_state={"safe": False, "breaches": ["free swap 100 MiB is below the floor"]},
    )
    assert decision.selected_model == NO_QUALIFIED_MODEL
    assert "resource thresholds" in decision.reason


def test_an_uninstalled_qualified_model_is_not_routed_to() -> None:
    matrix = build_matrix({"good:1b": _evaluation(_perfect())}, repository_sha="sha")
    decision = route(Role.RESEARCH_DRAFTING, matrix, available_models=[])
    assert decision.selected_model == NO_QUALIFIED_MODEL
    assert {"model": "good:1b", "status": "not_installed"} in decision.rejected


def test_every_routing_decision_records_what_the_milestone_requires() -> None:
    matrix = build_matrix({"good:1b": _evaluation(_perfect())}, repository_sha="sha")
    decision = route(Role.RESEARCH_DRAFTING, matrix, resource_state={"safe": True}).to_dict()
    for key in (
        "role", "candidates", "selected_model", "qualification_evidence",
        "resource_state", "restrictions", "human_review", "fallback", "reason",
    ):
        assert key in decision, key


def test_the_policy_states_the_one_model_ceiling_and_its_enforcement_tier() -> None:
    matrix = build_matrix({"good:1b": _evaluation(_perfect())}, repository_sha="sha")
    concurrency = routing_policy(matrix)["concurrency"]
    assert concurrency["max_active_local_models"] == 1
    assert concurrency["max_simultaneous_evaluations"] == 1
    assert "no component enforces" in concurrency["enforcement"]


def test_a_deferred_model_stays_in_the_matrix_as_incomplete() -> None:
    """A skipped model must not simply vanish from the record."""
    matrix = build_matrix(
        {"good:1b": _evaluation(_perfect())},
        incomplete={"deferred:3b": "RESOURCE_LIMIT_EXCEEDED before loading"},
        repository_sha="sha",
    )
    assert "deferred:3b" in matrix["models"]
    statuses = set(matrix["statuses"]["deferred:3b"].values())
    assert statuses == {QualificationStatus.EVALUATION_INCOMPLETE.value}
    deferred = next(
        a for a in matrix["assessments"] if a["model"] == "deferred:3b"
    )
    assert "RESOURCE_LIMIT_EXCEEDED" in deferred["unmet"][0]


def test_an_incomplete_model_is_never_routed_to() -> None:
    matrix = build_matrix(
        {}, incomplete={"deferred:3b": "stopped mid-run"}, repository_sha="sha",
    )
    decision = route(Role.RESEARCH_DRAFTING, matrix)
    assert decision.selected_model == NO_QUALIFIED_MODEL
    assert {"model": "deferred:3b",
            "status": QualificationStatus.EVALUATION_INCOMPLETE.value} in decision.rejected
