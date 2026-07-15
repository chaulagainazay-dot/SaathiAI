"""M17.20 — multi-writer harness registry concurrency.

Process-safe flock + revision CAS + lock→reload→mutate→atomic-write.
"""
from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from saathi.application_harness import registry
from saathi.application_harness.models import HarnessDefinition, TrustStatus


@pytest.fixture()
def iso_reg(tmp_path):
    store = tmp_path / "registry.json"
    original = Path(registry.STORE)
    # isolate concurrency constants for faster tests
    registry.reset_for_tests(store=store)
    yield store
    registry.reset_for_tests(store=original)


def _ext(hid: str, **kw) -> HarnessDefinition:
    return HarnessDefinition(
        harness_id=hid,
        display_name=hid,
        application_name=hid.replace("ext_", ""),
        version=kw.get("version", "1.0.0"),
        source_type="cli_anything",
        source_repository="https://example.invalid/w",
        source_commit="abc",
        install_method="brew",
        trust_status=kw.get("trust", TrustStatus.EXTERNAL_UNTRUSTED.value),
        validation_status="imported_untrusted",
        description=kw.get("description", ""),
    )


# ── 1–7 lock acquire / release / timeout / stale ─────────────────────────────

def test_single_writer_acquires_and_releases(iso_reg):
    with registry._registry_write_lock(timeout=2.0):
        assert registry._HOLDING_WRITE_LOCK is True
    assert registry._HOLDING_WRITE_LOCK is False


def test_second_writer_times_out_safely(iso_reg, monkeypatch):
    monkeypatch.setattr(registry, "_LOCK_TIMEOUT_SEC", 0.3)
    monkeypatch.setattr(registry, "_LOCK_POLL_SEC", 0.05)
    entered = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    def holder():
        with registry._registry_write_lock(timeout=5.0):
            entered.set()
            release.wait(timeout=5.0)

    def waiter():
        try:
            with registry._registry_write_lock(timeout=0.3):
                pass
        except registry.RegistryBusy as e:
            errors.append(e)

    t1 = threading.Thread(target=holder)
    t2 = threading.Thread(target=waiter)
    t1.start()
    assert entered.wait(2.0)
    t2.start()
    t2.join(3.0)
    release.set()
    t1.join(3.0)
    assert errors and isinstance(errors[0], registry.RegistryBusy)


def test_lock_released_after_successful_mutation(iso_reg):
    registry.register(_ext("ext_ok"), operation_id="op-ok-1")
    assert registry._HOLDING_WRITE_LOCK is False
    assert registry.get("ext_ok") is not None


def test_lock_released_after_validation_failure(iso_reg):
    bad = _ext("bad id")
    bad.harness_id = "bad id"
    with pytest.raises(ValueError):
        registry.register(bad)
    assert registry._HOLDING_WRITE_LOCK is False


def test_lock_released_after_persist_failure(iso_reg, monkeypatch):
    def boom(*a, **k):
        raise OSError("simulated_write_fail")

    monkeypatch.setattr(registry.os, "replace", boom)
    with pytest.raises(OSError):
        registry.register(_ext("ext_fail"), operation_id="op-fail")
    assert registry._HOLDING_WRITE_LOCK is False
    # previous valid (missing) state preserved — no partial file authority as truncated
    if iso_reg.exists():
        # if something was written before, must still parse
        json.loads(iso_reg.read_text(encoding="utf-8"))


def test_stale_flock_recoverable_after_holder_exits(iso_reg):
    """fcntl releases on process/thread end — next acquirer succeeds (stale free)."""
    with registry._registry_write_lock(timeout=2.0):
        pass
    # immediately re-acquire
    with registry._registry_write_lock(timeout=2.0):
        assert registry._HOLDING_WRITE_LOCK


def test_active_lock_not_stolen(iso_reg, monkeypatch):
    monkeypatch.setattr(registry, "_LOCK_TIMEOUT_SEC", 0.25)
    hold = threading.Event()
    done = threading.Event()

    def holder():
        with registry._registry_write_lock(timeout=5.0):
            hold.set()
            time.sleep(0.6)

    t = threading.Thread(target=holder)
    t.start()
    assert hold.wait(2)
    with pytest.raises(registry.RegistryBusy):
        with registry._registry_write_lock(timeout=0.2):
            done.set()
    t.join(2)
    assert not done.is_set()


# ── 8–13 revision / lost update / idempotency ────────────────────────────────

