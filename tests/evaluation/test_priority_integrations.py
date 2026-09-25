from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from saathi.baadar.provenance import AssetManifest, SourceType
from saathi.baadar.publication_gate import PublicationGate
from saathi.evaluation.collaboration import attach_collaboration_review, evaluate_collaboration
from saathi.evaluation.status import build_priority_status
from saathi.evaluation.workflows import run_workflow_evaluations
from saathi.inference.adapters.kimi import (
    KIMI_CODING_MODEL,
    KimiEngine,
    validate_kimi_base_url,
)
from saathi.inference.priority_policy import CloudBudgetPolicy, MissionModelClass, constraints_for
from saathi.inference.provider_descriptor import get_descriptor
from saathi.inference.provider_policy import family_for_model_router_name, resolve_availability
from saathi.model_router import ModelLabel


def _asset(**overrides):
    values = {
        "asset_id": "asset-1",
        "asset_type": "image",
        "created_at": "2026-07-31T00:00:00Z",
        "source_type": SourceType.GENERATED,
        "source_location": "local://fixture/asset.png",
        "generation_provider": "fixture",
        "model_name": "fixture-model",
        "model_version": "1",
        "prompt_reference": "prompt:fixture-1",
        "input_asset_references": (),
        "licence": "CC0-1.0",
        "commercial_use_status": "allowed",
        "attribution_required": False,
        "attribution_text": "",
        "music_rights": "not_applicable",
        "font_rights": "not_applicable",
        "voice_rights": "not_applicable",
        "character_rights": "not_applicable",
        "similarity_review_status": "passed",
        "human_review_status": "approved",
        "approved_by": "fixture-reviewer",
        "approved_at": "2026-07-31T00:01:00Z",
        "publication_destinations": ("mock://baadar",),
        "content_hash": "sha256:fixture-1",
        "permission_confirmed": True,
    }
    values.update(overrides)
    return AssetManifest(**values)


def _gate(approved=True):
    audit = []
    gate = PublicationGate(
        approval_checker=lambda approval_id, scope: approved and approval_id == "approval-1" and scope == "baadar.publish:mock://baadar",
        audit_writer=lambda event, payload: audit.append((event, payload)),
    )
    return gate, audit


def test_kimi_url_and_provider_are_fail_closed(monkeypatch):
    assert validate_kimi_base_url("https://api.moonshot.ai/v1") == (True, "ok")
    for bad in ("http://api.moonshot.ai/v1", "https://example.com/v1", "https://api.moonshot.ai/other"):
        assert validate_kimi_base_url(bad)[0] is False
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    assert resolve_availability("kimi").value == "policy_disabled"
    descriptor = get_descriptor("kimi")
    assert descriptor is not None
    assert descriptor.configured is False
    assert descriptor.max_retries == 2
    assert family_for_model_router_name("kimi/kimi-k3") == "kimi"


def test_kimi_adapter_uses_injected_transport_without_live_api():
    calls = []

    def transport(method, url, body=None, timeout=None):
        calls.append((method, url, body, timeout))
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        }

    engine = KimiEngine(api_key="fixture-not-a-real-key", transport=transport)
    result = asyncio.run(
        engine.generate([{"role": "user", "content": "fixture"}], model=KIMI_CODING_MODEL, max_tokens=8)
    )
    assert result.text == "ok"
    assert calls[0][1] == "https://api.moonshot.ai/v1/chat/completions"
    estimate = asyncio.run(engine.estimate_cost(model=KIMI_CODING_MODEL, prompt_tokens=1000, completion_tokens=1000))
    assert estimate.known is True
    assert estimate.amount == pytest.approx(0.00495)


def test_priority_constraints_and_monthly_budget():
    assert constraints_for(MissionModelClass.LOCAL_ROUTINE).label is ModelLabel.PRIVATE
    assert constraints_for(MissionModelClass.CRITICAL_EXPENSIVE).approval_required is True
    policy = CloudBudgetPolicy()
    assert policy.authorize(cumulative_monthly_cost="14", estimated_mission_cost="1") == (True, "warning_threshold")
    assert policy.authorize(cumulative_monthly_cost="18.5", estimated_mission_cost="0.6") == (False, "monthly_hard_stop")
    assert policy.authorize(
        cumulative_monthly_cost=Decimal("1"),
        estimated_mission_cost=Decimal("1"),
        expensive=True,
        approved=False,
    ) == (False, "approval_required")


