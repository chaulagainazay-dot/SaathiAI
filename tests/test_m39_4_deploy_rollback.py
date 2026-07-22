"""M39.4 — Deployment & rollback preparation tests (offline; executes nothing)."""
from __future__ import annotations

import json

from saathi.credentials import m39_4 as m
from saathi.credentials.leakscan import is_clean


def test_canonical_config_valid():
    assert m.validate_deployment_config()["valid"] is True


def test_unsafe_config_rejected():
    bad = m.validate_deployment_config({
        "rollout": "ON", "per_session_budget_max": 99, "concurrency_max": 99,
        "live_flag_default": "on", "canary": "GRANTED",
    })
    assert bad["valid"] is False
    for p in ("rollout_must_be_off", "per_session_budget_exceeds_ceiling",
              "concurrency_exceeds_ceiling", "live_flag_default_must_be_off",
              "canary_must_be_NOT GRANTED"):
        assert p in bad["problems"]


def test_backward_compat_additive():
    bc = m.backward_compatibility_check()
    assert bc["all_present"] is True
    assert bc["missing"] == []
    assert bc["additive_only"] is True
    assert bc["checked"] >= 11


def test_artifact_integrity_stable():
    ai = m.artifact_integrity()
    assert ai["stable"] is True and len(ai["m39_fingerprint"]) == 64


def test_release_checklist_gates():
    gates = m.release_checklist()["gates"]
    ids = [g["id"] for g in gates]
    assert ids == [f"REL-{i}" for i in range(1, 11)]


def test_rollback_plan_does_not_execute():
    rb = m.rollback_plan()
    assert rb["executes"] is False and rb["reversible"] is True
    assert rb["trading_guardian_untouched"] is True
    # script is text only and performs no push / force-push / hard reset
    script = rb["script_template"]
    assert "--force" not in script and "push -f" not in script
    assert "git push" not in script
    assert "reset --hard" not in script


def test_rollback_script_disables_flag_and_trips_kill():
    script = m.rollback_plan()["script_template"]
    assert "SAATHI_M39_ALLOW_LIVE_SANDBOX_VALIDATION" in script
    assert "SAATHI_M39_KILL_SWITCH=1" in script


def test_smoke_tests_defined():
    st = m.smoke_test_definitions()["tests"]
    assert len(st) == 4
    assert any("m39-2-simulation-matrix" in t["cmd"] for t in st)


def test_summary_complete_and_no_execution():
    ev = m.build_m39_4_evidence()
    s = ev["summary"]
    assert s["verdict"] == "DEPLOY_ROLLBACK_PREP_COMPLETE"
    assert s["executes_nothing"] is True
    for v in s["authorities"].values():
        assert v == "NOT GRANTED"
    assert s["trading_guardian"] == "UNENGAGED"


def test_evidence_deterministic_and_clean():
    a = m.build_m39_4_evidence()
    b = m.build_m39_4_evidence()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    for name, body in a.items():
        assert is_clean(body), name


def test_evidence_emit(tmp_path):
    res = m.emit_m39_4_evidence(tmp_path)
    assert res["count"] == 8
    for p in res["written"]:
        assert is_clean(json.loads(open(p).read()))
