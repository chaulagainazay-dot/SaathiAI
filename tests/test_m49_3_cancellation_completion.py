"""M49.3 cancellation completion matrix and subprocess honesty."""
from __future__ import annotations

import threading
import time

from saathi.tool_runtime.contracts import (
    ToolCancellationSupport,
    ToolExecutionRequest,
    ToolOutcomeClass,
)
from saathi.tool_runtime.gateway_audit import audit_cancellation
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.tool_runtime.service import ToolExecutionService
from saathi.tool_runtime.subprocess_exec import SubprocessCancelState, run_bounded
from saathi.tool_runtime.http_cancel import HttpRequestPhase, classify_http_outcome


def test_no_unknown_cancellation_on_supported_tools():
    reset_registry_for_tests()
    report = audit_cancellation()
    assert report["unknown_count"] == 0
    assert report["status"] == "PASS"
    assert report["supported_count"] >= 10


def test_allowlisted_command_hard_cancel_class():
    reg = reset_registry_for_tests()
    m = reg.get_manifest("m49.allowlisted_command")
    assert m is not None
    assert m.cancellation_support == ToolCancellationSupport.HARD_CANCEL_SUPPORTED


def test_subprocess_cancel_confirms_exit():
    flag = {"c": False}

    def cancel():
        return flag["c"]

    def arm():
        time.sleep(0.05)
        flag["c"] = True

    t = threading.Thread(target=arm)
    t.start()
    res = run_bounded(
        ["python3", "-c", "import time; time.sleep(5)"],
        timeout_sec=10,
        cancel_check=cancel,
        grace_sec=0.5,
        allow_kill=True,
    )
    t.join()
    assert res.cancellation_confirmed is True
    assert res.cancel_state == SubprocessCancelState.PROCESS_EXIT_CONFIRMED
    # must not report success
    assert res.ok is False


def test_timeout_not_reported_as_user_cancel():
    res = run_bounded(
        ["python3", "-c", "import time; time.sleep(5)"],
        timeout_sec=0.15,
        grace_sec=0.3,
        allow_kill=True,
    )
    assert res.timeout_detected is True
    assert res.cancellation_confirmed is False


def test_cooperative_cancel_tool():
    svc = ToolExecutionService(registry=reset_registry_for_tests())
    cancelled = {"v": False}

    def chk():
        return cancelled["v"]

    def arm():
        time.sleep(0.02)
        cancelled["v"] = True

    t = threading.Thread(target=arm)
    t.start()
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.cooperative_cancel",
            arguments={"stages": 50},
        ),
        cancel_check=chk,
    )
    t.join()
    assert r.outcome_class == ToolOutcomeClass.CANCELLED_CONFIRMED
    assert r.cancellation_confirmed is True


def test_http_ambiguous_mutation_not_retryable():
    out = classify_http_outcome(
        phase=HttpRequestPhase.BODY_SENT,
        side_effect_class="EXTERNAL_IRREVERSIBLE",
        cancelled=False,
    )
    assert out["outcome_class"] == "SIDE_EFFECT_UNKNOWN"
    assert out["retryable"] is False


def test_http_cancel_before_send_confirmed():
    out = classify_http_outcome(
        phase=HttpRequestPhase.NOT_STARTED,
        side_effect_class="EXTERNAL_IRREVERSIBLE",
        cancelled=True,
    )
    assert out["outcome_class"] == "CANCELLED_CONFIRMED"