def test_five_offline_workflows_are_deterministic_and_bounded():
    first = [result.to_dict() for result in run_workflow_evaluations()]
    second = [result.to_dict() for result in run_workflow_evaluations()]
    assert first == second
    assert len(first) == 5
    assert all(row["passed"] for row in first)
    assert all(row["estimated_api_cost_usd"] == "0.00" for row in first)
    assert all(row["iterations"] <= 20 for row in first)
    assert first[-1]["trace"][-2]["event"] == "stopped_before_real_publishing"


def test_collaboration_uncertainty_correction_resume_and_denial():
    trace = [
        {"event": "plan_created"},
        {"event": "uncertainty_disclosed"},
        {"event": "evidence", "kind": "retrieved_evidence"},
        {"event": "user_correction", "plan_updated": True},
        {"event": "intent_checked", "within_scope": True},
        {"event": "interrupted", "checkpoint_valid": True},
        {"event": "resumed", "from_checkpoint": "cp-1", "duplicate_action": False},
        {"event": "control_boundary_checked", "denial_stops_execution": True},
        {"event": "approval_requested", "action": "x", "risk": "y", "scope": "z", "consequence": "stop"},
        {"event": "approval_denied"},
        {"event": "final_evidence_report"},
    ]
    review = evaluate_collaboration(trace)
    assert review.evidence_separation_valid is True
    result = attach_collaboration_review({"mission_id": "fixture"}, trace)
    assert result["collaboration_review"]["score"] == review.score
    assert not any(row["name"] == "user_control_preservation" and row["score"] == 0 for row in result["collaboration_review"]["metrics"])


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"source_type": SourceType.UNKNOWN}, "source_unknown"),
        ({"licence": ""}, "licence_missing"),
        ({"commercial_use_status": "unclear"}, "commercial_rights_unclear"),
        ({"attribution_required": True, "attribution_text": ""}, "attribution_missing"),
        ({"character_rights": "unapproved"}, "character_rights_unresolved"),
        ({"music_rights": "unresolved"}, "music_rights_unresolved"),
        ({"similarity_review_status": ""}, "similarity_review_incomplete"),
        ({"approved_by": ""}, "human_review_evidence_missing"),
    ],
)
def test_provenance_gate_blocks_invalid_assets(overrides, reason):
    gate, audit = _gate()
    decision = gate.evaluate([_asset(**overrides)], approval_id="approval-1", destination="mock://baadar")
    assert decision.allowed is False
    assert any(reason in item for item in decision.reasons)
    assert audit[-1][1]["status"] == "BLOCKED"


def test_provenance_source_types_and_approved_simulation():
    gate, audit = _gate()
    assets = [
        _asset(asset_id="original", source_type=SourceType.ORIGINAL, content_hash="sha256:a"),
        _asset(asset_id="licensed", source_type=SourceType.LICENSED, content_hash="sha256:b", attribution_required=True, attribution_text="Fixture Author"),
        _asset(asset_id="public", source_type=SourceType.PUBLIC_DOMAIN, content_hash="sha256:c"),
    ]
    decision = gate.evaluate(assets, approval_id="approval-1", destination="mock://baadar")
    assert decision.allowed is True
    assert decision.status == "APPROVED_SIMULATION"
    assert audit[-1][0] == "baadar.publication_gate_evaluated"


def test_duplicate_hash_denial_and_real_publication_block():
    gate, _ = _gate()
    duplicate = gate.evaluate(
        [_asset(asset_id="a"), _asset(asset_id="b")],
        approval_id="approval-1",
        destination="mock://baadar",
    )
    assert duplicate.allowed is False
    assert "duplicate_asset_hash" in duplicate.reasons
    real = gate.evaluate([_asset()], approval_id="approval-1", destination="mock://baadar", simulate=False)
    assert real.allowed is False
    assert "real_publication_not_authorized" in real.reasons


def test_approval_denial_stops_gate_and_status_contract():
    gate, _ = _gate(approved=False)
    decision = gate.evaluate([_asset()], approval_id="approval-1", destination="mock://baadar")
    assert decision.allowed is False
    assert "existing_approval_missing_or_invalid" in decision.reasons
    status = build_priority_status(approval_required=True, provenance_status=decision.status)
    assert status["schema"] == "saathios.mission_control.priority_status.v1"
    assert status["rollback_available"] is True
