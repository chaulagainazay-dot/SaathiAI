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
    out = execute_tool("delete_all_records", {}, speaker_verified=False)
    assert out["error"] == "governance_denied"
    assert out["level"] == "L5"
    assert ran["n"] == 0                     # handler never ran
    del registry._HANDLERS["delete_all_records"]


def test_verified_operator_passes_destructive_tool():
    ran = {"n": 0}
    _register("delete_all_records2", lambda **kw: ran.__setitem__("n", ran["n"] + 1) or {"ok": True})
    out = execute_tool("delete_all_records2", {}, speaker_verified=True)
    assert out == {"ok": True}               # verified voice = operator approval
    assert ran["n"] == 1
    del registry._HANDLERS["delete_all_records2"]


def test_read_only_tool_passes_for_anyone():
    _register("read_status_x", lambda **kw: {"status": "ok"})
    out = execute_tool("read_status_x", {}, speaker_verified=False)
    assert out == {"status": "ok"}           # L0 → automatic
    del registry._HANDLERS["read_status_x"]


def test_every_dispatch_is_audited():
    _register("list_things_y", lambda **kw: {"items": []})
    execute_tool("list_things_y", {}, speaker_verified=False)
    audit = recent_governance_decisions()
    assert audit and audit[0]["what"] == "list_things_y"
    assert audit[0]["result"] == "allowed"
    assert "risk" in audit[0] and "level" in audit[0]
    del registry._HANDLERS["list_things_y"]


def test_unknown_tool_still_reported_before_gate():
    out = execute_tool("no_such_tool_zzz", {}, speaker_verified=False)
    assert "unknown tool" in out["error"]
