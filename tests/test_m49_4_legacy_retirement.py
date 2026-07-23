"""M49.4 legacy residual proofs — deferred/prohibited unreachable; bounded retained."""
from __future__ import annotations

from saathi.tool_runtime.legacy_policy import (
    CANONICAL_LEGACY_MAP,
    DEFERRED_RUNTIME_TOOLS,
    FREEFORM_SHELL_TOOLS,
    LEGACY_BOUNDED_TOOLS,
    classify_legacy_tool,
    is_runtime_executable,
)
from saathi.tools.registry import _HANDLERS, execute_tool


def test_handler_count_stable():
    assert len(_HANDLERS) == 120


def test_every_handler_has_explicit_policy_set():
    for name in _HANDLERS:
        sets = (
            name in CANONICAL_LEGACY_MAP
            or name in DEFERRED_RUNTIME_TOOLS
            or name in LEGACY_BOUNDED_TOOLS
            or name in FREEFORM_SHELL_TOOLS
        )
        assert sets, f"handler {name} missing explicit policy classification"


def test_deferred_not_runtime_executable():
    for name in sorted(DEFERRED_RUNTIME_TOOLS):
        if name not in _HANDLERS:
            continue
        assert not is_runtime_executable(name)
        out = execute_tool(name, {}, speaker_verified=True)
        assert out.get("blocked") is True
        assert out.get("disposition") == "DEFERRED_AND_DISABLED"


def test_freeform_shell_not_runtime_executable():
    for name in FREEFORM_SHELL_TOOLS:
        assert classify_legacy_tool(name).value == "PROHIBITED"
        assert not is_runtime_executable(name)
        out = execute_tool(name, {"command": "ls", "script": "ls", "name": "x"}, speaker_verified=True)
        assert out.get("blocked") is True


def test_canonical_mapped_route_or_block_not_raw_legacy_mutate():
    # manage_tasks non-list must not mutate via legacy
    out = execute_tool("manage_tasks", {"action": "complete", "id": "1"}, speaker_verified=True)
    assert out.get("error") in ("canonical_only", "governance_denied") or out.get("blocked") is True


def test_send_email_requires_approval_on_bridge():
    out = execute_tool(
        "send_email",
        {"to": "nobody@example.com", "subject": "t", "body": "b"},
        speaker_verified=True,
    )
    # Must not claim live send succeeded
    assert out.get("sent") is not True
    assert (
        out.get("error") in ("approval_required", "governance_denied", "canonical_rejected")
        or out.get("outcome_class") in ("BLOCKED", "PROHIBITED")
        or out.get("blocked") is True
        or out.get("dry_run_only") is True
    )


def test_legacy_bounded_stamped_when_executed():
    # canteen_query is inventory LEGACY_BOUNDED — if governance allows, stamp present
    out = execute_tool("canteen_query", {"query": "hours"}, speaker_verified=True)
    if not out.get("error") and not out.get("blocked"):
        assert out.get("_legacy_bounded") is True or out.get("_disposition") == "LEGACY_BOUNDED"


def test_unknown_name_rejected_no_generic_fallback():
    out = execute_tool("m49_4_totally_fake_tool", {}, speaker_verified=True)
    assert out.get("blocked") is True
    assert "unknown tool" in out.get("error", "")
