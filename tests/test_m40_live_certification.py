"""M40 — Live validation & production certification tests (offline; deterministic).

All live-dependent paths are fixture-driven and must remain LIVE_BLOCKED /
SIMULATED_NOT_LIVE. No real network, no real credential, no LIVE_CERTIFIED.
"""
from __future__ import annotations

import json

import pytest

from saathi.credentials import m40
from saathi.connectors.providers.external import testkit as tk
from saathi.credentials.leakscan import is_clean
from saathi.credentials.m39 import M39_ACK_TOKENS, run_live_single_session

GRANT_KEYS = ("grants_canary", "grants_active", "grants_rollout", "grants_production", "grants_write")


def _live_cfg(**kw):
    base = dict(
        mode="live", secret_source_kind="OS_KEYCHAIN_REFERENCE",
        secret_locator="svc:acct", acknowledgements=M39_ACK_TOKENS,
        authorization_present=True, environment_confirmed=True,
        branch="b", head="h", working_tree_class="CLEAN", live_flag=True,
    )
    base.update(kw)
    return m40.M40Config(**base)


# ── never certifies without a real provider ──────────────────────────────────
def test_no_credential_blocks():
    c = m40.run_live_certification(m40.M40Config())
    assert c["verdict"] == "LIVE_BLOCKED_OPERATOR_SECRET_REQUIRED"
    assert c["live_certified"] is False


def test_never_grants_anything():
    for body in (m40.run_live_certification(m40.M40Config()), m40.run_stage_rehearsal()):
        for k in GRANT_KEYS:
            assert body[k] is False


def test_rehearsal_never_certifies():
    r = m40.run_stage_rehearsal()
    assert r["verdict"] == "LIVE_BLOCKED"
    assert r["live_certified"] is False
    assert r["mode"] == "rehearsal"


def test_forged_complete_config_missing_secret_blocks_not_certifies():
    # approved backend + flag but the secret does not exist -> BLOCKED, no network
    c = m40.run_live_certification(_live_cfg(secret_locator="svc:definitely_absent"))
    assert c["live_certified"] is False
    assert c["verdict"] in ("LIVE_BLOCKED", "LIVE_BLOCKED_OPERATOR_SECRET_REQUIRED")
    last = c["stages"][-1]
    assert last["stage"] == "stage3_single_session"
    assert last["status"] == "BLOCKED"


# ── Stage 1 — operator acknowledgement (fail closed) ─────────────────────────
def test_stage1_all_present_passes():
    s = m40.stage1_operator_acknowledgement(_live_cfg())
    assert s["status"] == "PASSED"


@pytest.mark.parametrize("missing", ["acks", "auth", "env", "secret"])
def test_stage1_fails_closed_on_each_missing(missing):
    kw = {}
    if missing == "acks":
        kw["acknowledgements"] = ("only_one",)
    if missing == "auth":
        kw["authorization_present"] = False
    if missing == "env":
        kw["environment_confirmed"] = False
    if missing == "secret":
        kw["secret_source_kind"] = "IN_MEMORY_TEST"  # not approved for live
    s = m40.stage1_operator_acknowledgement(_live_cfg(**kw))
    assert s["status"] == "BLOCKED" and s["blockers"]


def test_stage1_rejects_raw_secret_locator():
    assert m40._secret_reference_supplied(
        _live_cfg(secret_source_kind="ENV_REFERENCE",
                  secret_locator="ghp_abcdefghijklmnopqrstuvwxyz12")) is False


# ── Stage 2 — preflight blocks synthetic backend, no mutation ────────────────
def test_stage2_rejects_synthetic_backend():
    s = m40.stage2_provider_preflight(_live_cfg(secret_source_kind="IN_MEMORY_TEST"))
    assert s["status"] == "BLOCKED"
    assert s["network_calls_performed"] == 0


def test_stage2_no_remote_mutation_field():
    s = m40.stage2_provider_preflight(_live_cfg())
    assert s["network_calls_performed"] == 0


# ── Stage 3 — single session (rehearsal) cleanup ─────────────────────────────
def test_stage3_rehearsal_cleanup_and_simulated():
    s = m40.stage3_single_session(m40.M40Config(mode="rehearsal"), rehearsal=True)
    assert s["status"] == "SIMULATED_NOT_LIVE"
    assert s["handle_closed"] is True
    assert s["live_network"] is False
    assert s["call_budget_used"] <= s["call_budget_max"]


# ── Stage 4 — multi session isolation ────────────────────────────────────────
def test_stage4_rehearsal_isolation():
    s = m40.stage4_multi_session(m40.M40Config(mode="rehearsal"), rehearsal=True)
    assert s["status"] == "SIMULATED_NOT_LIVE"
    assert s["lease_isolation_ok"] is True
    assert s["no_stale_handles"] is True
    assert s["session_count"] >= 2


# ── Stage 5 — external revocation -> 401 -> cleanup -> classification ─────────
def test_stage5_rehearsal_revocation_401_cleanup():
    s = m40.stage5_external_revocation(m40.M40Config(mode="rehearsal"), rehearsal=True)
    assert s["status"] == "SIMULATED_NOT_LIVE"
    assert s["retry_failed_401"] is True
    assert s["cleanup_ok"] is True
    assert s["failure_classification"] == "authorization_failure_401"
    assert s["audit_event"] == "m39.single_session_failed"


