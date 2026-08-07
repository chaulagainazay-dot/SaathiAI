"""M49.3 domain boundaries: browser, engineering, voice, IELTS, deploy."""
from __future__ import annotations

from saathi.tool_runtime.legacy_policy import classify_legacy_tool
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.tools.registry import execute_tool


def test_browser_mutation_tools_deferred():
    for name in ("ab_click", "ab_fill", "ab_goto", "ab_open"):
        assert classify_legacy_tool(name).value == "DEFERRED_AND_DISABLED"
        out = execute_tool(name, {}, speaker_verified=True)
        assert out.get("blocked") is True


def test_browser_inspect_fixture_canonical():
    reg = reset_registry_for_tests()
    m = reg.get_manifest("m49.connector.browser.inspect_page")
    assert m is not None
    assert m.authority_class.value == "READ_ONLY"


def test_mac_control_deferred():
    for name in ("mac_open_app", "mac_type_text", "look_at_screen"):
        assert classify_legacy_tool(name).value == "DEFERRED_AND_DISABLED"


def test_deployment_deferred():
    for name in ("deploy_ielts_site", "publish_to_youtube", "publish_blog"):
        assert classify_legacy_tool(name).value == "DEFERRED_AND_DISABLED"
        out = execute_tool(name, {}, speaker_verified=True)
        assert out.get("blocked") is True


def test_engineering_project_run_prohibited():
    assert classify_legacy_tool("project_run").value == "PROHIBITED"
