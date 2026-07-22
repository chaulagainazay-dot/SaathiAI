"""M39.2 — Failure-mode simulation tests (offline; SIMULATED_NOT_LIVE)."""
from __future__ import annotations

import json

import pytest

from saathi.credentials import m39_2 as m
from saathi.credentials.leakscan import is_clean
from saathi.credentials.m39 import M39Error

AUTHORITY_KEYS = (
    "production_authorization", "rollout_authorization", "CANARY_authorization",
    "ACTIVE_authorization", "write_authority",
)
EXPECTED_MODES = {
    "throttle_429", "auth_denied_401", "auth_denied_403", "server_error_500",
    "malformed_response", "network_timeout", "connection_reset",
    "connection_refused", "dns_resolution_failure", "secret_resolution_failure",
    "kill_switch_tripped",
}


def test_registry_covers_expected_modes():
    modes = {e[0] for e in m.FAULT_MODES}
    assert modes == EXPECTED_MODES


def test_matrix_verdict_all_fail_closed():
    mx = m.run_simulation_matrix()
    assert mx["verdict"] == "ALL_FAULTS_FAIL_CLOSED"
    inv = mx["invariants"]
    assert inv["all_faults_fail_closed"] is True
    assert inv["all_secret_handles_closed"] is True
    assert inv["all_retry_classifications_match"] is True
    assert inv["baseline_passes"] is True
    assert inv["no_live_network"] is True


def test_every_fault_fails_closed_and_no_live():
    mx = m.run_simulation_matrix()
    assert mx["fault_count"] == len(EXPECTED_MODES)
    for r in mx["results"]:
        assert r["status"] == "SIMULATED_NOT_LIVE"
        assert r["ok"] is False
        assert r["fails_closed"] is True
        assert r["live_network"] is False
        assert r["retry_matches_expected"] is True


@pytest.mark.parametrize("mode", sorted(EXPECTED_MODES))
def test_each_mode_individually(mode):
    r = m.simulate_fault(mode)
    assert r["mode"] == mode
    assert r["status"] == "SIMULATED_NOT_LIVE"
    assert r["ok"] is False and r["fails_closed"] is True
    assert r["contains_secret_values"] is False


def test_throttle_and_timeout_retryable():
    assert m.simulate_fault("throttle_429")["retryable"] is True
    assert m.simulate_fault("network_timeout")["retryable"] is True


def test_auth_denied_non_retryable():
    assert m.simulate_fault("auth_denied_401")["retryable"] is False
    assert m.simulate_fault("auth_denied_403")["retryable"] is False


def test_secret_resolution_failure_fails_closed_non_retryable():
    r = m.simulate_fault("secret_resolution_failure")
    assert r["ok"] is False and r["retryable"] is False
    assert r["handle_closed"] is True


def test_unknown_mode_raises():
    with pytest.raises(M39Error) as e:
        m.simulate_fault("meltdown")
    assert e.value.code == "unknown_fault_mode"


def test_authorities_never_granted():
    mx = m.run_simulation_matrix()
    for k in AUTHORITY_KEYS:
        assert mx["authorities"][k] == "NOT GRANTED"
    assert mx["trading_guardian"] == "UNENGAGED"


def test_matrix_deterministic_and_clean():
    a = m.run_simulation_matrix()
    b = m.run_simulation_matrix()
    assert a["fingerprint"] == b["fingerprint"]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert is_clean(a)


def test_no_secret_leaks_in_any_output():
    mx = m.run_simulation_matrix()
    blob = json.dumps(mx)
    assert "ghp_" not in blob
    assert is_clean(mx)


def test_evidence_emit(tmp_path):
    res = m.emit_m39_2_evidence(tmp_path)
    assert res["count"] == 2
    for p in res["written"]:
        assert is_clean(json.loads(open(p).read()))
