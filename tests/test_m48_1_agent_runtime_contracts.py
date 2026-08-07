"""M48.1 — fail-closed agent runtime contract tests (local, no network)."""
from __future__ import annotations

import time

import pytest

from saathi.agent_runtime.models import RunState, IllegalTransition
from saathi.agent_runtime.contracts import (
    AgentRunRequest,
    ApprovalRecord,
    AuthorityClass,
    ContractErrorCode,
    ModelResolutionStatus,
    approval_requirement_for,
    classify_provider_status,
    contract_summary,
    provider_status_is_success,
    require_transition,
    validate_approval_record,
    validate_run_request,
    validate_state_transition_safe,
)


def _codes(errs):
    return {e.code for e in errs}


def test_unknown_capability_denied():
    req = AgentRunRequest(objective="x", requested_capability="teleport_to_mars")
    assert ContractErrorCode.UNKNOWN_CAPABILITY in _codes(validate_run_request(req))


def test_unknown_authority_denied():
    req = AgentRunRequest(
        objective="x",
        requested_capability="plan",
        authority_class="SUPERUSER",
    )
    assert ContractErrorCode.UNKNOWN_AUTHORITY in _codes(validate_run_request(req))


def test_financial_execution_prohibited_by_authority():
    req = AgentRunRequest(
        objective="buy BTC",
        requested_capability="plan",
        authority_class=AuthorityClass.FINANCIAL_EXECUTION.value,
        approval_token="tok",
    )
    codes = _codes(validate_run_request(req))
    assert ContractErrorCode.FINANCIAL_EXECUTION_PROHIBITED in codes


def test_financial_execution_capability_prohibited():
    req = AgentRunRequest(
        objective="place order",
        requested_capability="trade_execute",
        authority_class=AuthorityClass.READ_ONLY.value,
    )
    assert ContractErrorCode.FINANCIAL_EXECUTION_PROHIBITED in _codes(
        validate_run_request(req)
    ) or ContractErrorCode.UNKNOWN_CAPABILITY in _codes(validate_run_request(req))
    # trade_execute is both known and prohibited
    assert any(
        e.code == ContractErrorCode.FINANCIAL_EXECUTION_PROHIBITED
        for e in validate_run_request(req)
    )


def test_missing_approval_blocked_for_local_mutation():
    req = AgentRunRequest(
        objective="migrate db",
        requested_capability="execute_local",
        authority_class=AuthorityClass.LOCAL_MUTATION.value,
    )
    assert ContractErrorCode.MISSING_APPROVAL in _codes(validate_run_request(req))


def test_expired_approval_blocked():
    req = AgentRunRequest(
        objective="migrate db",
        requested_capability="execute_local",
        authority_class=AuthorityClass.LOCAL_MUTATION.value,
        approval_token="tok-1",
        approval_expires_at=time.time() - 10,
    )
    assert ContractErrorCode.EXPIRED_APPROVAL in _codes(validate_run_request(req))


def test_revoked_approval_blocked():
    req = AgentRunRequest(
        objective="migrate db",
        requested_capability="execute_local",
        authority_class=AuthorityClass.LOCAL_MUTATION.value,
        approval_token="tok-1",
        approval_expires_at=time.time() + 3600,
        approval_revoked=True,
    )
    assert ContractErrorCode.REVOKED_APPROVAL in _codes(validate_run_request(req))


def test_valid_read_only_request_passes():
    req = AgentRunRequest(
        objective="summarize mission status",
        requested_capability="plan",
        authority_class=AuthorityClass.READ_ONLY.value,
        timeout_sec=30,
        max_retries=2,
    )
    assert validate_run_request(req) == []


def test_invalid_state_transition_rejected():
    errs = validate_state_transition_safe(RunState.CREATED, RunState.COMPLETED)
    assert ContractErrorCode.INVALID_TRANSITION in _codes(errs)


def test_terminal_state_restart_rejected():
    errs = validate_state_transition_safe(RunState.COMPLETED, RunState.RUNNING)
    assert ContractErrorCode.TERMINAL_RESTART in _codes(errs)
    with pytest.raises(IllegalTransition):
        require_transition(RunState.FAILED, RunState.QUEUED)


def test_legal_transition_ok():
    assert validate_state_transition_safe(RunState.CREATED, RunState.PLANNING) == []
    require_transition(RunState.QUEUED, RunState.RUNNING)


def test_missing_objective_rejected():
    req = AgentRunRequest(objective="  ", requested_capability="plan")
    assert ContractErrorCode.MISSING_OBJECTIVE in _codes(validate_run_request(req))


def test_invalid_timeout_rejected():
    req = AgentRunRequest(
        objective="x",
        requested_capability="plan",
        timeout_sec=0,
    )
    assert ContractErrorCode.INVALID_TIMEOUT in _codes(validate_run_request(req))
    req2 = AgentRunRequest(
        objective="x",
        requested_capability="plan",
        timeout_sec=99999,
    )
    assert ContractErrorCode.INVALID_TIMEOUT in _codes(validate_run_request(req2))


def test_unbounded_retry_rejected():
    req = AgentRunRequest(
        objective="x",
        requested_capability="plan",
        max_retries=99,
    )
    assert ContractErrorCode.UNBOUNDED_RETRY in _codes(validate_run_request(req))


def test_secret_like_field_rejected():
    req = AgentRunRequest(
        objective="x",
        requested_capability="plan",
        input_payload={"api_key": "sk-abcdefghijklmnopqrstuvwxyz"},
    )
    assert ContractErrorCode.SECRET_FIELD in _codes(validate_run_request(req))


def test_unavailable_provider_not_success():
    st = classify_provider_status(False, configured=True)
    assert st == ModelResolutionStatus.UNAVAILABLE
    assert provider_status_is_success(st) is False
    st2 = classify_provider_status(True, used_fallback=True)
    assert st2 == ModelResolutionStatus.FALLBACK_SELECTED
    assert provider_status_is_success(st2) is True
    st3 = classify_provider_status(False, configured=False)
    assert st3 == ModelResolutionStatus.CONFIGURATION_MISSING
    assert provider_status_is_success(st3) is False


def test_approval_record_pending_and_expired():
    now = time.time()
    pending = ApprovalRecord(approval_id="a1", status="pending")
    assert ContractErrorCode.MISSING_APPROVAL in _codes(
        validate_approval_record(pending, now=now)
    )
    expired = ApprovalRecord(
        approval_id="a2", status="granted", expires_at=now - 1
    )
    assert ContractErrorCode.EXPIRED_APPROVAL in _codes(
        validate_approval_record(expired, now=now)
    )


def test_approval_requirement_financial_advisory():
    assert (
        approval_requirement_for(AuthorityClass.FINANCIAL_ADVISORY).value
        == "EXPLICIT_APPROVAL_REQUIRED"
    )


def test_contract_summary_read_only():
    s = contract_summary()
    assert s["canonical_runtime"] == "saathi.agent_runtime"
    assert s["financial_execution"] == "PROHIBITED"
    assert "READ_ONLY" in s["authority_classes"]
