"""M17.21 — Control Center Registry Health cell."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.application_harness import registry
from saathi.application_harness.models import HarnessDefinition, TrustStatus
from saathi.control_center.aggregator import ControlCenterAggregator


@pytest.fixture()
def iso_reg(tmp_path):
    store = tmp_path / "registry.json"
    original = Path(registry.STORE)
    registry.reset_for_tests(store=store)
    yield store
    registry.reset_for_tests(store=original)


def _ext(hid="ext_h"):
    return HarnessDefinition(
        harness_id=hid, display_name=hid, application_name=hid,
        version="1.0.0", source_type="cli_anything",
        source_repository="https://example.invalid/x",
        source_commit="abc", install_method="brew",
        trust_status=TrustStatus.EXTERNAL_UNTRUSTED.value,
        validation_status="imported_untrusted",
    )


def test_health_score_perfect_on_clean_bootstrap(iso_reg):
    registry.all_harnesses()  # missing store is fine
    h = registry.health()
    assert h["overall_status"] == "GREEN"
    assert h["health_score"] >= 80
    assert h["schema_version"] == 1
    assert "registry_revision" in h
    assert h["size_limit"] == registry._MAX_STORE_BYTES
    assert h["entry_limit"] == registry._MAX_ENTRIES
    assert h["critical_checks_total"] >= 1
    assert "raw" not in h and "payload" not in h


def test_failed_validation_lowers_score(iso_reg):
    iso_reg.write_text("{not json", encoding="utf-8")
    registry.all_harnesses()
    h = registry.health()
    assert h["load_status"] == "invalid"
    assert h["health_score"] < 100
    assert h["overall_status"] in ("RED", "ORANGE", "YELLOW")
    assert any("load:" in r for r in h["score_reasons"])


def test_critical_failures_become_red(iso_reg):
    iso_reg.write_text(json.dumps({"schema_version": 99, "harnesses": []}),
                       encoding="utf-8")
    registry.all_harnesses()
    h = registry.health()
    assert h["load_status"] == "unsupported_schema"
    assert h["overall_status"] == "RED"
    assert h["health_score"] < 40 or "schema_mismatch" in h["score_reasons"]


def test_stale_lock_recovery_recorded(iso_reg):
    registry._note_health("stale_lock_recovered", "flock_free")
    h = registry.health()
    assert h["last_recovery"] is not None
    assert h["last_recovery"]["kind"] == "stale_lock_recovered"
    assert h["health_score"] < 100


def test_conflict_warning_recorded(iso_reg):
    registry._note_health("revision_conflict", "expected=1")
    h = registry.health()
    assert h["last_conflict"] is not None
    assert "conflict" in h["score_reasons"]


def test_registry_size_warning(iso_reg):
    score, status, reasons = registry._score_and_status({
        "load_status": "ok",
        "registry_size_bytes": 900,
        "size_limit": 1000,
        "critical_checks_green": 10,
        "critical_checks_total": 10,
    })
    assert "size_warning" in reasons or "near_size_limit" in reasons
    assert score < 100


def test_schema_mismatch_in_health(iso_reg):
    iso_reg.write_text(json.dumps({"schema_version": 99, "harnesses": []}),
                       encoding="utf-8")
    registry.all_harnesses()
    h = registry.health()
    assert h["load_status"] == "unsupported_schema"
    diag = registry.health_diagnostics()
    assert diag["load_status"] == "unsupported_schema"
    assert "raw" not in diag


def test_critical_check_aggregation(iso_reg):
    h = registry.health()
    assert h["critical_checks_total"] >= 10  # M17.18–20 registry.* checks
    assert isinstance(h["critical_check_ids"], list)
    assert all(i.startswith("registry.") for i in h["critical_check_ids"])


def test_ceo_summary_suppressed_when_green(iso_reg):
    registry.all_harnesses()
    h = registry.health()
    assert h["overall_status"] == "GREEN"
    assert h["health_score"] >= registry._CEO_BRIEF_SCORE_THRESHOLD
    assert h["include_in_ceo_brief"] is False


def test_ceo_summary_shown_when_unhealthy(iso_reg):
    iso_reg.write_text("{broken", encoding="utf-8")
    registry.all_harnesses()
    h = registry.health()
    assert h["include_in_ceo_brief"] is True


def test_control_center_registry_cell(iso_reg):
    registry.register(_ext("ext_cc"), operation_id="cc1")
    cell = ControlCenterAggregator("ajay").registry_health()
    assert cell.status == "ok"
    assert cell.source == "application_harness.registry_health"
    v = cell.value
    assert v["overall_status"] in ("GREEN", "YELLOW", "ORANGE", "RED")
    assert "health_score" in v
    assert "registry_revision" in v


def test_control_center_overview_includes_registry_health(iso_reg):
    ov = ControlCenterAggregator("ajay").overview()
    assert "registry_health" in ov
    assert ov["registry_health"]["status"] == "ok"
    assert "health_score" in ov["registry_health"]["value"]


def test_safe_diagnostics_only(iso_reg):
    registry.register(_ext("ext_safe"), operation_id="safe1")
    d = registry.health_diagnostics()
    blob = json.dumps(d).lower()
    assert "api_key" not in blob
    assert "password" not in blob
    assert "secret" not in blob or "secret" in " ".join(
        d.get("critical_checks", {}).get("ids") or []
    )  # allow only if appearing in check ids
    assert "harnesses" not in d
    assert "raw" not in d
    assert d.get("limits")
    # no full entry dump keys
    for banned in ("entrypoint", "source_repository", "body", "content"):
        assert banned not in d


def test_health_deterministic(iso_reg):
    registry.all_harnesses()
    a = registry.health()
    b = registry.health()
    assert a["health_score"] == b["health_score"]
    assert a["overall_status"] == b["overall_status"]
    assert a["score_reasons"] == b["score_reasons"]


def test_health_survives_restart(iso_reg):
    registry.register(_ext("ext_rs"), operation_id="rs1")
    rev = registry.health()["registry_revision"]
    registry.reset_for_tests(store=iso_reg)
    h = registry.health()
    assert h["registry_revision"] == rev
    assert h["overall_status"] in ("GREEN", "YELLOW", "ORANGE", "RED")


def test_score_function_pure():
    s1, st1, _ = registry._score_and_status({
        "load_status": "ok", "registry_size_bytes": 10, "size_limit": 1000,
        "critical_checks_green": 5, "critical_checks_total": 5,
    })
    s2, st2, _ = registry._score_and_status({
        "load_status": "ok", "registry_size_bytes": 10, "size_limit": 1000,
        "critical_checks_green": 5, "critical_checks_total": 5,
    })
    assert (s1, st1) == (s2, st2) == (100, "GREEN")


def test_trading_guardian_unchanged(iso_reg):
    src = Path(registry.__file__).read_text(encoding="utf-8")
    banned = ("broker", "withdraw", "leverage", "place_order", "trade_execution",
              "exchange_execution", "portfolio_", "binance", "alpaca")
    low = src.lower()
    for b in banned:
        assert b not in low, b


def test_attention_includes_registry_when_red(iso_reg):
    iso_reg.write_text(json.dumps({"schema_version": 99, "harnesses": []}),
                       encoding="utf-8")
    registry.all_harnesses()
    ov = ControlCenterAggregator("ajay").overview()
    kinds = [i["kind"] for i in ov["requires_attention"]]
    assert "registry_health" in kinds or "registry_schema" in kinds


def test_health_metrics_complete(iso_reg):
    h = registry.health()
    required = [
        "overall_status", "schema_version", "registry_revision",
        "built_in_pilots", "persisted_entries", "active_entries",
        "disabled_entries", "trust_overlays", "last_load_time",
        "last_successful_write", "last_validation", "last_atomic_write",
        "lock_state", "lock_owner", "lock_waiters", "last_conflict",
        "last_recovery", "failed_validations", "rejected_entries",
        "quarantined_files", "registry_size_bytes", "entry_limit",
        "size_limit", "critical_checks_green", "critical_checks_total",
        "health_score",
    ]
    for k in required:
        assert k in h, f"missing {k}"
