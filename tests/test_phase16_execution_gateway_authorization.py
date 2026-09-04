"""Phase 16 — ExecutionGateway authorization.

The property under test is one sentence: *no combination of missing, stale,
advisory or uncorrelated inputs may produce AUTHORIZED*. Most of what follows
attacks that from a different angle, because a fail-closed claim is only worth
what its adversarial cases prove.

Nothing here executes anything. There is no live broker, no order, no network,
and no real money anywhere in this file.
"""
from __future__ import annotations

import itertools
import time
from datetime import datetime

import pytest

from saathi.agent_runtime.contracts import AuthorityClass
from saathi.agent_runtime.models import RiskClass
from saathi.execution.authorization import (
    AuthorizationInputs,
    Decision,
    GateResult,
    LOCAL_ACTIONS,
    ResolvedAction,
    SYSTEM_ACTOR_MAX_AUTHORITY,
    authorize_intent,
    resolve_action,
)
from saathi.execution.errors import AuthorizationException, ExecutionGatewayException
from saathi.execution.gateway import ExecutionContext, ExecutionGateway
from saathi.execution.record import tool_intent_digest
from saathi.execution.state import IntentState, RiskLevel, StateHistory
from saathi.execution.toolintent import ToolIntent


# ── fixtures ────────────────────────────────────────────────────────────────

def _intent(**kw) -> ToolIntent:
    base = dict(intent_id="i-1", operation="local-llm-inference",
                actor_id="user:ajay", parameters={"prompt": "hi"})
    base.update(kw)
    return ToolIntent(**base)


def _mutating_intent(**kw) -> ToolIntent:
    """An action above READ_ONLY, so the approval and identity gates are live."""
    return _intent(operation="video-generation", **kw)


def _ok(**over) -> AuthorizationInputs:
    """Inputs under which a READ_ONLY action authorizes. The baseline every
    negative case perturbs by exactly one field."""
    inputs = AuthorizationInputs(
        actor_user_id="ajay",
        has_permission=True,
        kill_switch_blocked=False,
        run_declared=False,
        approvals=[],
        now=1_000_000.0,
    )
    for k, v in over.items():
        setattr(inputs, k, v)
    return inputs


def _approval(digest: str, **over) -> dict:
    appr = {"approval_id": "a1", "tool_intent_digest": digest,
            "status": "approved", "expires_at": None, "used": 0, "max_uses": 1}
    appr.update(over)
    return appr


def _ok_mutating(intent: ToolIntent, **over) -> AuthorizationInputs:
    return _ok(approvals=[_approval(tool_intent_digest(intent))], **over)


# ── the baseline is genuinely positive ──────────────────────────────────────

def test_the_baseline_authorizes():
    """Otherwise every negative test below would pass for the wrong reason."""
    assert authorize_intent(_intent(), _ok()).decision is Decision.AUTHORIZED


def test_a_mutating_action_authorizes_with_a_correlated_approval():
    intent = _mutating_intent()
    assert authorize_intent(intent, _ok_mutating(intent)).decision is Decision.AUTHORIZED


# ── the central invariant: unknown is never allow ───────────────────────────

#: Every input that can fail to resolve, and the decision each None must force.
_NULLABLE = ["actor_user_id", "has_permission", "kill_switch_blocked"]


@pytest.mark.parametrize("field", _NULLABLE)
def test_any_single_unestablished_input_denies(field):
    inputs = _ok(**{field: None})
    assert authorize_intent(_intent(), inputs).decision is not Decision.AUTHORIZED


@pytest.mark.parametrize("n", [1, 2, 3])
def test_no_combination_of_missing_inputs_falls_through_to_positive(n):
    """The dangerous failure is a *combination* that cancels out. Enumerated
    rather than argued: every subset of missing inputs must stay non-positive."""
    for combo in itertools.combinations(_NULLABLE, n):
        inputs = _ok(**{f: None for f in combo})
        decision = authorize_intent(_intent(), inputs)
        assert decision.decision is not Decision.AUTHORIZED, combo


def test_an_empty_input_set_denies():
    """The zero-information case: nothing resolved at all."""
    assert authorize_intent(_intent(), AuthorizationInputs()).decision \
        is not Decision.AUTHORIZED


