"""M39.8 — Final operator package tests (offline; no secret values)."""
from __future__ import annotations

import json

from saathi.credentials import m39_8 as m
from saathi.credentials.leakscan import is_clean


def test_package_indexes_all_milestones():
    pkg = m.build_operator_package()
    ids = [x["id"] for x in pkg["milestones"]]
    assert ids == ["M39", "M39.1", "M39.2", "M39.3", "M39.4",
                   "M39.5", "M39.6", "M39.7", "M39.8"]


def test_all_ten_acknowledgements_present():
    pkg = m.build_operator_package()
    assert len(pkg["required_acknowledgements"]) == 10


def test_permission_model_read_only():
    pm = m.build_operator_package()["permission_model"]
    assert pm["provider"] == "github_meta"
    assert pm["minimum_required"]["methods"] == ["GET"]
    assert set(pm["minimum_required"]["endpoints"]) == {"user", "meta"}
    assert "repository write" in pm["prohibited"]


def test_authority_state_all_denied():
    a = m.build_operator_package()["authority_state"]
    assert a["LIVE_PROVIDER_CERTIFICATION"] == "NOT GRANTED"
    assert a["CANARY"] == "NOT GRANTED"
    assert a["ACTIVE"] == "NOT GRANTED"
    assert a["PRODUCTION_DEPLOYMENT"] == "NOT AUTHORIZED"


def test_known_limitations_mark_not_exercised():
    pkg = m.build_operator_package()
    joined = " ".join(pkg["known_limitations"])
    assert "NOT_EXERCISED" in joined


def test_go_live_checklist_requires_reference_not_raw():
    pkg = m.build_operator_package()
    joined = " ".join(pkg["go_live_checklist"]).lower()
    assert "reference" in joined and "never a raw secret" in joined


def test_trust_boundaries_present():
    pkg = m.build_operator_package()
    assert len(pkg["trust_boundaries"]) >= 4


def test_package_deterministic_and_clean():
    a = m.build_m39_8_evidence()
    b = m.build_m39_8_evidence()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    for name, body in a.items():
        assert is_clean(body), name


def test_summary_verdict():
    ev = m.build_m39_8_evidence()
    assert ev["summary"]["verdict"] == "OPERATOR_PACKAGE_COMPLETE"
    assert ev["summary"]["trading_guardian"] == "UNENGAGED"


def test_evidence_emit(tmp_path):
    res = m.emit_m39_8_evidence(tmp_path)
    assert res["count"] == 2
    for p in res["written"]:
        assert is_clean(json.loads(open(p).read()))
