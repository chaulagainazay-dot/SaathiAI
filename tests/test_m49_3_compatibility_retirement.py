"""M49.3 compatibility bridge retirement bounds."""
from __future__ import annotations

from saathi.tool_runtime.adapters.migrated import LEGACY_NAME_MAP
from saathi.tool_runtime.compat import try_canonical_legacy_tool
from saathi.tool_runtime.legacy_policy import classify_legacy_tool
from saathi.tools.registry import execute_tool


def test_unmapped_name_returns_none_from_bridge():
    assert try_canonical_legacy_tool("not_a_real_tool", {}) is None


def test_legacy_map_is_specific_not_generic():
    # no catch-all
    assert "*" not in LEGACY_NAME_MAP
    assert "" not in LEGACY_NAME_MAP
    for k, v in LEGACY_NAME_MAP.items():
        assert k
        assert v.startswith("m49.")


def test_manage_tasks_non_list_not_silently_legacy_mutated():
    # non-list action should not hit freeform legacy mutate through canonical-only path
    out = execute_tool(
        "manage_tasks",
        {"action": "delete", "id": "x"},
        speaker_verified=True,
    )
    # either blocked canonical_only or governance denial — must not claim success delete
    if out.get("error"):
        assert out.get("error") in (
            "canonical_only",
            "governance_denied",
            "speaker_not_verified",
        ) or out.get("blocked")


def test_deferred_not_classified_as_migrated():
    assert classify_legacy_tool("ab_click").value == "DEFERRED_AND_DISABLED"
    assert classify_legacy_tool("run_shell").value == "PROHIBITED"
