"""M264–M271 recovery, clean-clone markers, and historical qualification tests.

PAPER/RESEARCH ONLY. No brokers. No credentials.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "docs/trading/m264_m271_evidence"


def test_m248_m255_committed_source_present():
    assert (ROOT / "saathi/platform/tg/intelligence/service.py").is_file()
    # Must be tracked in git — checked via ls-files if available
    import subprocess
    out = subprocess.check_output(
        ["git", "ls-files", "saathi/platform/tg/intelligence/service.py"],
        cwd=ROOT, text=True,
    ).strip()
    assert out.endswith("intelligence/service.py")


def test_m256_m263_committed_source_present():
    assert (ROOT / "saathi/platform/tg/market_data/service.py").is_file()
    import subprocess
    out = subprocess.check_output(
        ["git", "ls-files", "saathi/platform/tg/market_data/service.py"],
        cwd=ROOT, text=True,
    ).strip()
    assert out


def test_exact_m248_test_filename():
    assert (ROOT / "tests/test_m248_m255_institutional_intelligence.py").is_file()
    assert not (ROOT / "tests/test_m248_m255_intelligence.py").is_file()


def test_recovery_intake_ok():
    doc = json.loads((EV / "M264_RECOVERY_INTAKE.json").read_text())
    assert doc["recovery_status"] == "OK"
    assert doc["defect"]["confirmed_absent_from_HEAD"] is True
    assert doc["inventory_count"] >= 30


def test_dependency_audit_zero_untracked():
    doc = json.loads((EV / "M266_INTEGRATION_DEPENDENCY_AUDIT.json").read_text())
    assert doc["UNTRACKED_SOURCE_DEPENDENCIES"] == 0
    assert doc["api"]["intelligence_routes"] and doc["api"]["research_data_routes"]
    assert doc["frontend"]["intelligence_tab"] and doc["frontend"]["research_data_tab"]


def test_clean_clone_certification_markers():
    doc = json.loads((EV / "M267_CLEAN_CLONE_CERTIFICATION.json").read_text())
    assert doc["M248_M255_COMMITTED_SOURCE_PRESENT"] is True
    assert doc["M256_M263_COMMITTED_SOURCE_PRESENT"] is True
    assert doc["UNTRACKED_REQUIRED_SOURCE_FILES"] == 0
    assert doc["CLEAN_CLONE_BACKEND_TESTS_PASSED"] is True
    assert doc["CLEAN_CLONE_FRONTEND_TESTS_PASSED"] is True
    assert doc["CLEAN_CLONE_PRODUCTION_BUILD_PASSED"] is True
    assert doc["M255_BROWSER_CERT_PASSED"] is True
    assert doc["M263_BROWSER_CERT_PASSED"] is True


def test_historical_selection_and_checksums():
    doc = json.loads((EV / "M268_HISTORICAL_DATASET_SELECTION.json").read_text())
    assert doc["selected_count"] >= 2
    for s in doc["selected"]:
        if s.get("ok"):
            assert s.get("checksum")
            assert s.get("publisher")
            assert s.get("licence") or s.get("licence_name")


def test_historical_quality_and_validation_evidence():
    q = json.loads((EV / "M269_HISTORICAL_DATA_QUALITY_CERTIFICATION.json").read_text())
    v = json.loads((EV / "M270_REAL_HISTORICAL_SIGNAL_VALIDATION.json").read_text())
    assert q["raw_prices_preserved"] is True
    assert q["not_regulatory_grade"] is True
    assert v["historical_data_status"] in (
        "BOUNDED_REAL_HISTORICAL_DATA_VALIDATED_WITH_LIMITATIONS",
        "REAL_HISTORICAL_DATA_VALIDATION_INCOMPLETE",
        "HISTORICAL_DATA_GOVERNANCE_BLOCKED",
        "HISTORICAL_DATA_QUALITY_FAILED",
    )
    for state in ("PROFITABLE", "GUARANTEED", "LIVE_READY", "BROKER_READY"):
        assert state in v["forbidden_claims_not_used"]
    # At least one validation run recorded
    assert len(v["validations"]) >= 1
    for run in v["validations"]:
        assert run.get("is_synthetic") is False
        assert run.get("state") not in ("PROFITABLE", "GUARANTEED", "LIVE_READY")


def test_dual_services_certify():
    from saathi.platform.tg.intelligence.service import reset_intelligence_for_tests
    from saathi.platform.tg.market_data.service import reset_market_data_for_tests
    import tempfile
    td = Path(tempfile.mkdtemp())
    ii = reset_intelligence_for_tests(td / "ii.db")
    md = reset_market_data_for_tests(td / "md.db")
    assert ii.certify()["hard_gates_pass"] is True
    assert md.certify()["hard_gates_pass"] is True
    assert ii.terminal_verdict()["LIVE_TRADING_AUTHORIZED"] is False
    assert md.terminal_verdict()["LIVE_TRADING_AUTHORIZED"] is False
