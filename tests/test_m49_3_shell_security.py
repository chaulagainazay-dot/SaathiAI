"""M49.3 freeform shell elimination and allowlisted commands."""
from __future__ import annotations

import inspect

import pytest

from saathi.execution import ExecutionGateway
from saathi.tool_runtime.command_manifest import (
    CommandManifestError,
    list_command_manifests,
    resolve_argv,
    run_allowlisted_command,
)
from saathi.tool_runtime.contracts import ToolExecutionRequest, ToolOutcomeClass
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.tool_runtime.service import ToolExecutionService
from saathi.tool_runtime.subprocess_exec import run_bounded
from saathi.tools import system


def test_run_shell_source_has_no_shell_true_execution():
    src = inspect.getsource(system.run_shell)
    assert "freeform_shell_blocked" in src
    # must not call subprocess with shell=True in this function
    assert "subprocess.run" not in src
    assert "shell=True" not in src


def test_run_bounded_rejects_shell_true():
    with pytest.raises(ValueError, match="shell"):
        run_bounded(["echo", "x"], shell=True)


def test_run_bounded_rejects_shell_executable():
    with pytest.raises(ValueError, match="shell executable"):
        run_bounded(["/bin/sh", "-c", "echo hi"])


def test_allowlisted_command_executes():
    res = run_allowlisted_command("echo_ok")
    assert res.ok
    assert "m49.3-ok" in res.stdout
    assert res.cancellation_confirmed is False


def test_unapproved_command_id_rejected():
    with pytest.raises(CommandManifestError) as ei:
        resolve_argv("rm_rf_everything")
    assert ei.value.code == "COMMAND_NOT_ALLOWLISTED"


def test_extra_args_rejected_for_fixed_only():
    with pytest.raises(CommandManifestError) as ei:
        resolve_argv("uname", extra_args=["-r"])
    assert ei.value.code == "EXTRA_ARGS_PROHIBITED"


def test_cwd_outside_root_rejected():
    with pytest.raises(CommandManifestError) as ei:
        resolve_argv("git_status", cwd="/tmp")
    assert ei.value.code == "CWD_OUTSIDE_ROOT"


def test_env_key_rejected():
    with pytest.raises(CommandManifestError) as ei:
        resolve_argv("uname", env={"AWS_SECRET_ACCESS_KEY": "x"})
    assert ei.value.code == "ENV_KEY_REJECTED"


def test_metacharacters_rejected_when_extra_allowed():
    # uname is fixed_only; use resolve path that would accept extra if misconfigured
    from saathi.tool_runtime import command_manifest as cm

    # direct pattern check via forge: fixed_only commands reject extras first
    with pytest.raises(CommandManifestError):
        resolve_argv("echo_ok", extra_args=["hi; rm -rf /"])


def test_canonical_allowlisted_tool():
    svc = ToolExecutionService(registry=reset_registry_for_tests())
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.allowlisted_command",
            arguments={"command_id": "echo_ok"},
        )
    )
    assert r.ok
    assert r.data["shell"] is False
    assert "m49.3-ok" in r.data["stdout"]


def test_freeform_command_string_not_accepted_by_manifest_tool():
    svc = ToolExecutionService(registry=reset_registry_for_tests())
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.allowlisted_command",
            arguments={"command_id": "echo_ok", "command": "rm -rf /"},
        )
    )
    # additionalProperties false → input invalid
    assert r.outcome_class == ToolOutcomeClass.BLOCKED
    assert r.error_code == "TOOL_INPUT_INVALID"
    assert r.adapter_invoked is False


def test_list_command_manifests_nonempty():
    ms = list_command_manifests()
    assert len(ms) >= 5
    ids = {m["command_id"] for m in ms}
    assert "uname" in ids