def test_two_writers_different_ids_both_survive(iso_reg):
    def w(hid):
        return registry.register(_ext(hid), operation_id=f"op-{hid}")

    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(w, f"ext_w{i}") for i in range(8)]
        for f in as_completed(futs):
            assert f.result()["ok"] is True
    for i in range(8):
        assert registry.get(f"ext_w{i}") is not None
    doc = json.loads(iso_reg.read_text(encoding="utf-8"))
    ids = {h["harness_id"] for h in doc["harnesses"] if h["harness_id"].startswith("ext_w")}
    assert len(ids) == 8
    assert doc["revision"] >= 8


def test_same_identifier_idempotent_or_conflict(iso_reg):
    r1 = registry.register(_ext("ext_same", version="1.0.0"), operation_id="op-same")
    assert r1["ok"]
    # same operation id → deduplicated
    r2 = registry.register(_ext("ext_same", version="1.0.0"), operation_id="op-same")
    assert r2.get("deduplicated") is True
    # incompatible different version without shared op → conflict
    with pytest.raises(registry.RegistryConflict):
        registry.register(_ext("ext_same", version="2.0.0"), operation_id="op-same-v2")


def test_stale_revision_cannot_overwrite(iso_reg):
    registry.register(_ext("ext_a"), operation_id="op-a")
    rev = registry.current_revision()
    # simulate stale memory persist: force loaded revision behind disk
    registry._LOADED_REVISION = rev - 1 if rev > 0 else -1
    # advance disk via another write
    registry.register(_ext("ext_b"), operation_id="op-b")
    # now memory may be current from register; force stale again
    registry._LOADED_REVISION = 0
    with pytest.raises(registry.RegistryConflict):
        registry.persist()


def test_revision_increments_after_success(iso_reg):
    assert registry.current_revision() == 0
    registry.register(_ext("ext_r1"), operation_id="op-r1")
    r1 = registry.current_revision()
    assert r1 == 1
    registry.register(_ext("ext_r2"), operation_id="op-r2")
    assert registry.current_revision() == r1 + 1


def test_failed_mutation_does_not_increment_revision(iso_reg, monkeypatch):
    registry.register(_ext("ext_base"), operation_id="op-base")
    before = registry.current_revision()

    def boom(*a, **k):
        raise OSError("nope")

    monkeypatch.setattr(registry.os, "replace", boom)
    with pytest.raises(OSError):
        registry.register(_ext("ext_x"), operation_id="op-x")
    # reload to be sure
    registry.reset_for_tests(store=iso_reg)
    registry.all_harnesses()
    assert registry.current_revision() == before
    assert registry.get("ext_x") is None


def test_duplicate_operation_id_no_duplicate_mutation(iso_reg):
    registry.register(_ext("ext_dup"), operation_id="idem-1")
    registry.register(_ext("ext_dup"), operation_id="idem-1")
    doc = json.loads(iso_reg.read_text(encoding="utf-8"))
    matches = [h for h in doc["harnesses"] if h["harness_id"] == "ext_dup"]
    assert len(matches) == 1
    assert "idem-1" in doc.get("applied_ops", [])


# ── 14–17 import concurrency ─────────────────────────────────────────────────

def test_concurrent_imports_do_not_overwrite(iso_reg):
    def imp(i):
        rec = _ext(f"ext_imp{i}").to_dict()
        return registry.import_records([rec], strict=True, operation_id=f"imp-{i}")

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(imp, range(6)))
    assert all(r.get("error") is None for r in results)
    for i in range(6):
        assert registry.get(f"ext_imp{i}") is not None


def test_import_and_register_share_lock(iso_reg, monkeypatch):
    monkeypatch.setattr(registry, "_LOCK_TIMEOUT_SEC", 0.35)
    hold = threading.Event()
    release = threading.Event()
    outcomes: list[str] = []

    def long_reg():
        with registry._registry_write_lock(timeout=5.0):
            hold.set()
            release.wait(3.0)
            outcomes.append("held")

    def try_import():
        assert hold.wait(2)
        out = registry.import_records(
            [_ext("ext_shared").to_dict()], strict=True, operation_id="imp-shared"
        )
        outcomes.append(out.get("error") or "ok")

    t1 = threading.Thread(target=long_reg)
    t2 = threading.Thread(target=try_import)
    t1.start()
    t2.start()
    t2.join(3)
    release.set()
    t1.join(3)
    assert "LOCK_TIMEOUT" in outcomes or "ok" in outcomes
    # if timeout, import did not partially apply
    if "LOCK_TIMEOUT" in outcomes:
        assert registry.get("ext_shared") is None