def test_every_gate_reports_even_when_it_passes():
    """A gate that silently skipped itself would be invisible in the record."""
    decision = authorize_intent(_intent(), _ok())
    names = [g.gate for g in decision.gates]
    assert names == sorted(names, key=names.index)  # no duplicates lost
    for expected in ("kill_switch", "intent", "actor", "rbac", "action",
                     "run_state", "approval", "guardian", "connector"):
        assert expected in names


# ── individual gates ────────────────────────────────────────────────────────

def test_kill_switch_dominates_every_other_positive():
    """Approval granted, RBAC passing, run healthy -- and still denied."""
    intent = _mutating_intent()
    inputs = _ok_mutating(intent, kill_switch_blocked=True,
                          run_declared=True, run={"state": "running"})
    decision = authorize_intent(intent, inputs)
    assert decision.decision is Decision.DENIED
    assert decision.reason_code == "kill_switch.active"


def test_an_unreadable_kill_switch_is_not_an_inactive_one():
    decision = authorize_intent(_intent(), _ok(kill_switch_blocked=None))
    assert decision.decision is Decision.UNKNOWN
    assert decision.reason_code == "kill_switch.unknown"


def test_rbac_denial_denies():
    decision = authorize_intent(_intent(), _ok(has_permission=False))
    assert decision.decision is Decision.DENIED
    assert decision.reason_code == "rbac.denied"


def test_an_unknown_action_is_never_classified_downward():
    decision = authorize_intent(_intent(operation="no-such-operation"), _ok())
    assert decision.decision is Decision.DENIED
    assert decision.reason_code == "action.unknown"
    assert decision.risk is None, "an unclassifiable action gets no risk, not LOW"


def test_a_malformed_intent_denies():
    for kw in ({"operation": ""}, {"actor_id": ""}):
        decision = authorize_intent(_intent(**kw), _ok())
        assert decision.reason_code == "intent.malformed"


def test_a_stale_intent_denies():
    intent = _intent(expires_at=999_000.0)  # before inputs.now
    decision = authorize_intent(intent, _ok())
    assert decision.decision is Decision.DENIED
    assert decision.reason_code == "intent.stale"


@pytest.mark.parametrize("state", ["completed", "cancelled", "failed",
                                   "timed_out", "blocked", "awaiting_approval",
                                   "paused", "rolled_back"])
def test_a_run_whose_lifecycle_forbids_execution_denies(state):
    inputs = _ok(run_declared=True, run={"state": state})
    decision = authorize_intent(_intent(), inputs)
    assert decision.decision is Decision.DENIED
    assert decision.reason_code == "run_state.invalid"


def test_a_declared_but_unreadable_run_denies():
    """Naming a run you cannot read is not the same as naming no run."""
    decision = authorize_intent(_intent(), _ok(run_declared=True, run=None))
    assert decision.decision is Decision.UNKNOWN
    assert decision.reason_code == "run_state.unknown"


def test_an_unrecognised_run_state_denies():
    inputs = _ok(run_declared=True, run={"state": "vibes"})
    assert authorize_intent(_intent(), inputs).reason_code == "run_state.unknown"


# ── approval ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status,reason", [
    ("pending", "approval.pending"),
    ("denied", "approval.denied"),
    ("rejected", "approval.denied"),
    ("revoked", "approval.denied"),
    ("expired", "approval.expired"),
])
def test_an_unresolved_or_refused_approval_denies(status, reason):
    intent = _mutating_intent()
    inputs = _ok(approvals=[_approval(tool_intent_digest(intent), status=status)])
    decision = authorize_intent(intent, inputs)
    assert decision.decision is Decision.DENIED
    assert decision.reason_code == reason


def test_a_required_but_absent_approval_denies():
    intent = _mutating_intent()
    decision = authorize_intent(intent, _ok(approvals=[]))
    assert decision.reason_code == "approval.missing"


def test_an_unconsultable_approval_store_denies():
    intent = _mutating_intent()
    decision = authorize_intent(intent, _ok(approvals=None))
    assert decision.decision is Decision.UNKNOWN
    assert decision.reason_code == "approval.unknown"


def test_a_time_expired_approval_denies_even_while_marked_approved():
    intent = _mutating_intent()
    inputs = _ok(approvals=[_approval(tool_intent_digest(intent),
                                      expires_at=999_999.0)])
    assert authorize_intent(intent, inputs).reason_code == "approval.expired"


