"""M39.1 — Operator dry-run tooling tests (offline; deterministic; no secret)."""
from __future__ import annotations

import json

import pytest

from saathi.credentials import m39_1 as m
from saathi.credentials.leakscan import is_clean
from saathi.credentials.m39 import M39Error

RAW_TOKEN = "ghp_abcdefghijklmnopqrstuvwxyz12"  # synthetic fixture, never a real secret
AUTHORITY_KEYS = (
    "production_authorization",
    "rollout_authorization",
    "CANARY_authorization",
    "ACTIVE_authorization",
    "write_authority",
)


def _assert_no_grant(body: dict) -> None:
    auth = body.get("authorities", {})
    for k in AUTHORITY_KEYS:
        assert auth.get(k) == "NOT GRANTED", f"{k} must be NOT GRANTED"
    assert body.get("contains_secret_values") is False


# ── execution plan ───────────────────────────────────────────────────────────
def test_plan_valid_single():
    p = m.build_execution_plan(mode="single", locator="svc:acct")
    assert p["plan_valid"] is True and p["problems"] == []
    assert p["provider"] == "github_meta"
    assert p["operations"]["read_only"] is True and p["operations"]["writes"] == []
    assert p["live_outcomes"]["single_session"] == "NOT_EXERCISED"
    _assert_no_grant(p)


def test_plan_deterministic_and_fingerprinted():
    a = m.build_execution_plan(mode="multi", concurrency=2, locator="svc:acct")
    b = m.build_execution_plan(mode="multi", concurrency=2, locator="svc:acct")
    assert a == b
    assert a["fingerprint"] == b["fingerprint"] and len(a["fingerprint"]) == 24


def test_plan_rejects_bad_endpoint_and_budget():
    p = m.build_execution_plan(endpoints=("/repos",), locator="svc:acct")
    assert p["plan_valid"] is False and "endpoint_not_allowlisted" in p["problems"]
    p2 = m.build_execution_plan(per_session_budget=99, locator="svc:acct")
    assert "invalid_per_session_budget" in p2["problems"]


def test_plan_single_mode_concurrency_capped():
    p = m.build_execution_plan(mode="single", concurrency=2, locator="svc:acct")
    assert "invalid_concurrency" in p["problems"]


def test_plan_invalid_mode_raises():
    with pytest.raises(M39Error) as e:
        m.build_execution_plan(mode="canary")
    assert e.value.code == "invalid_plan_mode"


def test_plan_rejects_raw_locator():
    with pytest.raises(M39Error) as e:
        m.build_execution_plan(locator=RAW_TOKEN)
    assert e.value.code == "raw_secret_locator_rejected"


def test_plan_rejects_raw_env_var_name():
    with pytest.raises(M39Error):
        m.build_execution_plan(source_kind="ENV_REFERENCE", env_var_name=RAW_TOKEN)


def test_plan_unapproved_backend_flagged():
    p = m.build_execution_plan(source_kind="S3_URL", locator="svc")
    assert "unapproved_secret_backend" in p["problems"]


# ── command preview ──────────────────────────────────────────────────────────
def test_preview_contains_no_secret_and_has_fingerprint():
    p = m.build_execution_plan(mode="single", locator="svc:acct")
    text = m.render_command_preview(p)
    assert RAW_TOKEN not in text
    assert "<REFERENCE>" in text
    assert p["secret_reference"]["locator_fingerprint"] in text
    assert "m39-run-live-single-session" in text
    assert "NOT GRANTED" in text


def test_preview_multi_mode_uses_multisession_cmd():
    p = m.build_execution_plan(mode="multi", concurrency=2, locator="svc:acct")
    assert "m39-run-live-multisession" in m.render_command_preview(p)


def test_preview_rejects_non_plan():
    with pytest.raises(M39Error):
        m.render_command_preview({"kind": "not_a_plan"})


# ── backend availability ─────────────────────────────────────────────────────
def test_availability_unapproved():
    r = m.check_backend_availability(source_kind="FORBIDDEN")
    assert r["available"] == "UNAVAILABLE" and r["ready"] is False
    _assert_no_grant(r)