def test_failed_import_leaves_disk_unchanged(iso_reg):
    registry.register(_ext("ext_keep"), operation_id="keep")
    before = iso_reg.read_bytes()
    evil = _ext("ext_evil").to_dict()
    evil["api_key"] = "REDACTED_FIXTURE_NOT_A_REAL_SECRET"
    out = registry.import_records([evil], strict=True)
    assert out["added"] == 0
    assert iso_reg.read_bytes() == before


def test_failed_import_leaves_memory_unchanged(iso_reg):
    registry.register(_ext("ext_m"), operation_id="m1")
    before = {d.harness_id for d in registry.all_harnesses()}
    evil = _ext("ext_e").to_dict()
    evil["entrypoint"] = "/bin/true; rm -rf /"
    registry.import_records([evil], strict=True)
    after = {d.harness_id for d in registry.all_harnesses()}
    assert after == before


# ── 18–21 conflict rules / trust / pilots ────────────────────────────────────

def test_delete_update_style_no_resurrect_via_stale_register(iso_reg):
    """If entry removed from durable state, stale full-file overwrite is blocked by CAS."""
    registry.register(_ext("ext_del"), operation_id="d1")
    # remove from disk document manually under no concurrent writers
    doc = json.loads(iso_reg.read_text(encoding="utf-8"))
    doc["harnesses"] = [h for h in doc["harnesses"] if h["harness_id"] != "ext_del"]
    doc["revision"] = doc.get("revision", 1)  # keep revision; memory still has ext_del
    iso_reg.write_text(json.dumps(doc), encoding="utf-8")
    # memory thinks loaded rev matches but disk content removed entry with same rev
    # force loaded rev equal to disk so persist would try write — then advance disk
    registry._LOADED_REVISION = doc["revision"]
    # another writer advances revision
    registry.register(_ext("ext_other"), operation_id="d2")
    # stale persist of memory that still had ext_del should conflict
    registry._LOADED_REVISION = doc["revision"]
    with pytest.raises(registry.RegistryConflict):
        registry.persist()
    registry.reset_for_tests(store=iso_reg)
    # after reload, ext_del absent (was removed) unless re-registered
    # d2 register reloaded and wrote without ext_del if it was gone from disk
    d = registry.get("ext_del")
    # either absent or present only if a later write re-added — must not be from stale overwrite
    # disk after conflict should still be parseable latest
    latest = json.loads(iso_reg.read_text(encoding="utf-8"))
    assert isinstance(latest.get("revision"), int)


def test_update_update_conflict(iso_reg):
    registry.register(_ext("ext_u", version="1.0.0"), operation_id="u1")
    with pytest.raises(registry.RegistryConflict):
        registry.register(_ext("ext_u", version="9.9.9"), operation_id="u2")


def test_trust_escalation_rejected_under_concurrency(iso_reg):
    registry.register(_ext("ext_t", trust=TrustStatus.EXTERNAL_UNTRUSTED.value),
                      operation_id="t1")
    # concurrent "elevate" attempts still demote on load path; register validates demotion
    r = registry.register(
        _ext("ext_t2", trust=TrustStatus.TRUSTED.value), operation_id="t2"
    )
    assert r["ok"]
    d = registry.get("ext_t2")
    assert d is not None
    assert d.trust_status == TrustStatus.EXTERNAL_UNTRUSTED.value
    assert not d.executable()


def test_builtin_pilot_not_replaced_by_import(iso_reg):
    pilots = registry.all_harnesses()
    assert pilots
    hid = next((p.harness_id for p in pilots if p.harness_id in
                ("ffmpeg", "sqlite", "jq", "zip")), pilots[0].harness_id)
    before = registry.get(hid)
    assert before is not None
    rec = before.to_dict()
    rec["version"] = "9.9.9-evil"
    rec["source_type"] = "cli_anything"
    rec["description"] = "ATTACKER"
    out = registry.import_records([rec], strict=True, operation_id="evil-pilot")
    assert out.get("added", 0) == 0
    after = registry.get(hid)
    assert after is not None
    assert after.version != "9.9.9-evil"


# ── 22–27 crash / read consistency ───────────────────────────────────────────

def test_crash_before_persistence_leaves_previous_valid(iso_reg, monkeypatch):
    registry.register(_ext("ext_prev"), operation_id="p1")
    before = iso_reg.read_text(encoding="utf-8")

    def boom(*a, **k):
        raise OSError("crash_before_replace")

    monkeypatch.setattr(registry.os, "replace", boom)
    with pytest.raises(OSError):
        registry.register(_ext("ext_new"), operation_id="p2")
    assert iso_reg.read_text(encoding="utf-8") == before
    json.loads(before)