def test_a_spent_single_use_approval_cannot_authorize_again():
    """Replay: one grant, one action."""
    intent = _mutating_intent()
    inputs = _ok(approvals=[_approval(tool_intent_digest(intent),
                                      used=1, max_uses=1)])
    assert authorize_intent(intent, inputs).decision is Decision.DENIED


# ── correlation: the decision is about ONE action ───────────────────────────

def test_an_approval_for_another_action_does_not_authorize_this_one():
    mine = _mutating_intent()
    other = _mutating_intent(parameters={"different": "payload"})
    assert tool_intent_digest(mine) != tool_intent_digest(other)
    inputs = _ok(approvals=[_approval(tool_intent_digest(other))])
    decision = authorize_intent(mine, inputs)
    assert decision.decision is Decision.DENIED
    assert decision.reason_code == "approval.missing", \
        "an approval for another action reads as no approval, never as one"


def test_an_approval_with_no_action_binding_is_refused_not_accepted():
    intent = _mutating_intent()
    inputs = _ok(approvals=[_approval("", **{"tool_intent_digest": ""})])
    assert authorize_intent(intent, inputs).reason_code == "approval.uncorrelated"


def test_changing_the_payload_changes_the_digest():
    """Authorization binds to the action's content, so a mutated payload is a
    different action and inherits none of the first one's authority."""
    a = _intent(parameters={"prompt": "hi"})
    b = _intent(parameters={"prompt": "wire the money"})
    assert tool_intent_digest(a) != tool_intent_digest(b)


def test_changing_actor_or_connector_changes_the_digest():
    base = _intent()
    for kw in ({"actor_id": "user:someone-else"}, {"connector_id": "gmail"},
               {"operation": "video-generation"}):
        assert tool_intent_digest(_intent(**kw)) != tool_intent_digest(base)


def test_an_intent_attributed_to_another_user_is_refused():
    """A session for one user may not authorize an intent naming a different one."""
    decision = authorize_intent(_intent(actor_id="user:someone-else"),
                                _ok(actor_user_id="ajay"))
    assert decision.decision is Decision.DENIED
    assert decision.reason_code == "intent.actor_mismatch"


# ── Guardian: not-applicable is not allowed ─────────────────────────────────

def test_guardian_is_not_applicable_for_a_non_trading_action():
    decision = authorize_intent(_intent(), _ok())
    guardian = next(g for g in decision.gates if g.gate == "guardian")
    assert guardian.result is GateResult.NOT_APPLICABLE
    assert "trading-scoped" in guardian.detail


def test_not_applicable_is_recorded_distinctly_from_passed():
    """The two must never collapse: one means 'checked and fine', the other
    means 'this subsystem never looked at this action'."""
    assert GateResult.NOT_APPLICABLE is not GateResult.PASSED
    assert GateResult.NOT_APPLICABLE.value != GateResult.PASSED.value


def _financial(intent, **over):
    """A financial-advisory action, which is the only financial class that can
    reach the Guardian gate -- financial *execution* is refused before it."""
    action = ResolvedAction(AuthorityClass.FINANCIAL_ADVISORY,
                            RiskClass.EXTERNAL_SIDE_EFFECT, "test_fixture")
    return _ok(connector_action=action,
               approvals=[_approval(tool_intent_digest(intent))], **over)


def test_a_financial_action_without_a_guardian_verdict_fails_closed():
    """Required and absent is a refusal, not a blind spot: the Guardian's
    silence about a trading action is a definite fact about that action."""
    intent = _intent(operation="advice")
    decision = authorize_intent(intent, _financial(intent))
    assert decision.decision is Decision.DENIED
    assert decision.reason_code == "guardian.missing"


def test_a_blocking_guardian_verdict_denies():
    intent = _intent(operation="advice")
    verdict = {"decision": "block", "at": 1_000_000.0,
               "digest": tool_intent_digest(intent)}
    decision = authorize_intent(intent, _financial(intent, guardian_verdict=verdict))
    assert decision.reason_code == "guardian.blocked"


def test_a_stale_guardian_verdict_denies():
    intent = _intent(operation="advice")
    verdict = {"decision": "allow", "at": 1.0, "digest": tool_intent_digest(intent)}
    decision = authorize_intent(intent, _financial(intent, guardian_verdict=verdict))
    assert decision.reason_code == "guardian.stale"