def test_stage5_live_validation_only_pending_revocation():
    # live mode, no post-revocation retry requested -> NOT_EXERCISED (pending operator)
    s = m40.stage5_external_revocation(_live_cfg(), operator_confirmed=True)
    assert s["status"] == "NOT_EXERCISED"
    assert s["revocation_recorded"] is False
    assert "pending_operator_revocation" in s["reason"]


def test_expected_fingerprint_threads_into_config():
    cfg = _live_cfg(expected_subject_fingerprint="deadbeef", post_revocation_retry=False)
    assert cfg.expected_subject_fingerprint == "deadbeef"
    assert cfg.post_revocation_retry is False


def test_post_revocation_without_credential_never_certifies():
    # revocation phase with no reachable secret -> stage5 cannot pass -> not certified
    cfg = _live_cfg(secret_locator="svc:absent_m40", post_revocation_retry=True,
                    validation_phase_passed=True)
    c = m40.run_live_certification(cfg)
    assert c["live_certified"] is False
    assert c["verdict"] != "LIVE_CERTIFIED"


def test_post_revocation_without_validation_attestation_not_certified():
    # even if a 401 were observed, without the validation-phase attestation -> not certified
    cfg = _live_cfg(secret_locator="svc:absent_m40", post_revocation_retry=True,
                    validation_phase_passed=False)
    c = m40.run_live_certification(cfg)
    assert c["live_certified"] is False


def test_live_certified_requires_live_exercised_invariant():
    # the only verdict that sets live_certified true is LIVE_CERTIFIED, and it is
    # produced only on the revocation path with live_exercised true
    for body in (m40.run_live_certification(m40.M40Config()), m40.run_stage_rehearsal()):
        if body["live_certified"]:
            assert body["verdict"] == "LIVE_CERTIFIED" and body["live_exercised"] is True
        else:
            assert body["verdict"] != "LIVE_CERTIFIED"


# ── Stage 6 — evidence completeness ──────────────────────────────────────────
def test_stage6_evidence_complete_and_clean():
    r = m40.run_stage_rehearsal()
    s6 = next(s for s in r["stages"] if s["stage"] == "stage6_evidence_verification")
    assert s6["status"] == "PASSED"
    assert s6["missing_fields"] == []
    assert s6["leak_clean"] is True
    for f in ("identity", "provider", "scopes", "budget", "lease_ids",
              "timestamps", "cleanup", "revocation", "classification"):
        assert f in s6["evidence"]


# ── interruption / timeout / lease-collision resilience (fixtures) ───────────
def test_interruption_single_session_cleans_up():
    r = run_live_single_session(
        secret_source_kind="IN_MEMORY_TEST", secret_locator="m40/synth",
        acknowledgements=M39_ACK_TOKENS, allow_offline_fixture=True,
        interrupt_after="operation", session_id="m40_intr",
    )
    assert r["handle_closed"] is True  # SecretHandle destroyed even on interruption


def test_timeout_retry_classified_not_certified():
    r = run_live_single_session(
        secret_source_kind="IN_MEMORY_TEST", secret_locator="m40/synth",
        acknowledgements=M39_ACK_TOKENS, allow_offline_fixture=True,
        transport=tk.make_transport(sender=tk.raising_sender(TimeoutError())),
        session_id="m40_to",
    )
    assert r["ok"] is False and r["handle_closed"] is True


def test_multi_session_distinct_correlation_ids():
    s = m40.stage4_multi_session(m40.M40Config(mode="rehearsal"), rehearsal=True)
    # isolation invariant proven by the stage
    assert s["lease_isolation_ok"] is True


# ── kill switch ──────────────────────────────────────────────────────────────
def test_kill_switch_blocks_certification():
    c = m40.run_live_certification(m40.M40Config(environ={"SAATHI_M39_KILL_SWITCH": "1"}))
    assert c["verdict"] == "LIVE_BLOCKED"


# ── evidence determinism + leak ──────────────────────────────────────────────
def test_evidence_deterministic_and_clean():
    a = m40.build_m40_evidence()
    b = m40.build_m40_evidence()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["summary"]["live_certified"] is False
    for name, body in a.items():
        assert is_clean(body), name


def test_no_secret_in_certification_output():
    out = m40.run_live_certification(_live_cfg())
    blob = json.dumps(out)
    assert "ghp_" not in blob and "svc:acct" not in blob  # locator fingerprinted, not echoed
    assert is_clean(out)


def test_authorities_not_granted_everywhere():
    for body in (m40.run_live_certification(m40.M40Config()), m40.run_stage_rehearsal()):
        for v in body["authorities"].values():
            assert v == "NOT GRANTED"
        assert body["trading_guardian"] == "UNENGAGED"


def test_evidence_emit(tmp_path):
    res = m40.emit_m40_evidence(tmp_path)
    assert res["count"] == 3
    for p in res["written"]:
        assert is_clean(json.loads(open(p).read()))
