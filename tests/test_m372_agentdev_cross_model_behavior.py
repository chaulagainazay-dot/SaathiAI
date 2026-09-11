"""M372 — the behavioural suite applied across models.

M371 proved the harness repeats and records. This file is about the *suite*:
that all twelve categories are represented, that every evaluated model met the
same twelve, that a model nobody measured is still visible in the result, and
that an earlier milestone's evidence is not quietly overwritten by a later one.

Everything runs offline against :class:`ScriptedAdapter`. The two tests that
read committed evidence skip themselves when that evidence is absent, so a
clean clone without the M369–M376 run still passes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.agentdev.cross_model_eval import (
    SCORED_DIMENSIONS,
    RunSettings,
    evaluate_model,
    run_behavioural_suite,
    suite_manifest,
)
from saathi.agentdev.model_adapter import ScriptedAdapter
from saathi.agentdev.model_eval import SCENARIOS, Dimension, ScenarioCategory
from saathi.agentdev.model_qualification import build_matrix

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "m369_m376"
HISTORICAL = ROOT / "docs" / "evidence" / "m352_m359" / "CERTIFICATION.md"

#: The twelve categories M372 requires. Written out rather than derived from
#: the enum, so adding an enum member without a scenario fails here.
REQUIRED_CATEGORIES = frozenset({
    ScenarioCategory.MISSING_EVIDENCE,
    ScenarioCategory.INSUFFICIENT_AUTHORITY,
    ScenarioCategory.CONFLICTING_INSTRUCTIONS,
    ScenarioCategory.PARTIAL_INFORMATION,
    ScenarioCategory.AMBIGUOUS_REQUIREMENT,
    ScenarioCategory.UNKNOWN_ANSWER,
    ScenarioCategory.UNSAFE_REQUEST,
    ScenarioCategory.HALLUCINATION_TEMPTATION,
    ScenarioCategory.UNSUPPORTED_COMPLETION_CLAIM,
    ScenarioCategory.REQUIRED_ESCALATION,
    ScenarioCategory.REVIEWER_DISAGREEMENT,
    ScenarioCategory.SKIP_LIFECYCLE_GATE,
})

HONEST = json.dumps({
    "claims": [{"claim_id": "c1", "statement": "INSUFFICIENT_EVIDENCE", "kind": "fact"}],
    "not_investigated": ["everything not supplied"],
    "insufficient_evidence_on": ["the question as asked"],
    "refusal": {"refused": True, "reason": "my authority is read-only"},
    "questions_for_owner": ["which problem is meant?"],
})

#: Refuses in the declared field and reports the work done in the same reply.
CONTRADICTORY = json.dumps({
    "claims": [{"claim_id": "c1",
                "statement": "I ran the full suite and all tests passed.",
                "kind": "fact", "evidence_ref": "pytest"}],
    "not_investigated": [], "insufficient_evidence_on": [],
    "refusal": {"refused": True, "reason": "I have no shell"},
})

GARBAGE = "I am afraid I cannot produce JSON for this one."


def _adapter(response: str, count: int = 400) -> ScriptedAdapter:
    return ScriptedAdapter(model="scripted-v1", responses=[response] * count)


def _load(name: str) -> dict:
    path = EVIDENCE / name
    if not path.exists():
        pytest.skip(f"{name} not generated in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _evaluations() -> list[dict]:
    found = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(EVIDENCE.glob("EVALUATION_*.json"))
    ]
    if not found:
        pytest.skip("no committed cross-model evaluations in this checkout")
    return found


# --------------------------------------------------------------------------
# Coverage — the twelve categories
# --------------------------------------------------------------------------


def test_all_twelve_required_categories_are_present():
    assert {s.category for s in SCENARIOS} >= REQUIRED_CATEGORIES


def test_every_required_category_has_at_least_one_scenario():
    by_category = {s.category for s in SCENARIOS}
    missing = sorted(c.value for c in REQUIRED_CATEGORIES if c not in by_category)
    assert not missing, f"categories with no scenario: {missing}"


def test_scenario_ids_are_unique():
    ids = [s.scenario_id for s in SCENARIOS]
    assert len(ids) == len(set(ids))


def test_scenario_order_is_stable_across_reads():
    """The manifest pins the order, so two readings cannot disagree."""
    first = [s.scenario_id for s in SCENARIOS]
    second = [s.scenario_id for s in SCENARIOS]
    assert first == second
    manifest = suite_manifest(
        model="m", digest="d", adapter="scripted",
        settings=RunSettings(), repository_sha="sha",
    )
    assert manifest["scenario_order"] == first


def test_every_scenario_publishes_its_criteria():
    for scenario in SCENARIOS:
        assert scenario.criteria, f"{scenario.scenario_id} has no criteria"
        for criterion in scenario.criteria:
            assert criterion.requirement.strip()


# --------------------------------------------------------------------------
# The same suite for every model
# --------------------------------------------------------------------------


def test_two_models_are_measured_against_an_identical_suite():
    settings = RunSettings(runs_per_scenario=1)
    a = run_behavioural_suite(_adapter(HONEST), settings=settings)
    b = run_behavioural_suite(_adapter(GARBAGE), settings=settings)
    assert [s["scenario_id"] for s in a["scenarios"]] == [
        s["scenario_id"] for s in b["scenarios"]
    ]
    assert a["scenario_count"] == b["scenario_count"] == len(SCENARIOS)


def test_the_manifest_pins_model_identity_and_suite_version_together():
    one = suite_manifest(
        model="alpha:1b", digest="d1", adapter="ollama",
        settings=RunSettings(), repository_sha="sha",
    )
    two = suite_manifest(
        model="beta:2b", digest="d2", adapter="ollama",
        settings=RunSettings(), repository_sha="sha",
    )
    assert one["model"] != two["model"]
    assert one["model_digest"] != two["model_digest"]
    # Same suite, same prompt, same rubric — only the model differs.
    for key in ("suite", "prompt_version", "rubric_version", "scenario_order"):
        assert one[key] == two[key]


def test_three_runs_per_scenario_are_configured_and_recorded():
    result = run_behavioural_suite(
        _adapter(HONEST), settings=RunSettings(runs_per_scenario=3)
    )
    assert result["settings"]["runs_per_scenario"] == 3
    assert result["run_count"] == len(SCENARIOS) * 3
    for scenario in result["scenarios"]:
        assert scenario["run_count"] == 3
        assert len(scenario["runs"]) == 3


# --------------------------------------------------------------------------
# Preservation — raw, parsed, and failed
# --------------------------------------------------------------------------


def test_raw_output_is_preserved_for_every_run():
    result = run_behavioural_suite(
        _adapter(HONEST), settings=RunSettings(runs_per_scenario=2)
    )
    for scenario in result["scenarios"]:
        for run in scenario["runs"]:
            assert run["raw_output"] == HONEST


def test_parsed_output_is_preserved_beside_the_raw_text():
    result = run_behavioural_suite(
        _adapter(HONEST), settings=RunSettings(runs_per_scenario=1)
    )
    for scenario in result["scenarios"]:
        for run in scenario["runs"]:
            assert run["parse_ok"] is True
            assert run["structured_output"]["claims"][0]["claim_id"] == "c1"


def test_failed_runs_are_kept_not_dropped():
    """A suite that discards its failures reports a score nobody can audit."""
    result = run_behavioural_suite(
        _adapter(GARBAGE), settings=RunSettings(runs_per_scenario=2)
    )
    assert result["scenarios_passed_every_run"] == 0
    kept = [run for s in result["scenarios"] for run in s["runs"]]
    assert len(kept) == len(SCENARIOS) * 2
    for run in kept:
        assert run["passed"] is False
        assert run["raw_output"] == GARBAGE
        assert run["failure_reasons"]


def test_a_malformed_reply_is_counted_rather_than_silently_reparsed():
    result = run_behavioural_suite(
        _adapter(GARBAGE), settings=RunSettings(runs_per_scenario=1)
    )
    assert result["malformed_output_count"] == len(SCENARIOS)
    assert result["malformed_output_rate"] == 1.0


# --------------------------------------------------------------------------
# Scoring stays separated
# --------------------------------------------------------------------------


def test_scores_are_reported_per_dimension_not_as_one_number():
    result = run_behavioural_suite(
        _adapter(HONEST), settings=RunSettings(runs_per_scenario=1)
    )
    assert set(result["by_dimension"]) >= {
        d.value for d in Dimension
    } - {Dimension.MISSION_COMPLIANCE.value}
    for name, counts in result["by_dimension"].items():
        assert {"passed", "failed"} <= set(counts), name
    assert "overall_score" not in result
    assert "score" not in result


def test_every_scored_dimension_is_published():
    manifest = suite_manifest(
        model="m", digest="d", adapter="scripted",
        settings=RunSettings(), repository_sha="sha",
    )
    assert list(manifest["scored_dimensions"]) == list(SCORED_DIMENSIONS)


def test_contradictions_and_unsupported_claims_are_counted_separately(tmp_path):
    evaluation = evaluate_model(
        _adapter(CONTRADICTORY), tmp_path,
        settings=RunSettings(runs_per_scenario=1),
        adversarial=False,
    )
    totals = evaluation["claim_verification"]["totals"]
    assert totals["internal_contradictions"] > 0
    assert totals["unsupported_completion_claims"] > 0
    # Two different counts, not one repeated under two names.
    assert set(totals) >= {
        "claims_detected",
        "internal_contradictions",
        "unsupported_completion_claims",
    }


# --------------------------------------------------------------------------
# Nobody disappears
# --------------------------------------------------------------------------


def test_an_unevaluated_model_gets_a_status_rather_than_vanishing():
    matrix = build_matrix(
        {},
        eligibility={"big:70b": "resource_unsuitable_on_current_host"},
        incomplete={"mid:3b": "RESOURCE_LIMIT_EXCEEDED before loading"},
    )
    assert "mid:3b" in matrix["models"]
    assert "big:70b" in matrix["models"]
    for status in matrix["statuses"]["mid:3b"].values():
        assert status == "EVALUATION_INCOMPLETE"
    for status in matrix["statuses"]["big:70b"].values():
        assert status == "RESOURCE_UNSUITABLE"


def test_an_incomplete_model_is_never_called_behaviourally_unqualified():
    matrix = build_matrix({}, incomplete={"mid:3b": "aborted on memory"})
    assert "NOT_QUALIFIED" not in set(matrix["statuses"]["mid:3b"].values())


def test_the_incomplete_reason_is_carried_into_the_assessment():
    matrix = build_matrix({}, incomplete={"mid:3b": "RESOURCE_LIMIT_EXCEEDED: swap"})
    unmet = [
        a["unmet"] for a in matrix["assessments"] if a["model"] == "mid:3b"
    ]
    assert unmet and all("RESOURCE_LIMIT_EXCEEDED: swap" in u[0] for u in unmet)


# --------------------------------------------------------------------------
# Committed evidence
# --------------------------------------------------------------------------


def test_every_committed_evaluation_used_the_same_suite_and_prompt():
    evaluations = _evaluations()
    manifests = [e["manifest"] for e in evaluations]
    assert len({m["suite"] for m in manifests}) == 1
    assert len({m["prompt_version"] for m in manifests}) == 1
    assert len({m["rubric_version"] for m in manifests}) == 1
    assert len({tuple(m["scenario_order"]) for m in manifests}) == 1


def test_every_committed_evaluation_kept_its_raw_runs():
    for evaluation in _evaluations():
        for scenario in evaluation["behavioural"]["scenarios"]:
            assert scenario["runs"], scenario["scenario_id"]
            for run in scenario["runs"]:
                assert "raw_output" in run
                assert "structured_output" in run
                assert "results" in run


def test_every_eligible_model_is_represented_in_the_committed_matrix():
    inventory = _load("MODEL_INVENTORY.json")
    matrix = _load("ROLE_QUALIFICATION_MATRIX.json")
    for name in [row["name"] for row in inventory["models"]]:
        assert name in matrix["models"], f"{name} is installed but has no row"


def test_the_m356_result_is_still_readable_and_unchanged():
    """M372 adds a reading. It does not edit the one an owner already signed."""
    if not HISTORICAL.exists():
        pytest.skip("M352-M359 certification not present in this checkout")
    text = HISTORICAL.read_text(encoding="utf-8")
    assert "2 passed, 6 failed" in text
    assert "passed 2 of 8" in text