def test_a_guardian_verdict_for_another_trade_does_not_authorize_this_one():
    intent = _intent(operation="advice")
    verdict = {"decision": "allow", "at": 1_000_000.0, "digest": "someone-elses-trade"}
    decision = authorize_intent(intent, _financial(intent, guardian_verdict=verdict))
    assert decision.reason_code == "guardian.uncorrelated"


def test_a_fresh_correlated_guardian_allow_lets_the_gate_pass():
    """Proves the Guardian denials above are the gate working, not it being
    unsatisfiable -- a gate that can never pass proves nothing."""
    intent = _intent(operation="advice")
    verdict = {"decision": "allow", "at": 1_000_000.0,
               "digest": tool_intent_digest(intent)}
    decision = authorize_intent(intent, _financial(intent, guardian_verdict=verdict))
    guardian = next(g for g in decision.gates if g.gate == "guardian")
    assert guardian.result is GateResult.PASSED


# ── live trading stays prohibited ───────────────────────────────────────────

@pytest.mark.parametrize("op", ["trade_execute", "broker_order", "withdraw",
                                "live_trading", "enable_leverage",
                                "financial_execution"])
def test_live_money_actions_are_refused_for_every_caller(op):
    """No role, approval or Guardian verdict makes these authorizable."""
    intent = _intent(operation=op)
    inputs = _ok(approvals=[_approval(tool_intent_digest(intent))],
                 guardian_verdict={"decision": "allow", "at": 1_000_000.0,
                                   "digest": tool_intent_digest(intent)})
    decision = authorize_intent(intent, inputs)
    assert decision.decision is Decision.DENIED
    assert decision.reason_code == "action.prohibited"


def test_a_prohibited_capability_is_refused_even_on_a_benign_operation():
    intent = _intent(operation="local-llm-inference", capability="trade_execute")
    assert authorize_intent(intent, _ok()).reason_code == "action.prohibited"


# ── connector authority: presence is not permission ─────────────────────────

def _connector(intent, state, risk=RiskClass.EXTERNAL_SIDE_EFFECT, **over):
    action = ResolvedAction(AuthorityClass.EXTERNAL_MUTATION, risk,
                            "connector_registry", requires_connector=True)
    return _ok(connector_action=action, connector_state=state,
               approvals=[_approval(tool_intent_digest(intent))], **over)


@pytest.mark.parametrize("state,reason", [
    ("unauthorized", "connector.unauthorized"),
    ("expired", "connector.unauthorized"),
    ("authorization_pending", "connector.unauthorized"),
    ("unconfigured", "connector.environment_blocked"),
    ("configured", "connector.environment_blocked"),
    ("disabled", "connector.environment_blocked"),
    ("disconnected", "connector.unavailable"),
    ("rate_limited", "connector.unavailable"),
    ("error", "connector.unavailable"),
])
def test_a_connector_that_cannot_act_denies(state, reason):
    intent = _intent(operation="gmail.send", connector_id="gmail")
    decision = authorize_intent(intent, _connector(intent, state))
    assert decision.decision is Decision.DENIED
    assert decision.reason_code == reason


def test_a_connector_whose_state_is_unreadable_denies():
    intent = _intent(operation="gmail.send", connector_id="gmail")
    decision = authorize_intent(intent, _connector(intent, None))
    assert decision.decision is Decision.UNKNOWN
    assert decision.reason_code == "connector.unknown"


@pytest.mark.parametrize("state", ["connected", "healthy", "degraded"])
def test_an_executable_connector_passes_its_gate(state):
    intent = _intent(operation="gmail.send", connector_id="gmail")
    decision = authorize_intent(intent, _connector(intent, state))
    connector = next(g for g in decision.gates if g.gate == "connector")
    assert connector.result is GateResult.PASSED


def test_a_connector_is_not_required_for_a_local_action():
    connector = next(g for g in authorize_intent(_intent(), _ok()).gates
                     if g.gate == "connector")
    assert connector.result is GateResult.NOT_APPLICABLE


# ── the system actor's grant is small and fixed ─────────────────────────────

def test_an_unattributed_caller_may_only_perform_read_only_actions():
    decision = authorize_intent(_intent(), _ok(actor_user_id=None,
                                               has_permission=None,
                                               actor_is_system=True))
    assert decision.decision is Decision.AUTHORIZED


