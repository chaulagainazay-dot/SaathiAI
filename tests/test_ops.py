"""M13.5 operations test suite — identity, config, storage, cleanup, db
integrity, REAL backup+restore, release gate, process/stale detection.

Backup/restore tests genuinely create and restore real SQLite dbs into
isolated temp dirs and verify checksums + integrity — not mocked."""
import sqlite3
from pathlib import Path

import pytest

from saathi.ops import identity, storage, db_integrity, config_check, backup, process
from saathi.ops import release_gate as RG


# ── runtime identity / version compat (unit) ────────────────────────────────
def test_identity_exposes_safe_fields_only():
    ident = identity.identity(route_count=304)
    assert set(ident) >= {"commit", "api_version", "schema_versions",
                          "route_manifest_version", "route_count"}
    # never leak secrets/paths
    blob = str(ident).lower()
    assert "token" not in blob and "/users/" not in blob and "key" not in blob


def test_version_compat_matching():
    r = identity.compatible(identity.API_VERSION, identity.ROUTE_MANIFEST_VERSION)
    assert r["compatible"]


def test_version_compat_stale_frontend_major():
    r = identity.compatible("0.9", identity.ROUTE_MANIFEST_VERSION)
    assert not r["compatible"] and "major" in r["reason"]


def test_version_compat_route_manifest_mismatch():
    r = identity.compatible(identity.API_VERSION, "m8")
    assert not r["compatible"] and "route manifest" in r["reason"]


def test_version_compat_missing_info():
    r = identity.compatible("", "")
    assert not r["compatible"]


# ── config check (unit) ─────────────────────────────────────────────────────
def test_config_check_redacts_secrets():
    c = config_check.check_config()
    for item in c["items"]:
        if item["key"] in ("SAATHI_TOKEN", "ANTHROPIC_API_KEY"):
            assert item["value"] in ("PRESENT", "ABSENT")  # never the real value
    assert "ok" in c


def test_config_check_flags_tracked_firebase_key():
    c = config_check.check_config()
    fb = [i for i in c["items"] if i["key"] == "firebase_key_untracked"][0]
    assert fb["status"] == "valid"  # confirmed untracked (Repair 0)


# ── storage / cleanup (unit) ────────────────────────────────────────────────
def test_storage_report_levels():
    r = storage.storage_report()
    assert r["level"] in ("ok", "warning", "block", "critical")
    assert "free_gb" in r and "thresholds" in r


def test_allow_heavy_task_respects_threshold(monkeypatch):
    monkeypatch.setattr(storage, "free_gb", lambda: 1.0)  # below block
    ok, reason = storage.allow_heavy_task()
    assert not ok and "block" in reason
    monkeypatch.setattr(storage, "free_gb", lambda: 50.0)
    assert storage.allow_heavy_task()[0]


def test_cleanup_is_preview_first(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path)
    # create a temp file in a fake project tmp dir
    proj = tmp_path / "studio_workspaces" / "p1" / "tmp"
    proj.mkdir(parents=True)
    f = proj / "junk.tmp"
    f.write_text("x")
    import os, time
    old = time.time() - 7200
    os.utime(f, (old, old))
    preview = storage.run_cleanup(apply=False, temp_older_sec=3600)
    assert preview["candidates"] >= 1 and preview["removed"] == 0
    assert f.exists()  # preview never deletes
    applied = storage.run_cleanup(apply=True, temp_older_sec=3600)
    assert applied["removed"] >= 1 and not f.exists()


# ── db integrity (real) ─────────────────────────────────────────────────────
def test_db_integrity_ok_on_real_db(tmp_path):
    p = tmp_path / "t.db"
    c = sqlite3.connect(str(p))
    c.execute("CREATE TABLE x(a)")
    c.execute("INSERT INTO x VALUES(1)")
    c.commit(); c.close()
    r = db_integrity.check_db(p)
    assert r["ok"] and r["integrity"] == "ok" and r["tables"] == 1


def test_db_integrity_detects_corruption(tmp_path):
    p = tmp_path / "bad.db"
    p.write_bytes(b"this is not a sqlite database at all")
    r = db_integrity.check_db(p)
    assert not r["ok"]


def test_db_integrity_missing_db_ok(tmp_path):
    r = db_integrity.check_db(tmp_path / "nope.db")
    assert r["ok"] and not r["present"]


# ── REAL backup + restore drill (integration) ───────────────────────────────
@pytest.fixture
def fake_data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    for name in ("chat.db", "memory.db"):
        c = sqlite3.connect(str(d / name))
        c.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
        c.execute("INSERT INTO t(v) VALUES('hello')")
        c.commit(); c.close()
    return d


