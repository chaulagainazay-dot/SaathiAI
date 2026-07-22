"""M38 — Retry policy, failure injection, canary readiness, CLI secrets (offline)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.credentials.leakscan import is_clean
from saathi.credentials.m36 import M36Error as M36E, reject_forbidden_cli_argv
from saathi.credentials.m38 import (
    M38Error,
    RetryClass,
    RetryPolicy,
    CanaryReadinessVerdict,
    classify_retry,
    evaluate_canary_readiness,
    run_retry_matrix,
    run_failure_injection_matrix,
    run_m38_validation,
    write_m38_evidence,
    preflight_summary,
    validation_summary_body,
    compute_m38_fingerprint,
    AUTHORITIES,
    SYNTH_SECRET,
)


def test_retry_classification_retryable():
    for r in ("timeout", "http_429", "http_500", "http_503", "connection_refused"):
        assert classify_retry(r) == RetryClass.RETRYABLE.value, r


def test_retry_classification_non_retryable():
    for r in ("http_401", "http_403", "secret_empty", "authorization_expired", "concurrency_limit"):
        assert classify_retry(r) == RetryClass.NON_RETRYABLE.value, r


def test_retry_schedule_deterministic():
    p = RetryPolicy()
    assert [p.delay_ms(i) for i in range(3)] == [50, 100, 200]


def test_retry_exhausted():
    p = RetryPolicy(max_attempts=2)
    with pytest.raises(M38Error) as e:
        p.delay_ms(2)
    assert e.value.code == "retry_exhausted"


def test_retry_after_bounded():
    p = RetryPolicy(max_retry_after_ms=1000)
    assert p.delay_ms(0, retry_after_ms=99999) == 1000


def test_retry_matrix_all_pass():
    rep = run_retry_matrix()
    assert rep["failed"] == 0, json.dumps([c for c in rep["cases"] if not c.get("pass")], indent=2)


def test_failure_injection_matrix():
    rep = run_failure_injection_matrix()
    assert rep["failed"] == 0, json.dumps([c for c in rep["cases"] if not c.get("pass")], indent=2)
    assert all(c.get("handle_closed", True) for c in rep["cases"] if "handle_closed" in c)
    assert is_clean(rep)


def test_canary_no_live_is_limited_or_blocked():
    v = evaluate_canary_readiness(
        multi_session={"failed": 0},
        retry_matrix={"failed": 0},
        recovery_matrix={"failed": 0},
        failure_injection={"failed": 0},
        m37_ok=True,
        leak_clean=True,
        live_sandbox_exercised=False,
        evidence_complete=True,
    )
    assert v["grants_canary"] is False
    assert v["grants_active"] is False
    assert v["verdict"] in (
        CanaryReadinessVerdict.READY_WITH_LIMITATIONS.value,
        CanaryReadinessVerdict.BLOCKED_LIVE_VALIDATION_REQUIRED.value,
    )
    assert "live_sandbox_session_not_exercised" in v["limitations"]


def test_canary_not_ready_on_technical_failure():
    v = evaluate_canary_readiness(
        multi_session={"failed": 1},
        retry_matrix={"failed": 0},
        recovery_matrix={"failed": 0},
        failure_injection={"failed": 0},
        m37_ok=True,
        leak_clean=True,
        live_sandbox_exercised=False,
    )
    assert v["verdict"] == CanaryReadinessVerdict.NOT_READY.value


def test_canary_never_grants_even_with_live():
    v = evaluate_canary_readiness(
        multi_session={"failed": 0},
        retry_matrix={"failed": 0},
        recovery_matrix={"failed": 0},
        failure_injection={"failed": 0},
        m37_ok=True,
        leak_clean=True,
        live_sandbox_exercised=True,
        evidence_complete=True,
    )
    assert v["grants_canary"] is False
    assert v["verdict"] == CanaryReadinessVerdict.READY_FOR_OPERATOR_REVIEW.value


def test_full_m38_validation():
    result = run_m38_validation(live_exercised=False)
    assert result["ok"] is True, json.dumps({
        "multi": result["multi_session"].get("failed"),
        "retry": result["retry"].get("failed"),
        "recovery": result["recovery"].get("failed"),
        "failure": result["failure_injection"].get("failed"),
        "m37": result["m37_regression_ok"],
    })
    assert result["m39_started"] is False
    assert result["authorities"] == AUTHORITIES
    assert result["canary_readiness"]["grants_canary"] is False
    assert is_clean(result)
    assert SYNTH_SECRET not in json.dumps(result)


def test_evidence_write(tmp_path):
    result = run_m38_validation(live_exercised=False)
    bodies = {
        "baseline": {"milestone": "M38", "live": False, "fingerprint": compute_m38_fingerprint()},
        "validation_summary": validation_summary_body(result),
        "canary_readiness_evaluation": result["canary_readiness"],
        "authority_state": dict(AUTHORITIES),
        "leak_scan": {"clean": True, "findings": []},
        "verification_fingerprint": {"fingerprint": compute_m38_fingerprint()},
    }
    written = write_m38_evidence(bodies, evidence_dir=str(tmp_path))
    assert len(written) == len(bodies)
    for p in Path(tmp_path).iterdir():
        assert SYNTH_SECRET not in p.read_text()


def test_preflight():
    p = preflight_summary()
    assert p["milestone"] == "M38"
    assert p["grants_canary"] is False
    assert p["m39_started"] is False


@pytest.mark.parametrize("flag", ["--token", "--api-key", "--secret", "--password"])
def test_cli_rejects_raw_secrets(flag):
    with pytest.raises(M36E):
        reject_forbidden_cli_argv([flag, "x"])


def test_fingerprint_deterministic():
    assert compute_m38_fingerprint() == compute_m38_fingerprint()