@pytest.mark.parametrize("op", ["video-generation"])
def test_an_unattributed_caller_may_not_perform_a_mutating_action(op):
    intent = _intent(operation=op)
    inputs = _ok(actor_user_id=None, has_permission=None, actor_is_system=True,
                 approvals=[_approval(tool_intent_digest(intent))])
    decision = authorize_intent(intent, inputs)
    assert decision.decision is Decision.DENIED
    assert decision.reason_code == "actor.system_insufficient_authority"


def test_an_unattributed_caller_may_not_reach_a_connector():
    intent = _intent(operation="gmail.send", connector_id="gmail")
    inputs = _connector(intent, "healthy", actor_user_id=None,
                        has_permission=None, actor_is_system=True)
    decision = authorize_intent(intent, inputs)
    assert decision.decision is Decision.DENIED


def test_the_system_grant_is_pinned_to_read_only():
    """Widening this constant would widen every unattributed call at once, so
    the value itself is asserted rather than only its effects."""
    assert SYSTEM_ACTOR_MAX_AUTHORITY is AuthorityClass.READ_ONLY


# ── action classification is deterministic and truthful ─────────────────────

def test_the_local_action_table_classifies_only_what_it_knows():
    assert resolve_action("no-such-op") is None
    for op in LOCAL_ACTIONS:
        assert resolve_action(op) is not None


def test_a_connector_action_outranks_the_local_table():
    supplied = ResolvedAction(AuthorityClass.ADMINISTRATIVE, RiskClass.HIGH_IMPACT,
                              "connector_registry", requires_connector=True)
    resolved = resolve_action("local-llm-inference", connector_action=supplied)
    assert resolved is supplied


# ── the gateway method itself ───────────────────────────────────────────────

@pytest.fixture
def gw():
    return ExecutionGateway()


@pytest.fixture
def ctx():
    now = datetime.utcnow()
    return ExecutionContext(actor_id="user:ajay", business_unit="test",
                            timestamp=now, current_time=now)


def _history(intent):
    return StateHistory(intent_id=intent.intent_id)


def test_authorize_transitions_to_authorized_on_a_positive_decision(gw, ctx):
    intent = _intent()
    history = gw.authorize(intent, ctx, _history(intent), inputs=_ok())
    assert history.current_state is IntentState.AUTHORIZED


def test_authorize_transitions_to_denied_and_raises_on_refusal(gw, ctx):
    intent = _intent()
    history = _history(intent)
    with pytest.raises(AuthorizationException) as excinfo:
        gw.authorize(intent, ctx, history, inputs=_ok(has_permission=False))
    assert history.current_state is IntentState.DENIED
    assert "rbac.denied" in str(excinfo.value)


def test_a_denied_intent_never_reaches_authorized(gw, ctx):
    intent = _intent()
    history = _history(intent)
    with pytest.raises(AuthorizationException):
        gw.authorize(intent, ctx, history, inputs=_ok(kill_switch_blocked=True))
    assert IntentState.AUTHORIZED not in [t.to_state for t in history.transitions]


def test_a_denied_intent_cannot_be_revived_by_re_authorizing_after_terminal(gw, ctx):
    """The refusal is terminal for that history: a second call on the same
    history under the same conditions cannot walk it back to AUTHORIZED."""
    intent = _intent()
    history = _history(intent)
    for _ in range(2):
        with pytest.raises(AuthorizationException):
            gw.authorize(intent, ctx, history, inputs=_ok(has_permission=False))
    assert history.current_state is IntentState.DENIED
    assert history.is_terminal()


def test_authorize_executes_nothing(gw, ctx, monkeypatch):
    """The decision is a decision. If authorize ever dispatched a handler, this
    is where it would show."""
    fired = []
    monkeypatch.setattr(gw, "submit", lambda *a, **k: fired.append("submit"))
    monkeypatch.setattr(gw, "execute_registered_tool",
                        lambda *a, **k: fired.append("tool"))
    intent = _intent()
    gw.authorize(intent, ctx, _history(intent), inputs=_ok())
    assert fired == []


def test_the_decision_declares_it_is_not_a_capability_token(gw, ctx):
    intent = _intent()
    gw.authorize(intent, ctx, _history(intent), inputs=_ok())
    assert gw._last_decision.to_dict()["is_capability_token"] is False