def test_real_backup_and_restore_roundtrip(fake_data_dir, tmp_path):
    dest = tmp_path / "backups"
    res = backup.create_backup(data_dir=fake_data_dir, dest_dir=dest, label="test")
    assert res["databases"] == 2 and Path(res["archive"]).exists()

    target = tmp_path / "restore"
    r = backup.restore_backup(res["archive"], target=target)
    v = backup.verify_restore(r["restored_to"])
    assert v["ok"]  # checksums + integrity all pass
    assert all(x == "match" for x in v["details"]["checksums"].values())
    # restored db is genuinely queryable
    restored_db = Path(r["restored_to"]) / "chat.db"
    c = sqlite3.connect(str(restored_db))
    assert c.execute("SELECT v FROM t").fetchone()[0] == "hello"
    c.close()


def test_backup_excludes_secrets(fake_data_dir, tmp_path):
    # a stray .env in the data dir must NOT be included
    (fake_data_dir / ".env").write_text("SECRET=abc")
    res = backup.create_backup(data_dir=fake_data_dir, dest_dir=tmp_path / "b")
    import tarfile
    with tarfile.open(res["archive"]) as tar:
        names = tar.getnames()
    assert not any(".env" in n for n in names)


def test_restore_refuses_over_live_data(fake_data_dir, tmp_path):
    res = backup.create_backup(data_dir=fake_data_dir, dest_dir=tmp_path / "b")
    with pytest.raises(RuntimeError):
        backup.restore_backup(res["archive"], target=backup.DATA)


def test_restore_rejects_path_traversal_archive(tmp_path):
    # a malicious archive with a ../ member must be refused
    import tarfile, io
    arc = tmp_path / "evil.tar.gz"
    with tarfile.open(arc, "w:gz") as tar:
        data = b"pwn"
        info = tarfile.TarInfo("../escape.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    with pytest.raises(RuntimeError):
        backup.restore_backup(arc, target=tmp_path / "t")


def test_verify_restore_detects_checksum_mismatch(fake_data_dir, tmp_path):
    res = backup.create_backup(data_dir=fake_data_dir, dest_dir=tmp_path / "b")
    target = tmp_path / "r"
    r = backup.restore_backup(res["archive"], target=target)
    # tamper with a restored db
    tampered = Path(r["restored_to"]) / "chat.db"
    tampered.write_bytes(tampered.read_bytes() + b"tamper")
    v = backup.verify_restore(r["restored_to"])
    assert not v["ok"]


# ── release gate (unit + integration) ───────────────────────────────────────
def test_release_gate_exit_codes_defined():
    assert RG.EXIT_READY == 0 and RG.EXIT_SECURITY == 3 and RG.EXIT_VERSION == 10


def test_release_gate_storage_block(monkeypatch):
    monkeypatch.setattr("saathi.ops.storage.free_gb", lambda: 1.0)
    code, report = RG.release_check(run_backup=False, run_secret_scan=False,
                                    run_db=False)
    assert code == RG.EXIT_STORAGE


def test_release_gate_config_block(monkeypatch):
    monkeypatch.setattr(RG, "release_check", RG.release_check)  # keep ref
    from saathi.ops import config_check as CC
    monkeypatch.setattr(CC, "check_config",
                        lambda: {"ok": False, "blocking": 1, "warnings": 0, "items": []})
    code, _ = RG.release_check(run_backup=False, run_secret_scan=False, run_db=False,
                              run_storage=False)
    assert code == RG.EXIT_CONFIG


def test_release_gate_passes_baseline():
    # real run of the safe gates (storage/config/db/backup/secret) — should pass
    code, report = RG.release_check(strict_dirty=False)
    assert code in (RG.EXIT_READY, RG.EXIT_WARN)
    assert report["gates"]["backup_restore"]["restore_verified"] is True
    assert report["gates"]["secret_scan"]["clean"] is True


# ── process / stale detection (unit) ────────────────────────────────────────
def test_backend_status_shape():
    s = process.backend_status(port=59999)  # nothing listening here
    assert "listening" in s and "working_tree_commit" in s and "duplicate" in s


# ── CLI ─────────────────────────────────────────────────────────────────────
def test_cli_read_only_commands():
    from saathi.ops import cli
    assert cli.main(["identity"]) == 0
    assert cli.main(["storage"]) in (0, 9)
    assert cli.main(["config-check"]) in (0, 4)
    assert cli.main(["db-check"]) in (0, 5)
    assert cli.main(["bogus"]) == 2


def test_cli_cleanup_preview_default():
    from saathi.ops import cli
    # default cleanup is preview (apply=False) — exit 0, no mutation claim
    assert cli.main(["cleanup"]) == 0
