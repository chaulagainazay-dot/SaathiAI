"""M161 — Full-system private-alpha backup and restore.

Extends ops/backup patterns for PlatformStore + alpha config + release manifest.
Never includes raw secrets, API keys, cookies, or unrestricted env dumps.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import tarfile
import time
from pathlib import Path
from typing import Any

from .config import load_config
from .manifest import BACKUP_FORMAT_VERSION, RELEASE_VERSION, build_release_manifest

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BACKUP_DIR = ROOT / "data" / "backups" / "system"
PLATFORM_DB = ROOT / "data" / "platform" / "platform.db"

_FORBIDDEN_NAMES = {
    ".env",
    ".env.bak",
    ".env.local",
    "firebase-admin.json",
    "credentials.json",
    "service-account.json",
}
_SECRET_RE = re.compile(
    r"(password|secret|token|api[_-]?key|authorization|cookie|private[_-]?key)",
    re.I,
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_member(base: Path, member_name: str) -> Path:
    dest = (base / member_name).resolve()
    if base.resolve() != dest and base.resolve() not in dest.parents:
        raise RuntimeError(f"unsafe archive member escapes target: {member_name}")
    return dest


def _disk_ok(need_bytes: int, path: Path) -> bool:
    free = shutil.disk_usage(str(path if path.exists() else ROOT)).free
    return free > need_bytes + 2 * 1024**3  # +2 GB margin


def _redact_config(cfg: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in (cfg or {}).items():
        if _SECRET_RE.search(str(k)):
            out[k] = "REDACTED"
        elif isinstance(v, dict):
            out[k] = _redact_config(v)
        elif isinstance(v, str) and _SECRET_RE.search(v):
            out[k] = "REDACTED"
        else:
            out[k] = v
    return out


def _record_counts(db_path: Path) -> dict[str, int]:
    if not db_path.is_file():
        return {}
    counts: dict[str, int] = {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            ]
            for t in tables:
                if not re.match(r"^[A-Za-z0-9_]+$", t):
                    continue
                try:
                    counts[t] = int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
                except sqlite3.Error:
                    counts[t] = -1
        finally:
            conn.close()
    except sqlite3.Error:
        return {}
    return counts


def create_system_backup(
    *,
    dest_dir: Path | None = None,
    label: str = "",
    db_path: Path | None = None,
    include_legacy_app_dbs: bool = True,
) -> dict[str, Any]:
    out_dir = Path(dest_dir or load_config().backup_path)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    db = Path(db_path) if db_path else PLATFORM_DB
    files: list[Path] = []
    if db.is_file():
        files.append(db)

    if include_legacy_app_dbs:
        data = ROOT / "data"
        for name in (
            "chat.db",
            "memory.db",
            "agent_runtime.db",
            "voice_os.db",
            "studio_os.db",
            "ceo_os.db",
            "connectors.db",
        ):
            p = data / name
            if p.is_file() and p.name not in _FORBIDDEN_NAMES:
                files.append(p)

    total = sum(p.stat().st_size for p in files)
    if not _disk_ok(total, out_dir):
        raise RuntimeError("insufficient disk for backup (need size + 2GB margin)")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"saathios-system-{stamp}{('-' + label) if label else ''}"
    archive = out_dir / f"{name}.tar.gz"

    manifest: dict[str, Any] = {
        "format_version": BACKUP_FORMAT_VERSION,
        "release_version": RELEASE_VERSION,
        "created": time.time(),
        "stamp": stamp,
        "label": label,
        "excludes_secrets": True,
        "excludes_api_keys": True,
        "excludes_cookies": True,
        "excludes_raw_env": True,
        "files": {},
        "record_counts": _record_counts(db) if db.is_file() else {},
        "release_manifest": build_release_manifest(),
        "config_redacted": _redact_config(load_config().to_public()),
    }

    # Atomic write via temp then rename
    tmp_archive = out_dir / f".{name}.partial.tar.gz"
    try:
        with tarfile.open(tmp_archive, "w:gz") as tar:
            for p in files:
                if p.name in _FORBIDDEN_NAMES:
                    continue
                # refuse symlink escape
                if p.is_symlink():
                    continue
                arcname = f"{name}/files/{p.name}"
                manifest["files"][p.name] = {
                    "checksum": _sha256_file(p),
                    "size": p.stat().st_size,
                    "role": "platform_db" if p.name == "platform.db" else "app_db",
                }
                tar.add(p, arcname=arcname)

            mbytes = json.dumps(manifest, indent=2).encode("utf-8")
            info = tarfile.TarInfo(f"{name}/manifest.json")
            info.size = len(mbytes)
            tar.addfile(info, io.BytesIO(mbytes))

        tmp_archive.replace(archive)
    except Exception:
        if tmp_archive.exists():
            try:
                tmp_archive.unlink()
            except OSError:
                pass
        raise

    archive_checksum = _sha256_file(archive)
    # sidecar integrity
    (out_dir / f"{name}.sha256").write_text(
        f"{archive_checksum}  {archive.name}\n", encoding="utf-8"
    )

    return {
        "archive": str(archive),
        "name": archive.name,
        "size_bytes": archive.stat().st_size,
        "checksum": archive_checksum,
        "format_version": BACKUP_FORMAT_VERSION,
        "files": len(manifest["files"]),
        "record_counts": manifest["record_counts"],
        "stamp": stamp,
        "excludes_secrets": True,
    }


def list_system_backups(dest_dir: Path | None = None) -> list[dict[str, Any]]:
    out_dir = Path(dest_dir or load_config().backup_path)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    if not out_dir.exists():
        return []
    rows = []
    for p in sorted(out_dir.glob("saathios-system-*.tar.gz")):
        rows.append(
            {
                "name": p.name,
                "size_bytes": p.stat().st_size,
                "created": p.stat().st_mtime,
                "path": str(p),
            }
        )
    return rows


def _extract_manifest(archive: Path) -> tuple[dict[str, Any], str]:
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name.endswith("/manifest.json") or member.name == "manifest.json":
                f = tar.extractfile(member)
                if not f:
                    continue
                data = json.loads(f.read().decode("utf-8"))
                prefix = member.name[: -len("manifest.json")].rstrip("/")
                return data, prefix
    raise RuntimeError("manifest.json missing from backup archive")


def verify_system_backup(archive: str | Path) -> dict[str, Any]:
    archive = Path(archive)
    if not archive.is_file():
        return {"ok": False, "error": "ARCHIVE_MISSING"}
    try:
        manifest, prefix = _extract_manifest(archive)
    except Exception as exc:
        return {"ok": False, "error": f"MANIFEST_INVALID: {exc}"}

    if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
        # wrong version is not always corrupt — flag compatibility
        pass

    ok = True
    details: dict[str, Any] = {"files": {}, "format_version": manifest.get("format_version")}
    with tarfile.open(archive, "r:gz") as tar:
        for fname, meta in (manifest.get("files") or {}).items():
            member_name = f"{prefix}/files/{fname}" if prefix else f"files/{fname}"
            try:
                m = tar.getmember(member_name)
            except KeyError:
                details["files"][fname] = "MISSING"
                ok = False
                continue
            f = tar.extractfile(m)
            if not f:
                details["files"][fname] = "UNREADABLE"
                ok = False
                continue
            data = f.read()
            cs = _sha256_bytes(data)
            if cs != meta.get("checksum"):
                details["files"][fname] = "MISMATCH"
                ok = False
            else:
                details["files"][fname] = "match"

    return {
        "ok": ok,
        "details": details,
        "release_version": (manifest.get("release_manifest") or {}).get(
            "saathios_release_version"
        ),
        "format_version": manifest.get("format_version"),
        "compatible": manifest.get("format_version") == BACKUP_FORMAT_VERSION,
    }


def dry_run_restore(archive: str | Path) -> dict[str, Any]:
    v = verify_system_backup(archive)
    return {
        "mode": "dry_run",
        "would_restore": v.get("ok"),
        "verification": v,
        "destructive": False,
        "live_data_touched": False,
    }


def restore_system_backup(
    archive: str | Path,
    *,
    target: Path,
    approval_token: str = "",
    destructive_overwrite: bool = False,
    live_db: Path | None = None,
    expect_format_version: str | None = BACKUP_FORMAT_VERSION,
) -> dict[str, Any]:
    """Restore into isolated target by default.

    Destructive overwrite of live_db requires approval_token == 'APPROVE_DESTRUCTIVE_RESTORE'
    and destructive_overwrite=True. Fail-closed otherwise.
    """
    archive = Path(archive)
    target = Path(target).resolve()
    live = Path(live_db).resolve() if live_db else PLATFORM_DB.resolve()

    v = verify_system_backup(archive)
    if not v.get("ok"):
        return {"ok": False, "error": "INTEGRITY_FAILED", "verification": v}
    if expect_format_version and v.get("format_version") != expect_format_version:
        return {
            "ok": False,
            "error": "WRONG_VERSION",
            "expected": expect_format_version,
            "got": v.get("format_version"),
            "verification": v,
        }

    # Refuse direct live overwrite without approval
    if target == live or str(target) == str(live.parent):
        if not (
            destructive_overwrite
            and approval_token == "APPROVE_DESTRUCTIVE_RESTORE"
        ):
            raise RuntimeError(
                "destructive restore over live data requires "
                "destructive_overwrite=True and approval_token=APPROVE_DESTRUCTIVE_RESTORE"
            )

    target.mkdir(parents=True, exist_ok=True)
    # pre-restore checkpoint of target if platform.db present
    checkpoint = None
    existing = target / "platform.db"
    if existing.is_file():
        checkpoint = target / f"platform.db.prerestore-{int(time.time())}"
        shutil.copy2(existing, checkpoint)

    with tarfile.open(archive, "r:gz") as tar:
        base = target
        for member in tar.getmembers():
            # normalize to relative under target
            name = member.name
            # strip top-level prefix
            parts = Path(name).parts
            if not parts:
                continue
            # keep files/ and manifest
            rel = Path(*parts[1:]) if len(parts) > 1 else Path(parts[0])
            if str(rel) in (".", ""):
                continue
            dest = _safe_member(base, str(rel))
            if member.issym() or member.islnk():
                raise RuntimeError(f"symlink/hardlink refused: {member.name}")
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            f = tar.extractfile(member)
            if f is None:
                continue
            dest.write_bytes(f.read())

    restored_files = list((target / "files").glob("*")) if (target / "files").is_dir() else list(target.glob("*.db"))
    return {
        "ok": True,
        "restored_to": str(target),
        "files": [p.name for p in restored_files],
        "checkpoint": str(checkpoint) if checkpoint else None,
        "verification": v,
        "isolated": target != live,
        "destructive": bool(destructive_overwrite and target == live),
    }


def prune_system_backups(*, keep: int = 5, dest_dir: Path | None = None) -> dict[str, Any]:
    backups = list_system_backups(dest_dir)
    if keep < 1:
        keep = 1
    to_remove = backups[:-keep] if len(backups) > keep else []
    removed = 0
    for b in to_remove:
        try:
            Path(b["path"]).unlink()
            sidecar = Path(b["path"]).with_suffix("").with_suffix(".sha256")
            # name is .tar.gz so with_suffix once -> .tar; handle explicitly
            sha = Path(str(b["path"])[: -len(".tar.gz")] + ".sha256")
            if sha.is_file():
                sha.unlink()
            removed += 1
        except OSError:
            pass
    return {"removed": removed, "kept": min(keep, len(backups))}


def disaster_recovery_drill(
    *,
    work_dir: Path,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Deterministic DR drill: backup → verify → dry-run → isolated restore → corrupt reject."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = work_dir / "backups"
    restore_dir = work_dir / "restore"
    results: dict[str, Any] = {"steps": []}

    # Ensure a db exists for the drill
    db = Path(db_path) if db_path else (work_dir / "platform.db")
    if not db.is_file():
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE IF NOT EXISTS drill (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO drill(v) VALUES ('ok')")
        conn.commit()
        conn.close()

    b = create_system_backup(
        dest_dir=backup_dir, label="dr-drill", db_path=db, include_legacy_app_dbs=False
    )
    results["steps"].append({"step": "backup", "ok": True, "archive": b["name"]})

    v = verify_system_backup(b["archive"])
    results["steps"].append({"step": "verify", "ok": v["ok"]})

    d = dry_run_restore(b["archive"])
    results["steps"].append({"step": "dry_run", "ok": d["would_restore"]})

    r = restore_system_backup(b["archive"], target=restore_dir)
    results["steps"].append({"step": "isolated_restore", "ok": r.get("ok")})

    # Corrupted backup rejection
    corrupt = backup_dir / "corrupt.tar.gz"
    corrupt.write_bytes(b"not-a-tar")
    cv = verify_system_backup(corrupt)
    results["steps"].append({"step": "corrupt_reject", "ok": not cv.get("ok")})

    # Wrong version rejection
    bad_version = restore_system_backup(
        b["archive"], target=work_dir / "wrongver", expect_format_version="never.match.v0"
    )
    results["steps"].append(
        {"step": "wrong_version_reject", "ok": bad_version.get("error") == "WRONG_VERSION"}
    )

    # Destructive without approval must fail
    destructive_blocked = False
    try:
        restore_system_backup(
            b["archive"],
            target=db if db_path else (work_dir / "live.db"),
            live_db=db if db_path else (work_dir / "live.db"),
            destructive_overwrite=True,
            approval_token="nope",
        )
    except RuntimeError:
        destructive_blocked = True
    results["steps"].append({"step": "destructive_approval_gate", "ok": destructive_blocked})

    results["ok"] = all(s.get("ok") for s in results["steps"])
    results["verdict"] = (
        "PRIVATE_ALPHA_DR_DRILL_PASSED" if results["ok"] else "PRIVATE_ALPHA_DR_DRILL_FAILED"
    )
    return results