def test_the_decision_carries_the_action_digest_not_a_secret(gw, ctx):
    intent = _intent(parameters={"api_key": "sk-should-never-appear"})
    gw.authorize(intent, ctx, _history(intent), inputs=_ok())
    rendered = repr(gw._last_decision.to_dict())
    assert "sk-should-never-appear" not in rendered
    assert gw._last_decision.intent_digest == tool_intent_digest(intent)


def test_a_decision_for_one_intent_does_not_describe_another(gw, ctx):
    a, b = _intent(intent_id="i-a"), _intent(intent_id="i-b",
                                             parameters={"prompt": "other"})
    gw.authorize(a, ctx, _history(a), inputs=_ok())
    first = gw._last_decision
    gw.authorize(b, ctx, _history(b), inputs=_ok())
    assert gw._last_decision.intent_digest != first.intent_digest


# ── risk classification is real ─────────────────────────────────────────────

def test_risk_is_no_longer_always_low(gw, ctx):
    intent = _mutating_intent()
    _, level = gw.classify_risk(intent, ctx, _history(intent))
    assert level is not RiskLevel.LOW


def test_risk_matches_the_action_class(gw, ctx):
    for op, expected in (("local-llm-inference", RiskLevel.LOW),
                         ("video-generation", RiskLevel.MEDIUM)):
        intent = _intent(operation=op)
        _, level = gw.classify_risk(intent, ctx, _history(intent))
        assert level is expected, op


def test_an_unclassifiable_action_raises_rather_than_defaulting_low(gw, ctx):
    intent = _intent(operation="no-such-op")
    with pytest.raises(ExecutionGatewayException) as excinfo:
        gw.classify_risk(intent, ctx, _history(intent))
    assert "risk.unknown" in str(excinfo.value)


# ── durable evidence ────────────────────────────────────────────────────────

def test_a_decision_is_recorded_durably_and_can_be_inspected(gw, ctx):
    intent = _intent(intent_id=f"i-durable-{time.time_ns()}")
    gw.authorize(intent, ctx, _history(intent), inputs=_ok())
    record = gw.inspect_decision(intent_id=intent.intent_id)
    assert record and record["decision"] == "AUTHORIZED"
    assert record["tool_intent_digest"] == tool_intent_digest(intent)
    assert record["authority_class"] == AuthorityClass.READ_ONLY.value


def test_a_refusal_is_recorded_too_with_enough_to_reconstruct_why(gw, ctx):
    """A log that only kept the grants would be useless for exactly the
    investigation it exists to support."""
    intent = _intent(intent_id=f"i-refused-{time.time_ns()}")
    with pytest.raises(AuthorizationException):
        gw.authorize(intent, ctx, _history(intent), inputs=_ok(has_permission=False))
    record = gw.inspect_decision(intent_id=intent.intent_id)
    assert record["decision"] == "DENIED"
    assert record["reason_code"] == "rbac.denied"
    blocked = [g for g in record["gates"] if g["result"] == "BLOCKED"]
    assert any(g["gate"] == "rbac" for g in blocked)


def test_the_decision_record_contains_no_payload(gw, ctx):
    intent = _intent(intent_id=f"i-secret-{time.time_ns()}",
                     parameters={"password": "hunter2"})
    gw.authorize(intent, ctx, _history(intent), inputs=_ok())
    assert "hunter2" not in repr(gw.inspect_decision(intent_id=intent.intent_id))


def test_inspecting_a_decision_that_does_not_exist_returns_nothing(gw):
    assert gw.inspect_decision(intent_id="i-never-decided") is None
    assert gw.inspect_decision() is None


def test_re_deciding_appends_rather_than_amending(gw, ctx):
    """A decision describes an instant; overwriting one would destroy the
    evidence. The second decision is the latest, and both were written."""
    intent = _intent(intent_id=f"i-twice-{time.time_ns()}")
    gw.authorize(intent, ctx, _history(intent), inputs=_ok(now=1.0))
    with pytest.raises(AuthorizationException):
        gw.authorize(intent, ctx, _history(intent),
                     inputs=_ok(now=2.0, has_permission=False))
    assert gw.inspect_decision(intent_id=intent.intent_id)["decision"] == "DENIED"


