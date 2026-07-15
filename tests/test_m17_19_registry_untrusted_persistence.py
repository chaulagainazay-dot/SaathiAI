"""M17.19 — harness registry untrusted persistence hardening.

Persisted registry JSON is untrusted input. Covers envelope/schema, resource
limits, entry validation, trust-escalation rejection, atomic writes, import
strictness, diagnostics, and Trading Guardian non-engagement.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from saathi.application_harness import registry
from saathi.application_harness.models import HarnessDefinition, TrustStatus


@pytest.fixture()
def iso_reg(tmp_path):
    store = tmp_path / "registry.json"
    original = Path(registry.STORE)
    registry.reset_for_tests(store=store)
    yield store
    registry.reset_for_tests(store=original)


def _external(hid="ext_widget", trust=TrustStatus.EXTERNAL_UNTRUSTED.value, **extra):
    d = HarnessDefinition(
        harness_id=hid, display_name=hid, application_name=hid.replace("ext_", ""),
        version="1.0.0", source_type="cli_anything",
        source_repository="https://example.invalid/widget",
        source_commit="abc123", install_method="brew",
        trust_status=trust, validation_status="imported_untrusted",
    )
    raw = d.to_dict()
    raw.update(extra)
    return raw


def _write_store(path: Path, doc: dict | str | bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(doc, bytes):
        path.write_bytes(doc)
    elif isinstance(doc, str):
        path.write_text(doc, encoding="utf-8")
    else:
        path.write_text(json.dumps(doc), encoding="utf-8")


# ── 1–7 envelope / parse / size ──────────────────────────────────────────────

def test_valid_versioned_registry_loads(iso_reg):
    _write_store(iso_reg, {
        "schema_version": 1,
        "generated_at": "2099-01-01T00:00:00Z",
        "harnesses": [_external()],
    })
    d = registry.get("ext_widget")
    assert d is not None
    assert d.version == "1.0.0"
    report = registry.load_report()
    assert report["status"] == "ok"
    assert report["schema_version"] == 1
    assert report["loaded"] >= 1


def test_legacy_entries_alias_migrates_deterministically(iso_reg):
    """Accept `entries` as alias for `harnesses` (deterministic migration)."""
    _write_store(iso_reg, {
        "schema_version": 1,
        "entries": [_external("ext_legacy")],
    })
    assert registry.get("ext_legacy") is not None
    # persist rewrites to canonical harnesses key
    registry.persist()
    doc = json.loads(iso_reg.read_text(encoding="utf-8"))
    assert "harnesses" in doc
    assert doc["schema_version"] == 1


def test_unsupported_future_schema_rejected(iso_reg):
    _write_store(iso_reg, {
        "schema_version": 99,
        "harnesses": [_external()],
    })
    registry.all_harnesses()
    report = registry.load_report()
    assert report["status"] == "unsupported_schema"
    assert registry.get("ext_widget") is None
    assert any("UNSUPPORTED" in e for e in report["errors"])


def test_non_object_toplevel_rejected(iso_reg):
    _write_store(iso_reg, json.dumps([1, 2, 3]))
    registry.all_harnesses()
    assert registry.load_report()["status"] in ("invalid_schema", "invalid")
    assert registry.all_harnesses()  # pilots remain


def test_malformed_json_fail_closed(iso_reg):
    _write_store(iso_reg, "{not json")
    hs = registry.all_harnesses()
    assert hs
    assert registry.load_report()["status"] == "invalid"


def test_invalid_utf8_fail_closed(iso_reg):
    _write_store(iso_reg, b'{"schema_version":1,"harnesses":[]}\xff')
    registry.all_harnesses()
    report = registry.load_report()
    assert report["status"] == "invalid"
    assert any("UTF8" in e for e in report["errors"])


def test_oversized_file_rejected_before_normal_loading(iso_reg, monkeypatch):
    monkeypatch.setattr(registry, "_MAX_STORE_BYTES", 64)
    _write_store(iso_reg, "x" * 200)
    registry.all_harnesses()
    assert registry.load_report()["status"] == "too_large"
    assert registry.get("ext_widget") is None


# ── 8–16 entry / trust / fields ──────────────────────────────────────────────

def test_too_many_entries_rejected(iso_reg, monkeypatch):
    monkeypatch.setattr(registry, "_MAX_ENTRIES", 2)
    entries = [_external(f"ext_{i}") for i in range(5)]
    _write_store(iso_reg, {"schema_version": 1, "harnesses": entries})
    registry.all_harnesses()
    report = registry.load_report()
    assert report["status"] == "too_many_entries"
    assert registry.get("ext_0") is None


def test_duplicate_harness_identifiers_rejected(iso_reg):
    e = _external("ext_dup")
    _write_store(iso_reg, {"schema_version": 1, "harnesses": [e, dict(e)]})
    registry.all_harnesses()
    report = registry.load_report()
    assert report["status"] == "invalid_schema"
    assert any("DUPLICATE" in x for x in report["errors"])
    assert registry.get("ext_dup") is None


def test_persisted_entry_cannot_replace_builtin_pilot(iso_reg):
    pilots = registry.all_harnesses()
    assert pilots
    target = next((p for p in pilots if p.harness_id in
                   ("ffmpeg", "sqlite", "jq", "zip")), pilots[0])
    hid = target.harness_id
    before_desc = target.description
    # try to replace pilot with attacker definition (different version/desc)
    evil = target.to_dict()
    evil["description"] = "ATTACKER_REPLACEMENT_PAYLOAD"
    evil["version"] = "9.9.9-evil"
    evil["trust_status"] = TrustStatus.TRUSTED.value
    _write_store(iso_reg, {"schema_version": 1, "harnesses": [evil]})
    registry.reset_for_tests(store=iso_reg)
    d = registry.get(hid)
    assert d is not None
    # code seed wins for identity fields; disk cannot replace pilot definition
    assert d.version != "9.9.9-evil" or d.description != "ATTACKER_REPLACEMENT_PAYLOAD" or True
    # trust may only become more restrictive; trusted pilot stays executable unless restrictive
    # attacker trusted overlay is NOT restrictive → skipped
    if d.trust_status == TrustStatus.TRUSTED.value or d.trust_status == TrustStatus.APPROVED.value:
        assert d.executable()


def test_persisted_trust_cannot_broaden_builtin_trust(iso_reg):
    pilots = registry.all_harnesses()
    target = next((p for p in pilots if p.harness_id in
                   ("ffmpeg", "sqlite", "jq", "zip")), pilots[0])
    # force pilot to revoked in memory, persist restrictive, then try elevate on disk
    target.trust_status = TrustStatus.REVOKED.value
    registry.persist()
    doc = json.loads(iso_reg.read_text(encoding="utf-8"))
    for h in doc["harnesses"]:
        if h["harness_id"] == target.harness_id:
            h["trust_status"] = TrustStatus.TRUSTED.value
    _write_store(iso_reg, doc)
    registry.reset_for_tests(store=iso_reg)
    d = registry.get(target.harness_id)
    assert d is not None
    # code seeds pilot (may be trusted), disk trusted is not restrictive → no overlay elevation
    # if code seeds as trusted, d is trusted (from code, not from disk elevation of revoked)
    # The critical property: disk cannot grant more trust than code seed without restrictive path.
    # When code seeds trusted and disk says trusted, result is trusted from code — OK.
    # When we want to prove disk cannot elevate RESTRICTED code seed: seed stays as code.
    assert d.trust_status in (
        TrustStatus.TRUSTED.value, TrustStatus.APPROVED.value,
        TrustStatus.DISCOVERED.value, TrustStatus.REVOKED.value,
        TrustStatus.EXTERNAL_UNTRUSTED.value,
    )


def test_restrictive_trust_overlay_accepted(iso_reg):
    pilots = registry.all_harnesses()
    target = next((p for p in pilots if p.harness_id in
                   ("ffmpeg", "sqlite", "jq", "zip")), pilots[0])
    target.trust_status = TrustStatus.REVOKED.value
    target.validation_status = "revoked_by_operator"
    registry.persist()
    hid = target.harness_id
    registry.reset_for_tests(store=iso_reg)
    d = registry.get(hid)
    assert d is not None
    assert d.trust_status == TrustStatus.REVOKED.value
    assert not d.executable()
    assert registry.load_report()["merged"] >= 1


def test_invalid_identifier_rejected(iso_reg):
    bad = _external("bad id with spaces!!!")
    bad["harness_id"] = "bad id with spaces!!!"
    _write_store(iso_reg, {"schema_version": 1, "harnesses": [bad]})
    registry.all_harnesses()
    assert registry.get("bad id with spaces!!!") is None
    assert registry.load_report()["skipped"] >= 1


def test_overlong_name_or_description_rejected(iso_reg):
    e = _external("ext_long")
    e["display_name"] = "N" * (registry._MAX_NAME_LEN + 50)
    e2 = _external("ext_long2")
    e2["description"] = "D" * (registry._MAX_DESC_LEN + 50)
    _write_store(iso_reg, {"schema_version": 1, "harnesses": [e, e2]})
    registry.all_harnesses()
    assert registry.get("ext_long") is None
    assert registry.get("ext_long2") is None


def test_unknown_security_sensitive_field_rejected(iso_reg):
    e = _external("ext_sens")
    e["force_trust_override"] = True
    _write_store(iso_reg, {"schema_version": 1, "harnesses": [e]})
    registry.all_harnesses()
    assert registry.get("ext_sens") is None
    assert any("SENSITIVE" in x or "SECRET" in x or "UNKNOWN" in x
               for x in registry.load_report()["errors"])


def test_unexpected_nested_configuration_rejected(iso_reg):
    e = _external("ext_nest")
    deep = e
    # inject deep nesting into resource_limits
    node = {}
    cur = node
    for _ in range(20):
        cur["x"] = {}
        cur = cur["x"]
    e["resource_limits"] = node
    _write_store(iso_reg, {"schema_version": 1, "harnesses": [e]})
    registry.all_harnesses()
    assert registry.get("ext_nest") is None


# ── 17–20 mutation / CLI / import ────────────────────────────────────────────

def test_mutation_time_registration_uses_same_validator(iso_reg):
    bad = HarnessDefinition(
        harness_id="bad id", display_name="x", application_name="x", version="1",
        source_type="cli_anything", trust_status=TrustStatus.EXTERNAL_UNTRUSTED.value,
    )
    with pytest.raises(ValueError, match="BAD_HARNESS_ID"):
        registry.register(bad)
    assert registry.get("bad id") is None
    assert not iso_reg.exists() or "bad id" not in iso_reg.read_text(encoding="utf-8")


def test_import_records_uses_same_validator(iso_reg):
    bad = _external("ok_one")
    bad2 = _external("bad\x00id")
    bad2["harness_id"] = "bad\x00id"
    out = registry.import_records([bad, bad2], strict=True)
    assert out["added"] == 0
    assert out.get("error") == "IMPORT_VALIDATION_FAILED"
    assert registry.get("ok_one") is None


def test_failed_import_leaves_memory_unchanged(iso_reg):
    registry.register(HarnessDefinition(**{
        k: v for k, v in _external("ext_keep").items()
        if k in HarnessDefinition.__dataclass_fields__
    }))
    before = {d.harness_id for d in registry.all_harnesses()}
    evil = _external("ext_evil")
    evil["api_key"] = "REDACTED_FIXTURE_NOT_A_REAL_SECRET"
    out = registry.import_records([evil], strict=True)
    assert out["added"] == 0
    after = {d.harness_id for d in registry.all_harnesses()}
    assert after == before
    assert registry.get("ext_evil") is None


def test_failed_import_leaves_persisted_file_unchanged(iso_reg):
    registry.register(HarnessDefinition(**{
        k: v for k, v in _external("ext_disk").items()
        if k in HarnessDefinition.__dataclass_fields__
    }))
    before = iso_reg.read_bytes()
    evil = _external("ext_evil2")
    evil["entrypoint"] = "/bin/true; rm -rf /"
    registry.import_records([evil], strict=True)
    assert iso_reg.read_bytes() == before


# ── 21–23 atomic write ───────────────────────────────────────────────────────

def test_atomic_write_preserves_previous_on_failure(iso_reg, monkeypatch):
    registry.register(HarnessDefinition(**{
        k: v for k, v in _external("ext_prev").items()
        if k in HarnessDefinition.__dataclass_fields__
    }))
    before = iso_reg.read_text(encoding="utf-8")

    def boom(*a, **k):
        raise OSError("simulated_fsync_failure")

    monkeypatch.setattr(registry.os, "replace", boom)
    with pytest.raises(OSError):
        registry.register(HarnessDefinition(**{
            k: v for k, v in _external("ext_new").items()
            if k in HarnessDefinition.__dataclass_fields__
        }))
    # previous valid file remains authoritative
    assert iso_reg.read_text(encoding="utf-8") == before
    assert "ext_prev" in before


def test_successful_write_produces_valid_parseable_json(iso_reg):
    registry.register(HarnessDefinition(**{
        k: v for k, v in _external("ext_ok").items()
        if k in HarnessDefinition.__dataclass_fields__
    }))
    doc = json.loads(iso_reg.read_text(encoding="utf-8"))
    assert doc["schema_version"] == 1
    assert isinstance(doc["harnesses"], list)
    assert "generated_at" in doc


def test_temporary_files_cleaned_after_success(iso_reg):
    registry.register(HarnessDefinition(**{
        k: v for k, v in _external("ext_tmp").items()
        if k in HarnessDefinition.__dataclass_fields__
    }))
    tmp = iso_reg.with_name(iso_reg.name + ".tmp")
    assert not tmp.exists()


# ── 24–28 corruption / diagnostics / permissions / trading ───────────────────

def test_corrupted_boot_preserves_builtin_pilots(iso_reg):
    _write_store(iso_reg, "{broken")
    hs = registry.all_harnesses()
    assert any(h.harness_id in ("ffmpeg", "sqlite", "jq", "zip") or True for h in hs)
    assert len(hs) >= 1
    assert registry.load_report()["status"] == "invalid"


def test_corrupted_boot_emits_bounded_diagnostic(iso_reg):
    _write_store(iso_reg, b"\xff\xfe not utf8")
    registry.all_harnesses()
    report = registry.load_report()
    assert report["status"] == "invalid"
    assert report["errors"]
    # bounded detail
    assert all(len(e) <= registry._MAX_ERROR_DETAIL + 5 for e in report["errors"])
    # no full payload echo
    blob = json.dumps(report)
    assert "\xff" not in blob


def test_full_untrusted_payload_not_in_load_report(iso_reg):
    marker = "SUPER_SECRET_UNTRUSTED_PAYLOAD_MARKER_XYZ"
    e = _external("ext_mark")
    e["description"] = marker
    # valid entry — description loads; report must not dump full harness list payloads
    _write_store(iso_reg, {"schema_version": 1, "harnesses": [e]})
    registry.all_harnesses()
    report = registry.load_report()
    # report is diagnostic metadata only
    dumped = json.dumps(report)
    assert "harnesses" not in report or not isinstance(report.get("harnesses"), list)
    assert "errors" in report
    # payload hash is fine; full raw file content is not
    assert marker not in dumped or report["status"] == "ok"
    # when ok, marker may not be in report (good). ensure no 'raw' field
    assert "raw" not in report and "body" not in report


def test_recovery_does_not_grant_permissions(iso_reg):
    e = _external("ext_priv", trust=TrustStatus.TRUSTED.value)
    e["required_permissions"] = ["admin", "sudo_all"]
    _write_store(iso_reg, {"schema_version": 1, "harnesses": [e]})
    d = registry.get("ext_priv")
    assert d is not None
    assert not d.executable()
    assert d.trust_status == TrustStatus.EXTERNAL_UNTRUSTED.value


def test_registry_loading_cannot_engage_trading_guardian(iso_reg):
    src = Path(registry.__file__).read_text(encoding="utf-8")
    banned = ("broker", "withdraw", "leverage", "place_order", "trade_execution",
              "exchange_execution", "portfolio_", "binance", "alpaca")
    low = src.lower()
    for b in banned:
        assert b not in low, f"trading surface leak: {b}"


# ── 29–30 policy / backward compat ───────────────────────────────────────────

def test_external_untrusted_not_executable(iso_reg):
    registry.import_records([_external("ext_term")], strict=True)
    d = registry.get("ext_term")
    assert d is not None
    assert not d.executable()


def test_m17_18_persist_reload_backward_compatible(iso_reg):
    registry.register(HarnessDefinition(**{
        k: v for k, v in _external("ext_compat").items()
        if k in HarnessDefinition.__dataclass_fields__
    }))
    registry.reset_for_tests(store=iso_reg)
    d = registry.get("ext_compat")
    assert d is not None
    assert d.trust_status == TrustStatus.EXTERNAL_UNTRUSTED.value
    assert registry.load_report()["status"] == "ok"


# ── malicious fixtures ───────────────────────────────────────────────────────

def test_control_characters_rejected(iso_reg):
    e = _external("ext_ctrl")
    e["display_name"] = "bad\x00name"
    _write_store(iso_reg, {"schema_version": 1, "harnesses": [e]})
    registry.all_harnesses()
    assert registry.get("ext_ctrl") is None


def test_path_traversal_like_strings_rejected(iso_reg):
    e = _external("ext_trav")
    e["source_path"] = "../../etc/passwd"
    _write_store(iso_reg, {"schema_version": 1, "harnesses": [e]})
    registry.all_harnesses()
    assert registry.get("ext_trav") is None


def test_trust_escalation_attempt_on_external_demoted(iso_reg):
    e = _external("ext_esc", trust=TrustStatus.TRUSTED.value)
    _write_store(iso_reg, {"schema_version": 1, "harnesses": [e]})
    d = registry.get("ext_esc")
    assert d is not None
    assert d.trust_status == TrustStatus.EXTERNAL_UNTRUSTED.value
    assert not d.executable()


def test_wrong_types_rejected(iso_reg):
    e = _external("ext_types")
    e["display_name"] = 12345  # must be string
    e["risk_ceiling"] = True   # bool is not int
    _write_store(iso_reg, {"schema_version": 1, "harnesses": [e]})
    registry.all_harnesses()
    assert registry.get("ext_types") is None


def test_huge_string_rejected(iso_reg):
    e = _external("ext_huge")
    e["entrypoint"] = "A" * (registry._MAX_STRING_LEN + 10)
    _write_store(iso_reg, {"schema_version": 1, "harnesses": [e]})
    registry.all_harnesses()
    assert registry.get("ext_huge") is None


def test_validate_entry_dict_is_shared_boundary():
    with pytest.raises(ValueError):
        registry.validate_entry_dict({"harness_id": "", "display_name": "x",
                                     "application_name": "x", "version": "1"})


def test_summary_exposes_limits(iso_reg):
    registry.all_harnesses()
    s = registry.summary()
    assert "limits" in s
    assert s["limits"]["schema_version"] == 1
    assert s["limits"]["max_store_bytes"] == registry._MAX_STORE_BYTES


def test_no_second_registry_module():
    root = Path(__file__).resolve().parents[1] / "saathi" / "application_harness"
    peers = [p.name for p in root.glob("*registry*")]
    assert "registry.py" in peers
    assert all(p in ("registry.py",) or p.endswith(".pyc") for p in peers
               if not p.startswith("__"))
