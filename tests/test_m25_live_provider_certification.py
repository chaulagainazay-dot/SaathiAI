"""M25 — Live local provider certification harness (environment-aware)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.inference.live_cert_m25 import (
    VERDICT_CERTIFIED,
    VERDICT_ENV_BLOCKED,
    VERDICT_SECURITY_FAIL,
    decide_verdict,
    discover_environment,
    run_m25_certification,
)
from saathi.inference.release_check import run_release_check
from saathi.inference.runtime_gate import GateState, detect_live_provider_status, evaluate_runtime_gate

ROOT = Path(__file__).resolve().parents[1]


def test_discover_environment_is_read_only():
    env = discover_environment()
    assert env["install_performed"] is False
    assert env["service_started_by_m25"] is False
    assert env["models_pulled_by_m25"] is False
    assert env["operator_permission"]["auto_install"] is False
    assert env["operator_permission"]["auto_pull_models"] is False
    assert "endpoint" in env
    assert env["endpoint_allowlisted"] is True  # default loopback


def test_discover_detects_broken_or_missing_binary():
    env = discover_environment()
    # On this pilot host: broken symlink or absent — never claim installed without target
    if env.get("broken_symlink"):
        assert env["binary_present"] is False
        assert "ollama_broken_symlink" in env["blockers"]
    # Either way, if not present+reachable, live must be blocked
    if not env.get("runtime_reachable"):
        assert "ollama_runtime_unreachable" in env["blockers"] or not env.get("binary_present")


def test_run_certification_does_not_claim_live_when_blocked():
    report = run_m25_certification(write_evidence=True, starting_commit="e9571f3")
    d = report.to_dict()
    assert d["downloads_performed"] is False
    assert d["cloud_calls"] == 0
    assert d["cloud_fallback"] is False
    assert d["production_certified"] is False
    assert "UNENGAGED" in d["trading_guardian"]
    if not d["live"]:
        assert d["live_provider_certified"] is False
        assert d["verdict"] in {VERDICT_ENV_BLOCKED, VERDICT_SECURITY_FAIL}
        assert d["live_cases"] == [] or all(not c.get("ok") for c in d["live_cases"])
    # Never certify production without live
    if not d["live"]:
        assert d["production_certified"] is False


def test_evidence_bundle_written_and_privacy_safe():
    report = run_m25_certification(write_evidence=True)
    path = ROOT / "docs" / "evidence" / "m25" / "LIVE_CERT_EVIDENCE.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = path.read_text(encoding="utf-8")
    # Canary-like secrets should not appear from harness itself
    assert "sk-" not in raw
    assert "api_key" not in raw.lower() or "no_credentials" in raw.lower()
    assert data.get("production_certified") is False or data.get("live") is True
    assert data.get("schema") == "m25.live_cert_report.v1"


def test_decide_verdict_matrix():
    v, live_c, prod = decide_verdict(
        live=False,
        live_cases_ok=False,
        blockers=["ollama_runtime_unreachable"],
        security_fail=False,
        partial=False,
        production_gates_pass=False,
    )
    assert v == VERDICT_ENV_BLOCKED
    assert live_c is False and prod is False

    v2, live_c2, prod2 = decide_verdict(
        live=True,
        live_cases_ok=True,
        blockers=[],
        security_fail=False,
        partial=False,
        production_gates_pass=True,
    )
    assert v2 == VERDICT_CERTIFIED
    assert live_c2 and prod2

    v3, live_c3, prod3 = decide_verdict(
        live=False,
        live_cases_ok=False,
        blockers=[],
        security_fail=True,
        partial=False,
        production_gates_pass=False,
    )
    assert v3 == VERDICT_SECURITY_FAIL
    assert not prod3


def test_detect_live_provider_status_uses_m25():
    # Ensure evidence exists
    run_m25_certification(write_evidence=True)
    st = detect_live_provider_status()
    assert st["provider"] == "ollama"
    assert st["certification"] in {
        GateState.ENVIRONMENT_BLOCKED.value,
        GateState.NOT_TESTED.value,
        GateState.PASS.value,
    }
    # Without live cert, must not be PASS
    if not st.get("live_provider_certified"):
        assert st["certification"] != GateState.PASS.value


def test_runtime_gate_m25_checks():
    run_m25_certification(write_evidence=True)
    report = evaluate_runtime_gate()
    ids = {c.check_id: c for c in report.checks}
    assert "m25_live_provider_cert" in ids
    assert "m25_no_mock_as_live" in ids
    assert "m25_production_cert_invariant" in ids
    # production remains false on blocked host
    assert report.production_certified is False
    # no-mock gate must pass
    assert ids["m25_no_mock_as_live"].state is GateState.PASS
    assert ids["m25_production_cert_invariant"].state is GateState.PASS
    # live cert is ENVIRONMENT_BLOCKED when provider unavailable
    if not ids["m25_live_provider_cert"].evidence.get("live_provider_certified"):
        assert ids["m25_live_provider_cert"].state is GateState.ENVIRONMENT_BLOCKED


def test_release_check_still_passes():
    rep = run_release_check()
    assert rep.ok is True
    assert rep.production_certified is False


def test_mock_not_labeled_live_invariant():
    """Unit/injected success must never flip live_provider_certified without live flag."""
    report = run_m25_certification(write_evidence=False)
    if report.live is False:
        assert report.live_provider_certified is False
        assert report.production_certified is False


def test_residual_still_zero():
    data = json.loads(
        (ROOT / "docs" / "M21_3_RESIDUAL_EXCEPTION_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert data["exceptions"] == []
    assert data.get("production_certified") is False