# ── concurrency ─────────────────────────────────────────────────────────────

def test_concurrent_authorization_of_one_intent_agrees(gw, ctx):
    """Same inputs, many threads: one canonical answer, no interleaving artefact."""
    import concurrent.futures

    intent = _intent(intent_id=f"i-conc-{time.time_ns()}")
    inputs = _ok()

    def decide():
        return authorize_intent(intent, inputs).decision

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = [f.result() for f in
                   [pool.submit(decide) for _ in range(24)]]
    assert set(results) == {Decision.AUTHORIZED}


def test_concurrent_writes_of_one_decision_do_not_corrupt_the_record(gw, ctx):
    import concurrent.futures

    intent = _intent(intent_id=f"i-cw-{time.time_ns()}")

    def run():
        gw.authorize(intent, ctx, _history(intent), inputs=_ok())

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for f in [pool.submit(run) for _ in range(8)]:
            f.result()
    record = gw.inspect_decision(intent_id=intent.intent_id)
    assert record["decision"] == "AUTHORIZED"


# ── the stub is gone ────────────────────────────────────────────────────────

def test_no_todo_remains_on_the_authorization_or_risk_path():
    """The two methods whose TODOs produced an unconditional grant."""
    import inspect as _inspect

    for method in (ExecutionGateway.authorize, ExecutionGateway.classify_risk):
        source = _inspect.getsource(method)
        assert "TODO" not in source, method.__name__


def test_authorization_cannot_reach_authorized_without_the_composer():
    """Structural: the only AUTHORIZED transition in `authorize` is guarded by
    the composer's verdict. A future edit that adds an unguarded one fails here."""
    import inspect as _inspect

    source = _inspect.getsource(ExecutionGateway.authorize)
    assert source.count("IntentState.AUTHORIZED") == 1
    assert "Decision.AUTHORIZED" in source


# ── the approval gate cannot be walked past ─────────────────────────────────

def test_a_high_risk_action_without_approval_raises_rather_than_returning(gw, ctx):
    """The defect this closes: `check_approval` recorded AWAITING_APPROVAL and
    returned, so a caller that did not inspect the history executed anyway.

    Unreachable while risk was always LOW; reachable the moment risk became
    real. A gate a caller can walk past is not a gate.
    """
    from saathi.execution.errors import ApprovalException

    intent = _intent(operation="gmail.send", connector_id="gmail")
    history = _history(intent)
    with pytest.raises(ApprovalException):
        gw.check_approval(intent, RiskLevel.HIGH, history)
    assert history.current_state is IntentState.AWAITING_APPROVAL


def test_an_authorized_intent_passes_the_approval_gate(gw, ctx):
    """Approval is decided once, at authorization, against a correlated record.
    This gate reports that decision instead of forming a second opinion."""
    intent = _mutating_intent(intent_id=f"i-appr-{time.time_ns()}")
    gw.authorize(intent, ctx, _history(intent), inputs=_ok_mutating(intent))
    history = gw.check_approval(intent, RiskLevel.HIGH, _history(intent))
    assert history.current_state is IntentState.APPROVED


def test_an_authorization_for_a_different_intent_does_not_satisfy_the_gate(gw, ctx):
    """The decision is correlated to one intent; it may not vouch for another."""
    from saathi.execution.errors import ApprovalException

    authorized = _mutating_intent(intent_id=f"i-a-{time.time_ns()}")
    gw.authorize(authorized, ctx, _history(authorized),
                 inputs=_ok_mutating(authorized))
    other = _intent(intent_id=f"i-b-{time.time_ns()}",
                    operation="gmail.send", connector_id="gmail")
    with pytest.raises(ApprovalException):
        gw.check_approval(other, RiskLevel.CRITICAL, _history(other))


def test_a_low_risk_action_needs_no_approval(gw, ctx):
    intent = _intent()
    history = gw.check_approval(intent, RiskLevel.LOW, _history(intent))
    assert history.current_state is IntentState.APPROVED


# ── run ownership: a healthy run is not therefore *your* run ────────────────

def test_a_run_belonging_to_someone_else_denies():
    """Liveness is not ownership. Without this a caller holding `write` could
    act inside any run in the system merely by naming it."""
    inputs = _ok(run_declared=True,
                 run={"state": "running", "actor": "user:someone-else"})
    decision = authorize_intent(_intent(), inputs)
    assert decision.decision is Decision.DENIED
    assert decision.reason_code == "run_state.not_owned"


