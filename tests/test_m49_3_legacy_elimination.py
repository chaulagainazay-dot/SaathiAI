"""M49.3 legacy path elimination and policy enforcement."""
from __future__ import annotations

from saathi.tool_runtime.legacy_policy import (
    FREEFORM_SHELL_TOOLS,
    classify_legacy_tool,
    is_runtime_executable,
)
from saathi.tools.registry import execute_tool


def test_freeform_shell_tools_prohibited():
    for name in FREEFORM_SHELL_TOOLS:
        assert classify_legacy_tool(name).value == "PROHIBITED"
        assert not is_runtime_executable(name)


def test_run_shell_blocked_via_execute_tool():
    out = execute_tool("run_shell", {"command": "ls -la"}, speaker_verified=True)
    assert out.get("blocked") is True
    assert out.get("error") in ("freeform_shell_blocked", "tool_prohibited")
    assert "stdout" not in out or out.get("command_rejected")


def test_project_run_blocked_via_execute_tool():
    out = execute_tool(
        "project_run",
        {"name": "x", "command": "echo hi"},
        speaker_verified=True,
    )
    assert out.get("blocked") is True


def test_applescript_blocked():
    out = execute_tool(
        "applescript", {"script": 'display dialog "x"'}, speaker_verified=True
    )
    assert out.get("blocked") is True


def test_unknown_tool_no_generic_fallback():
    out = execute_tool("totally_unknown_tool_xyz", {}, speaker_verified=True)
    assert "unknown tool" in out.get("error", "")
    assert out.get("blocked") is True


def test_deferred_browser_disabled():
    out = execute_tool("ab_goto", {"url": "https://example.com"}, speaker_verified=True)
    assert out.get("blocked") is True
    assert out.get("disposition") == "DEFERRED_AND_DISABLED"


def test_deferred_deploy_disabled():
    out = execute_tool("deploy_ielts_site", {}, speaker_verified=True)
    assert out.get("blocked") is True


def test_supported_legacy_routes_through_gateway():
    out = execute_tool("system_health", {}, speaker_verified=True)
    assert out.get("error") != "unknown tool"
    if "error" not in out:
        assert "_canonical_tool_id" in out or "health" in out


def test_manage_tasks_list_canonical():
    out = execute_tool("manage_tasks", {"action": "list"}, speaker_verified=True)
    if "error" not in out:
        assert "_canonical_tool_id" in out or "open_tasks" in out
