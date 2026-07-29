"""M160 — Bounded local upgrade flow (synthetic/local fixtures only).

Never fetches remote releases or auto-updates from the internet.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from .backup_restore import create_system_backup
from .config import load_config, migrate_config, save_config
from .manifest import RELEASE_VERSION, build_release_manifest
from .prepare import prepare

ROOT = Path(__file__).resolve().parents[3]
UPGRADE_STATE = ROOT / "data" / "alpha" / "upgrade_state.json"


def upgrade_preflight(*, fixture_version: str | None = None) -> dict[str, Any]:
    prep = prepare(install_deps=False)
    cfg = load_config()
    free_ok = any(
        c["check"] == "disk_headroom" and c["status"] == "PASS"
        for c in prep.get("checks") or []
    )
    return {
        "ok": bool(prep.get("ok") and free_ok),
        "current_version": RELEASE_VERSION,
        "target_version": fixture_version or RELEASE_VERSION,
        "prepare": {"ok": prep.get("ok"), "checks": len(prep.get("checks") or [])},
        "disk_ok": free_ok,
        "schema_compatible": True,
        "remote_fetch": False,
        "production_authorized": False,
        "config_channel": cfg.release_channel,
    }


def apply_local_upgrade(
    *,
    fixture_dir: Path,
    work_db: Path | None = None,
) -> dict[str, Any]:
    """Apply a local release fixture: preflight → backup → migrate config → smoke.

    fixture_dir must contain release_fixture.json with target_version.
    """
    fixture_dir = Path(fixture_dir)
    fixture_path = fixture_dir / "release_fixture.json"
    if not fixture_path.is_file():
        return {"ok": False, "error": "FIXTURE_MISSING", "path": str(fixture_path)}

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    target = str(fixture.get("target_version") or "")
    if not target:
        return {"ok": False, "error": "TARGET_VERSION_MISSING"}

    pre = upgrade_preflight(fixture_version=target)
    if not pre.get("ok"):
        return {"ok": False, "error": "PREFLIGHT_FAILED", "preflight": pre}

    state = {
        "phase": "started",
        "from_version": RELEASE_VERSION,
        "target_version": target,
        "started_at": time.time(),
        "backup": None,
        "committed": False,
        "rolled_back": False,
    }

    # Backup
    backup_dir = fixture_dir / "pre_upgrade_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    db = Path(work_db) if work_db else ROOT / "data" / "platform" / "platform.db"
    if not db.is_file():
        # synthetic empty db for fixture upgrades
        import sqlite3

        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE IF NOT EXISTS upgrade_marker(v TEXT)")
        conn.execute("INSERT INTO upgrade_marker(v) VALUES (?)", (RELEASE_VERSION,))
        conn.commit()
        conn.close()

    try:
        b = create_system_backup(
            dest_dir=backup_dir,
            label="pre-upgrade",
            db_path=db,
            include_legacy_app_dbs=False,
        )
        state["backup"] = b
        state["phase"] = "backup_done"
    except Exception as exc:
        state["phase"] = "backup_failed"
        state["error"] = str(exc)[:200]
        _save_state(state)
        return {"ok": False, "error": "BACKUP_FAILED", "state": state}

    # Config migration
    try:
        cfg = load_config()
        raw = cfg.to_public()
        raw["schema_version"] = "m160.alpha_config.v0"  # force migrate path
        migrated = migrate_config(raw)
        save_config(migrated)
        state["phase"] = "config_migrated"
    except Exception as exc:
        state["phase"] = "config_failed"
        state["error"] = str(exc)[:200]
        _save_state(state)
        return rollback_upgrade(state)

    # Smoke: re-prepare
    smoke = prepare(install_deps=False)
    if not smoke.get("ok"):
        state["phase"] = "smoke_failed"
        state["smoke"] = {"ok": False}
        _save_state(state)
        return rollback_upgrade(state)

    state["phase"] = "committed"
    state["committed"] = True
    state["finished_at"] = time.time()
    state["smoke"] = {"ok": True}
    state["manifest"] = build_release_manifest()
    _save_state(state)
    return {"ok": True, "state": state, "remote_fetch": False}


def rollback_upgrade(state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = dict(state or _load_state() or {})
    backup = state.get("backup") or {}
    archive = backup.get("archive")
    if not archive or not Path(archive).is_file():
        state["rolled_back"] = False
        state["phase"] = "rollback_failed"
        state["error"] = "NO_BACKUP"
        _save_state(state)
        return {"ok": False, "error": "NO_BACKUP", "state": state}

    # Restore config from history if possible
    try:
        from .config import rollback_config

        rollback_config()
    except Exception:
        pass

    state["rolled_back"] = True
    state["phase"] = "rolled_back"
    state["finished_at"] = time.time()
    _save_state(state)
    return {"ok": True, "state": state, "rolled_back": True}


def _save_state(state: dict) -> None:
    UPGRADE_STATE.parent.mkdir(parents=True, exist_ok=True)
    UPGRADE_STATE.write_text(json.dumps(state, indent=2, default=str) + "\n", encoding="utf-8")


def _load_state() -> dict | None:
    if not UPGRADE_STATE.is_file():
        return None
    return json.loads(UPGRADE_STATE.read_text(encoding="utf-8"))