def test_availability_encrypted_store_blocks_on_operator():
    r = m.check_backend_availability(source_kind="ENCRYPTED_STORE_REFERENCE")
    assert r["available"] == "BLOCKED_OPERATOR_ACTION_REQUIRED"
    assert r["reason"] == "encrypted_store_requires_operator_wiring"


def test_availability_in_memory_is_simulated():
    r = m.check_backend_availability(source_kind="IN_MEMORY_TEST")
    assert r["available"] == "SIMULATED_NOT_LIVE" and r["ready"] is False


def test_availability_env_reference_missing_is_unavailable():
    r = m.check_backend_availability(
        source_kind="ENV_REFERENCE", env_var_name="SAATHI_DEFINITELY_MISSING_M391",
        environ={},
    )
    assert r["available"] in ("UNAVAILABLE", "UNKNOWN") and r["ready"] is False
    assert r["resolves_plaintext"] is False


def test_availability_env_reference_present_does_not_leak_value():
    r = m.check_backend_availability(
        source_kind="ENV_REFERENCE", env_var_name="SAATHI_M391_PRESENT",
        environ={"SAATHI_M391_PRESENT": RAW_TOKEN},
    )
    # present reference → AVAILABLE, but the value must never appear in output
    assert r["available"] == "AVAILABLE" and r["ready"] is True
    assert RAW_TOKEN not in json.dumps(r)
    assert is_clean(r)


def test_availability_rejects_raw_locator():
    with pytest.raises(M39Error):
        m.check_backend_availability(source_kind="OS_KEYCHAIN_REFERENCE", locator=RAW_TOKEN)


# ── revocation checklist ─────────────────────────────────────────────────────
def test_checklist_steps_and_state():
    c = m.generate_revocation_checklist(locator="svc:acct")
    ids = [s["id"] for s in c["steps"]]
    assert ids == ["REV-1", "REV-2", "REV-3", "REV-4", "REV-5"]
    assert c["current_state"]["external_credential_revocation"] == "NOT_EXERCISED"
    _assert_no_grant(c)
    assert is_clean(c)


def test_checklist_rejects_bad_provider():
    with pytest.raises(M39Error) as e:
        m.generate_revocation_checklist(provider="stripe")
    assert e.value.code == "provider_not_allowlisted"


def test_checklist_rejects_raw_locator():
    with pytest.raises(M39Error):
        m.generate_revocation_checklist(locator=RAW_TOKEN)


def test_checklist_render_has_no_secret():
    c = m.generate_revocation_checklist(locator="svc:acct")
    text = m.render_revocation_checklist(c)
    assert "REV-1" in text and RAW_TOKEN not in text


# ── diagnostics ──────────────────────────────────────────────────────────────
def test_diagnostics_redacted_and_flags():
    d = m.collect_offline_diagnostics(environ={})
    assert d["flags"]["live_flag_set"] is False
    assert d["flags"]["kill_switch_active"] is False
    assert d["live_state"]["single_session"] == "NOT_EXERCISED"
    _assert_no_grant(d)
    assert is_clean(d)


def test_diagnostics_reflect_live_flag():
    d = m.collect_offline_diagnostics(
        environ={"SAATHI_M39_ALLOW_LIVE_SANDBOX_VALIDATION": "1"}
    )
    assert d["flags"]["live_flag_set"] is True


# ── evidence ─────────────────────────────────────────────────────────────────
def test_evidence_deterministic_and_clean():
    a = m.build_m39_1_evidence()
    b = m.build_m39_1_evidence()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    for name, body in a.items():
        assert is_clean(body), name
    assert a["summary"]["verdict"] == "OFFLINE_OPERATOR_TOOLING_COMPLETE"
    assert a["summary"]["live_state"] == "NOT_EXERCISED"
    _assert_no_grant(a["summary"])


def test_evidence_emit_writes_files(tmp_path):
    res = m.emit_m39_1_evidence(tmp_path)
    assert res["count"] == 7
    for path in res["written"]:
        assert is_clean(json.loads(open(path).read()))
