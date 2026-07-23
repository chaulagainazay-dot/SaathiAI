"""M49.2 subprocess cancellation helper and diag tool."""
from __future__ import annotations

import time

from saathi.tool_runtime.contracts import ToolExecutionRequest
from saathi.tool_runtime.durable_idempotency import DurableIdempotencyStore
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.tool_runtime.service import ToolExecutionService
from saathi.tool_runtime.subprocess_exec import SubprocessCancelState, run_bounded


def test_run_bounded_echo():
    r = run_bounded(["echo", "hello"], timeout_sec=5)
    assert r.ok
    assert "hello" in r.stdout
    assert r.cancel_state == SubprocessCancelState.COMPLETED
    assert r.cancellation_confirmed is False


def test_run_bounded_cancel_confirmed():
    # sleep then cancel immediately
    r = run_bounded(
        ["sleep", "30"],
        timeout_sec=30,
        cancel_check=lambda: True,
        grace_sec=0.5,
        allow_kill=True,
    )
    assert r.ok is False
    assert r.cancellation_confirmed is True
    assert r.cancel_state == SubprocessCancelState.PROCESS_EXIT_CONFIRMED


def test_run_bounded_timeout():
    r = run_bounded(
        ["sleep", "30"],
        timeout_sec=0.15,
        grace_sec=0.3,
        allow_kill=True,
    )
    assert r.timeout_detected is True
    assert r.ok is False


def test_shell_true_rejected():
    try:
        run_bounded(["echo", "x"], shell=True)
        assert False, "should raise"
    except ValueError as e:
        assert "shell" in str(e).lower()


def test_subprocess_diag_tool(tmp_path):
    svc = ToolExecutionService(
        registry=reset_registry_for_tests(),
        idempotency=DurableIdempotencyStore(tmp_path / "i.db"),
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.subprocess_diag",
            arguments={"kind": "echo_ok"},
        )
    )
    assert r.ok
    assert "m49.2-ok" in r.data.get("stdout", "")


def test_http_classify_ambiguous_mutation():
    from saathi.tool_runtime.http_cancel import HttpRequestPhase, classify_http_outcome

    out = classify_http_outcome(
        phase=HttpRequestPhase.REQUEST_SENT_NO_RESPONSE,
        side_effect_class="EXTERNAL_IRREVERSIBLE",
    )
    assert out["outcome_class"] == "SIDE_EFFECT_UNKNOWN"
    assert out["retryable"] is False
