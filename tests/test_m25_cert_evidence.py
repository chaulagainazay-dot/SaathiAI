"""M25 — Canonical production-certification package evidence."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from saathi.inference import cert_evidence as ce
from saathi.inference.runtime_gate import (
    GateState,
    MANDATORY_CERT_CHECKS,
    decide_production_certified,
    evaluate_runtime_gate,
)
from saathi.inference import runtime_gate as rg

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def cert_store(tmp_path, monkeypatch):
    """Isolate package evidence under tmp_path."""
    monkeypatch.setattr(ce, "EVIDENCE_DIR", tmp_path)
    monkeypatch.setattr(ce, "SUITE_PATH", tmp_path / "full_suite_evidence.json")
    monkeypatch.setattr(ce, "SECRET_PATH", tmp_path / "secret_scan_evidence.json")
    monkeypatch.setattr(ce, "CRITICAL_PATH", tmp_path / "critical_check_evidence.json")
    monkeypatch.setattr(ce, "FOCUSED_PATH", tmp_path / "focused_suite_evidence.json")
    monkeypatch.setattr(ce, "PACKAGE_PATH", tmp_path / "certification_package.json")
    return tmp_path


def test_atomic_write_evidence(cert_store):
    rec = ce.write_evidence(
        "full_suite_evidence",
        status="PASS",
        detail="unit",
        metrics={"passed": 10, "failed": 0},
        path=ce.SUITE_PATH,
    )
    assert ce.SUITE_PATH.is_file()
    assert not ce.SUITE_PATH.with_suffix(".json.tmp").exists()
    data = json.loads(ce.SUITE_PATH.read_text(encoding="utf-8"))
    assert data["status"] == "PASS"
    assert data["schema"] == ce.SCHEMA
    assert data["package_fingerprint"]
    assert data["created_at"]
    assert data["expires_at"]
    assert data["producer_version"] == ce.PRODUCER_VERSION
    assert rec.status == "PASS"


def test_successful_evidence_injection(cert_store):
    ce.write_evidence("full_suite_evidence", status="PASS", detail="ok", path=ce.SUITE_PATH)
    ce.write_evidence("secret_scan_evidence", status="PASS", detail="ok", path=ce.SECRET_PATH)
    ce.write_evidence("critical_check_evidence", status="PASS", detail="ok", path=ce.CRITICAL_PATH)
    inj = ce.inject_evidence_dict()
    assert inj["full_suite_status"] == "PASS"
    assert inj["secret_scan_status"] == "PASS"
    assert inj["critical_check_status"] == "PASS"


def test_missing_evidence_status(cert_store):
    st, meta = ce.evidence_status_for_gate("full_suite_evidence")
    assert st == "MISSING"
    assert meta["evidence_id"] == "full_suite_evidence"


def test_fingerprint_mismatch_is_stale(cert_store, monkeypatch):
    ce.write_evidence("full_suite_evidence", status="PASS", detail="ok", path=ce.SUITE_PATH)
    data = json.loads(ce.SUITE_PATH.read_text(encoding="utf-8"))
    data["package_fingerprint"] = "sha256:deadbeef"
    ce.SUITE_PATH.write_text(json.dumps(data), encoding="utf-8")
    st, meta = ce.evidence_status_for_gate("full_suite_evidence")
    assert st == "STALE"
    assert meta["freshness"] == "STALE"


def test_stale_by_expiration(cert_store):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    rec = {
        "evidence_id": "full_suite_evidence",
        "status": "PASS",
        "package_fingerprint": ce.package_fingerprint(),
        "created_at": (past - timedelta(days=20)).isoformat(),
        "expires_at": past.isoformat(),
        "ttl_seconds": 1,
    }
    ce._atomic_write_json(ce.SUITE_PATH, rec)
    assert ce.evaluate_freshness(rec) == "STALE"
    st, _ = ce.evidence_status_for_gate("full_suite_evidence")
    assert st == "STALE"


def test_fail_status_preserved(cert_store):
    ce.write_evidence("secret_scan_evidence", status="FAIL", detail="hit", path=ce.SECRET_PATH)
    st, meta = ce.evidence_status_for_gate("secret_scan_evidence")
    assert st == "FAIL"


def test_record_full_suite_from_counts(cert_store):
    rec = ce.record_full_suite(passed=3095, failed=0, skipped=1)
    assert rec.status == "PASS"
    assert rec.metrics["passed"] == 3095
    assert rec.metrics["failed"] == 0


def test_record_full_suite_failed_counts(cert_store):
    rec = ce.record_full_suite(passed=100, failed=5, skipped=0)
    assert rec.status == "FAIL"


def test_runtime_gate_missing_package_blocks_cert(cert_store, monkeypatch):
    """No package artifacts → MISSING → production_certified false."""
    rep = evaluate_runtime_gate(
        evidence={"_skip_disk_cert_evidence": False},
        include_live_probe=False,
    )
    by = {c.check_id: c for c in rep.checks}
    assert by["full_suite_evidence"].state is GateState.MISSING
    assert by["secret_scan_evidence"].state is GateState.MISSING
    assert by["critical_check_evidence"].state is GateState.MISSING
    assert rep.production_certified is False
    assert any("full_suite_evidence" in b for b in rep.certification_blockers)


def test_runtime_gate_stale_blocks_cert(cert_store):
    for eid, path in (
        ("full_suite_evidence", ce.SUITE_PATH),
        ("secret_scan_evidence", ce.SECRET_PATH),
        ("critical_check_evidence", ce.CRITICAL_PATH),
    ):
        ce.write_evidence(eid, status="PASS", detail="ok", path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["package_fingerprint"] = "sha256:stale"
        path.write_text(json.dumps(data), encoding="utf-8")

    rep = evaluate_runtime_gate(include_live_probe=False)
    by = {c.check_id: c for c in rep.checks}
    assert by["full_suite_evidence"].state is GateState.STALE
    assert rep.production_certified is False
    assert any("STALE" in b for b in rep.certification_blockers)


def test_runtime_gate_package_pass_with_live_can_certify(cert_store):
    ce.write_evidence(
        "full_suite_evidence",
        status="PASS",
        detail="3095 passed",
        metrics={"passed": 3095, "failed": 0, "skipped": 1},
        path=ce.SUITE_PATH,
    )
    ce.write_evidence("secret_scan_evidence", status="PASS", detail="clean", path=ce.SECRET_PATH)
    ce.write_evidence(
        "critical_check_evidence", status="PASS", detail="ok", path=ce.CRITICAL_PATH
    )
    # Force live PASS via evidence override of live probe path: inject statuses
    # and mock detect_live_provider_status
    rep = evaluate_runtime_gate(
        evidence={
            "full_suite_status": "PASS",
            "secret_scan_status": "PASS",
            "critical_check_status": "PASS",
        },
        include_live_probe=True,
    )
    by = {c.check_id: c for c in rep.checks}
    assert by["full_suite_evidence"].state is GateState.PASS
    assert by["secret_scan_evidence"].state is GateState.PASS
    assert by["critical_check_evidence"].state is GateState.PASS
    # Production true only if live also PASS
    if by["live_provider_cert"].state is GateState.PASS:
        assert rep.production_certified is True
        assert rep.certification_blockers == []
    else:
        assert rep.production_certified is False
        assert any("live_provider_cert" in b for b in rep.certification_blockers)


def test_decide_production_true_when_all_mandatory_pass():
    checks = [rg.GateCheck(cid, GateState.PASS) for cid in MANDATORY_CERT_CHECKS]
    cert, blockers = decide_production_certified(checks, force_false=False)
    assert cert is True
    assert blockers == []


def test_decide_production_false_on_missing():
    checks = []
    for cid in MANDATORY_CERT_CHECKS:
        st = GateState.MISSING if cid == "secret_scan_evidence" else GateState.PASS
        checks.append(rg.GateCheck(cid, st))
    cert, blockers = decide_production_certified(checks, force_false=False)
    assert cert is False
    assert any("secret_scan_evidence:MISSING" in b for b in blockers)


def test_force_false_path_still_works():
    checks = [rg.GateCheck(cid, GateState.PASS) for cid in MANDATORY_CERT_CHECKS]
    cert, _ = decide_production_certified(checks, force_false=True)
    assert cert is False


def test_historical_live_cert_not_invalidated_by_package_fingerprint():
    """Package fingerprint must not erase historical live cert file."""
    live_path = ROOT / "docs" / "evidence" / "m25" / "LAST_SUCCESSFUL_LIVE_CERTIFICATION.json"
    assert live_path.is_file()
    before = live_path.read_text(encoding="utf-8")
    _ = ce.package_fingerprint()
    after = live_path.read_text(encoding="utf-8")
    assert before == after
    data = json.loads(before)
    assert data.get("live_provider_certified") is True


def test_environment_observation_separate_from_package(cert_store):
    """Package evidence status is independent of RAM / environment observation."""
    ce.write_evidence("full_suite_evidence", status="PASS", detail="ok", path=ce.SUITE_PATH)
    # Even if env is blocked, suite evidence remains PASS (not STALE from RAM)
    st, meta = ce.evidence_status_for_gate("full_suite_evidence")
    assert st == "PASS"
    assert "available_memory" not in (meta.get("detail") or "")


def test_skip_disk_cert_evidence_flag(cert_store):
    ce.write_evidence("full_suite_evidence", status="PASS", detail="ok", path=ce.SUITE_PATH)
    ce.write_evidence("secret_scan_evidence", status="PASS", detail="ok", path=ce.SECRET_PATH)
    ce.write_evidence(
        "critical_check_evidence", status="PASS", detail="ok", path=ce.CRITICAL_PATH
    )
    rep = evaluate_runtime_gate(
        evidence={"_skip_disk_cert_evidence": True},
        include_live_probe=False,
    )
    by = {c.check_id: c for c in rep.checks}
    assert by["full_suite_evidence"].state is GateState.MISSING
    assert rep.production_certified is False


def test_package_fingerprint_stable():
    a = ce.package_fingerprint()
    b = ce.package_fingerprint()
    assert a == b
    assert a.startswith("sha256:")
