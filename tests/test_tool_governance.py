"""Tool-dispatch governance tests — proves the Governance Engine is the
mandatory gate inside execute_tool (SES-002, AP-14). Nothing bypasses it.

Registers throwaway handlers so we exercise the gate without real side effects.
"""
import pytest

from saathi.tools import registry
from saathi.tools.registry import execute_tool, recent_governance_decisions


@pytest.fixture(autouse=True)
def _reset_governance():
    # Fresh harness + audit log per test.
    registry._governance_harness = None
    registry._governance_audit.clear()
    yield


def _register(name, fn):
    registry._HANDLERS[name] = fn
    return name


def test_unverified_caller_blocked_on_destructive_tool():
    ran = {"n": 0}
    _register("delete_all_records", lambda **kw: ran.__setitem__("n", ran["n"] + 1) or {"ok": True})
    out = execute_tool("delete_all_records", {})
    assert out["error"] == "governance_denied"
    assert out["level"] == "L5"
    assert ran["n"] == 0                     # handler never ran
    del registry._HANDLERS["delete_all_records"]


@pytest.mark.parametrize("observed", [True, False, None])
def test_speaker_match_never_passes_destructive_tool(observed):
    """R2.1-S1: a voiceprint match is an observation, not an approval.

    This test previously asserted the opposite — that a "verified" speaker was
    treated as operator approval and the L5 handler ran. That was the authority
    forgery. No value of speaker_match_observed may unlock the handler now.
    """
    ran = {"n": 0}
    _register("delete_all_records2", lambda **kw: ran.__setitem__("n", ran["n"] + 1) or {"ok": True})
    out = execute_tool("delete_all_records2", {}, speaker_match_observed=observed)
    assert out["error"] == "governance_denied"
    assert out["level"] == "L5"
    assert ran["n"] == 0                     # handler never ran, for any observation
    del registry._HANDLERS["delete_all_records2"]


def test_speaker_match_never_selects_admin_identity():
    """The governance audit must record USER regardless of the observation."""
    _register("list_things_admin_probe", lambda **kw: {"items": []})
    for observed in (True, False, None):
        registry._governance_audit.clear()
        execute_tool("list_things_admin_probe", {}, speaker_match_observed=observed)
        audit = recent_governance_decisions()
        assert audit, "dispatch must be audited"
        assert audit[0]["who"] == "user", f"observation {observed!r} selected {audit[0]['who']}"
    del registry._HANDLERS["list_things_admin_probe"]


@pytest.mark.parametrize("observed", [True, False, None])
def test_no_privileged_tool_is_reachable_from_legacy_path(observed):
    """R2.1-S1: every PRIVILEGED tool fails closed, for every observation.

    Each is blocked either as an explicit approval requirement or by a stricter
    disposition (prohibited / deferred). What must never happen is the handler
    running, or a block that names speaker identity as the thing to fix.
    """
    ran = {"n": 0}
    for name in sorted(registry.PRIVILEGED):
        original = registry._HANDLERS.get(name)
        _register(name, lambda **kw: ran.__setitem__("n", ran["n"] + 1) or {"ok": True})
        try:
            out = execute_tool(name, {}, speaker_match_observed=observed)
        finally:
            if original is not None:
                registry._HANDLERS[name] = original
            else:
                del registry._HANDLERS[name]
        assert out.get("blocked") is True, f"{name} was not blocked"
        assert out.get("outcome_class") in {"BLOCKED", "PROHIBITED"}, \
            f"{name} not marked non-executable: {out.get('outcome_class')}"
        # The block must never be attributed to who the speaker is, nor hint
        # that re-verifying a voice would unlock it.
        blob = f"{out.get('error')} {out.get('message', '')}".lower()
        assert "speaker_not_verified" not in blob, f"{name}: identity-based denial"
        assert "verified voice" not in blob, f"{name}: offers voice re-verification"
        assert ran["n"] == 0, f"{name} handler executed"


def test_privileged_non_deferred_tool_states_approval_requirement():
    """A privileged tool with no stricter disposition must name the real fix."""
    from saathi.tool_runtime.legacy_policy import (
        LegacyDisposition, classify_legacy_tool,
    )
    candidates = [n for n in sorted(registry.PRIVILEGED)
                  if classify_legacy_tool(n) not in (
                      LegacyDisposition.PROHIBITED,
                      LegacyDisposition.DEFERRED_AND_DISABLED)]
    if not candidates:
        pytest.skip("every privileged tool currently carries a stricter disposition")
    ran = {"n": 0}
    name = candidates[0]
    original = registry._HANDLERS.get(name)
    _register(name, lambda **kw: ran.__setitem__("n", ran["n"] + 1) or {"ok": True})
    try:
        out = execute_tool(name, {}, speaker_match_observed=True)
    finally:
        if original is not None:
            registry._HANDLERS[name] = original
        else:
            del registry._HANDLERS[name]
    assert out["error"] == "approval_required"
    assert out["requires"] == "approval_reference+execution_gateway"
    assert ran["n"] == 0


def test_read_only_tool_is_governed_but_still_not_executed_here():
    """L0 clears governance — and still does not run on this path (R2.1-S2).

    Governance answers "is this action allowed?"; the gateway invariant answers
    "where may it run?". A read-only tool passes the first and is stopped by
    the second, because the legacy dispatcher never invokes a handler.
    """
    ran = {"n": 0}
    _register("read_status_x", lambda **kw: ran.__setitem__("n", ran["n"] + 1) or {"status": "ok"})
    try:
        out = execute_tool("read_status_x", {})
    finally:
        del registry._HANDLERS["read_status_x"]
    assert ran["n"] == 0
    assert out["error"] == "execution_gateway_required"
    assert out["blocked"] is True
    audit = recent_governance_decisions()
    assert audit and audit[0]["result"] == "allowed"   # L0 → governance allowed


def test_every_dispatch_is_audited():
    _register("list_things_y", lambda **kw: {"items": []})
    execute_tool("list_things_y", {})
    audit = recent_governance_decisions()
    assert audit and audit[0]["what"] == "list_things_y"
    assert audit[0]["result"] == "allowed"
    assert "risk" in audit[0] and "level" in audit[0]
    del registry._HANDLERS["list_things_y"]


def test_speaker_match_recorded_as_bounded_metadata():
    """The observation must survive into the L7 audit — as metadata only."""
    _register("list_things_meta", lambda **kw: {"items": []})
    for observed, expected in ((True, "true"), (False, "false"), (None, "unknown")):
        registry._governance_audit.clear()
        execute_tool("list_things_meta", {}, speaker_match_observed=observed)
        audit = recent_governance_decisions()
        assert f"speaker_match_observed={expected}" in audit[0]["why"]
    del registry._HANDLERS["list_things_meta"]


def test_speaker_verified_kwarg_is_gone():
    """The forged-authority parameter must not be silently accepted again."""
    _register("read_status_legacy", lambda **kw: {"status": "ok"})
    with pytest.raises(TypeError):
        execute_tool("read_status_legacy", {}, speaker_verified=True)
    del registry._HANDLERS["read_status_legacy"]


def test_unknown_tool_still_reported_before_gate():
    out = execute_tool("no_such_tool_zzz", {})
    assert "unknown tool" in out["error"]