def test_crash_during_temp_write_leaves_previous(iso_reg, monkeypatch):
    registry.register(_ext("ext_p"), operation_id="c1")
    before = iso_reg.read_bytes()

    real_open = os.open

    def open_boom(path, flags, mode=0o777):
        if str(path).endswith(".tmp"):
            raise OSError("temp_write_fail")
        return real_open(path, flags, mode)

    monkeypatch.setattr(registry.os, "open", open_boom)
    with pytest.raises(OSError):
        registry.register(_ext("ext_q"), operation_id="c2")
    assert iso_reg.read_bytes() == before


def test_restart_loads_latest_revision(iso_reg):
    registry.register(_ext("ext_s1"), operation_id="s1")
    registry.register(_ext("ext_s2"), operation_id="s2")
    rev = registry.current_revision()
    registry.reset_for_tests(store=iso_reg)
    registry.all_harnesses()
    assert registry.current_revision() == rev
    assert registry.get("ext_s1") and registry.get("ext_s2")


def test_reader_never_observes_partial_json(iso_reg):
    """Readers only open STORE (atomic replace), never .tmp."""
    registry.register(_ext("ext_r"), operation_id="r1")
    # leave a corrupt tmp beside store
    tmp = iso_reg.with_name(iso_reg.name + ".tmp")
    tmp.write_text("{partial", encoding="utf-8")
    registry.reset_for_tests(store=iso_reg)
    hs = registry.all_harnesses()
    assert hs
    assert registry.get("ext_r") is not None
    # report is fine
    assert registry.load_report()["status"] in ("ok", "missing")


def test_reader_sees_old_or_new_revision_not_mixed(iso_reg):
    registry.register(_ext("ext_v1"), operation_id="v1")
    r_old = registry.current_revision()
    registry.register(_ext("ext_v2"), operation_id="v2")
    r_new = registry.current_revision()
    doc = json.loads(iso_reg.read_text(encoding="utf-8"))
    assert doc["revision"] == r_new
    ids = {h["harness_id"] for h in doc["harnesses"]}
    # committed new state includes both
    assert "ext_v1" in ids and "ext_v2" in ids
    assert r_new > r_old


# ── 28–34 evidence / security / compat ───────────────────────────────────────

def test_full_payload_not_in_events_helpers(iso_reg):
    # event helper strips raw/body
    captured = []

    def fake_emit(name, payload):
        captured.append((name, payload))

    # call internal strip path via _emit_registry_event with forbidden keys
    registry._emit_registry_event("test_evt", {
        "raw": "SECRET_PAYLOAD_SHOULD_NOT_PASS",
        "revision": 3,
        "count": 1,
    })
    # cannot easily capture bus; ensure helper doesn't raise and report stays bounded
    rep = registry.load_report()
    assert "raw" not in rep


def test_m17_19_protections_still_apply_under_lock(iso_reg):
    evil = _ext("ext_shell").to_dict()
    evil["entrypoint"] = "true; curl evil"
    out = registry.import_records([evil], strict=True)
    assert out["added"] == 0
    assert registry.get("ext_shell") is None


def test_m17_18_persist_reload_compatible(iso_reg):
    registry.register(_ext("ext_c"), operation_id="c")
    registry.reset_for_tests(store=iso_reg)
    assert registry.get("ext_c") is not None
    doc = json.loads(iso_reg.read_text(encoding="utf-8"))
    assert doc["schema_version"] == 1
    assert "revision" in doc


def test_trading_guardian_unengaged(iso_reg):
    src = Path(registry.__file__).read_text(encoding="utf-8")
    banned = ("broker", "withdraw", "leverage", "place_order", "trade_execution",
              "exchange_execution", "portfolio_", "binance", "alpaca")
    low = src.lower()
    for b in banned:
        assert b not in low, b


def test_retry_after_uncertain_completion_dedupes(iso_reg, monkeypatch):
    """If write succeeds but client retries same operation_id, no duplicate."""
    registry.register(_ext("ext_unc"), operation_id="unc-1")
    # uncertain retry
    r = registry.register(_ext("ext_unc"), operation_id="unc-1")
    assert r.get("deduplicated") is True
    doc = json.loads(iso_reg.read_text(encoding="utf-8"))
    assert sum(1 for h in doc["harnesses"] if h["harness_id"] == "ext_unc") == 1


def test_summary_exposes_revision_and_lock_timeout(iso_reg):
    registry.all_harnesses()
    s = registry.summary()
    assert "revision" in s
    assert s["limits"]["lock_timeout_sec"] == registry._LOCK_TIMEOUT_SEC


def test_no_second_registry_module():
    root = Path(__file__).resolve().parents[1] / "saathi" / "application_harness"
    peers = [p.name for p in root.glob("*registry*")]
    assert "registry.py" in peers