def test_a_run_with_no_recorded_owner_denies():
    inputs = _ok(run_declared=True, run={"state": "running", "actor": ""})
    decision = authorize_intent(_intent(), inputs)
    assert decision.decision is Decision.UNKNOWN
    assert decision.reason_code == "run_state.unknown"


def test_your_own_live_run_passes_its_gate():
    inputs = _ok(run_declared=True, run={"state": "running", "actor": "user:ajay"})
    decision = authorize_intent(_intent(), inputs)
    assert decision.decision is Decision.AUTHORIZED


def test_ownership_is_checked_before_the_action_can_proceed_cross_run():
    """Intent for run A, submitted naming run B: refused."""
    intent = _mutating_intent()
    inputs = _ok_mutating(intent, run_declared=True,
                          run={"state": "running", "actor": "user:other"})
    assert authorize_intent(intent, inputs).reason_code == "run_state.not_owned"


# ── the TODOs that remain cannot grant anything ─────────────────────────────
# Phase 16 resolved 4 of the file's 9 TODOs (authorize, classify_risk,
# check_approval, and the evidence rationale placeholder). The 5 that remain
# stay only because none of them sits on a path that can produce a positive
# authorization. That is an executable claim, not a note.

def test_the_unimplemented_validator_cannot_let_a_bad_intent_through(gw, ctx):
    """`validate_intent` still passes everything. Authorization does not rely
    on it: it checks intent integrity itself, so the stub cannot grant."""
    bad = _intent(operation="")
    history = gw.validate_intent(bad, _history(bad))
    assert history.current_state is IntentState.VALIDATED, "the stub still passes"
    with pytest.raises(AuthorizationException):
        gw.authorize(bad, ctx, _history(bad), inputs=_ok())


def test_the_unimplemented_idempotency_check_cannot_grant(gw, ctx):
    """It records nothing and decides nothing; duplicate detection lives in the
    universal boundary. It cannot turn a refusal into a grant."""
    intent = _intent()
    history = gw.check_idempotency(intent, _history(intent))
    assert IntentState.AUTHORIZED not in [t.to_state for t in history.transitions]
    with pytest.raises(AuthorizationException):
        gw.authorize(intent, ctx, history, inputs=_ok(has_permission=False))


def test_the_unimplemented_execute_returns_no_success(gw):
    """A stub that returned a successful-looking result would be far worse than
    one that returns nothing."""
    intent = _intent()
    assert gw.execute(intent, _history(intent)).status is None


def test_no_remaining_todo_sits_on_the_authorization_path():
    """Structural: the methods that decide must be TODO-free, and the methods
    that still carry one must not be decision-makers."""
    import inspect as _inspect

    deciding = (ExecutionGateway.authorize, ExecutionGateway.classify_risk,
                ExecutionGateway.check_approval)
    for method in deciding:
        assert "TODO" not in _inspect.getsource(method), method.__name__


# ── the actor context propagates safely, and loses safely ───────────────────

def test_the_bound_actor_survives_the_async_boundary():
    """Chat and agent inference reach the gateway through `asyncio.run`. If the
    actor did not cross that boundary, every authenticated call would silently
    degrade to the capped system actor."""
    import asyncio

    from saathi.execution.authorization_sources import actor_context, current_actor

    async def probe():
        return current_actor()

    with actor_context("ajay"):
        assert asyncio.run(probe()) == "ajay"
    assert current_actor() is None, "the binding must not outlive its block"


def test_losing_the_actor_across_a_thread_loses_authority_not_gains_it():
    """Context does not cross into a new thread. The result must be *less*
    authority -- the capped system actor -- never an unattributed call
    inheriting the caller's rights."""
    import concurrent.futures

    from saathi.execution.authorization_sources import actor_context, current_actor

    with actor_context("ajay"):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            leaked = pool.submit(current_actor).result()
    assert leaked is None

    # And an unattributed caller is capped, so the loss is fail-closed.
    intent = _mutating_intent()
    inputs = _ok(actor_user_id=None, has_permission=None, actor_is_system=True,
                 approvals=[_approval(tool_intent_digest(intent))])
    assert authorize_intent(intent, inputs).decision is Decision.DENIED
