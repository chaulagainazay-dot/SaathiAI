"""M13.5 backup + restore — real, checksum-verified, secret-free.

`create_backup` snapshots the app databases + a redacted config manifest into a
compressed archive with a checksum manifest. `restore_backup` extracts into an
ISOLATED target directory (never the live data dir by default) and
`verify_restore` re-checks checksums, schema versions, and db integrity.

Backups NEVER include: provider keys, tokens, .env, firebase-admin.json,
session cookies, temp render files, or media binaries (only db + metadata).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"
BACKUP_DIR = DATA / "backups"

APP_DBS = ["chat.db", "memory.db", "agent_runtime.db", "voice_os.db", "studio_os.db"]

# never back these up
_FORBIDDEN = {".env", ".env.bak", "firebase-admin.json"}


def _checksum(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _min_free_ok(need_mb: float) -> bool:
    import shutil
    return shutil.disk_usage(str(DATA)).free / 1e6 > need_mb + 2000  # +2GB margin


def create_backup(*, data_dir: Path | None = None, dest_dir: Path | None = None,
                  label: str = "") -> dict:
    d = data_dir or DATA
    out_dir = dest_dir or BACKUP_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    dbs = [d / name for name in APP_DBS if (d / name).exists()]
    total_mb = sum(p.stat().st_size for p in dbs) / 1e6
    if not _min_free_ok(total_mb):
        raise RuntimeError("insufficient disk for backup (need db size + 2GB margin)")

    from saathi.ops.identity import SCHEMA_VERSIONS, git_commit
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"saathi-backup-{stamp}{('-' + label) if label else ''}"
    archive = out_dir / f"{name}.tar.gz"

    manifest = {
        "created": time.time(), "stamp": stamp, "commit": git_commit(),
        "schema_versions": SCHEMA_VERSIONS,
        "databases": {}, "excludes_secrets": True,
    }
    with tarfile.open(archive, "w:gz") as tar:
        for p in dbs:
            if p.name in _FORBIDDEN:
                continue
            manifest["databases"][p.name] = {
                "checksum": _checksum(p), "size": p.stat().st_size}
            tar.add(p, arcname=f"{name}/{p.name}")
        # redacted config manifest (presence only, no values)
        import os
        cfg = {k: "PRESENT" for k in ("SAATHI_TOKEN", "ANTHROPIC_API_KEY", "GROQ_API_KEY")
               if os.getenv(k)}
        manifest["config_presence"] = cfg
        mbytes = json.dumps(manifest, indent=1).encode()
        info = tarfile.TarInfo(f"{name}/manifest.json")
        info.size = len(mbytes)
        import io
        tar.addfile(info, io.BytesIO(mbytes))

    return {"archive": str(archive), "size_bytes": archive.stat().st_size,
            "databases": len(manifest["databases"]), "stamp": stamp,
            "checksum": _checksum(archive)[:16]}


def list_backups(dest_dir: Path | None = None) -> list[dict]:
    out_dir = dest_dir or BACKUP_DIR
    if not out_dir.exists():
        return []
    return [{"name": p.name, "size_bytes": p.stat().st_size,
             "created": p.stat().st_mtime}
            for p in sorted(out_dir.glob("saathi-backup-*.tar.gz"))]


def restore_backup(archive: str | Path, *, target: Path) -> dict:
    """Extract into an ISOLATED target dir. Refuses to write into the live data
    dir unless target is explicitly that (safety default = isolated)."""
    archive = Path(archive)
    target = Path(target).resolve()
    if target == DATA.resolve():
        raise RuntimeError("refusing to restore over the live data dir; use an "
                           "isolated --target")
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        # path-traversal-safe extraction
        base = target.resolve()
        for member in tar.getmembers():
            dest = (base / member.name).resolve()
            if base != dest and base not in dest.parents:
                raise RuntimeError(f"unsafe archive member escapes target: {member.name}")
        tar.extractall(target)
    # find the extracted backup dir
    extracted = next((p for p in target.iterdir() if p.is_dir()
                     and p.name.startswith("saathi-backup-")), None)
    return {"restored_to": str(extracted or target),
            "files": [f.name for f in (extracted or target).glob("*")]}


def verify_restore(restored_dir: str | Path) -> dict:
    """Re-check checksums, schema versions, and db integrity of a restored copy."""
    rd = Path(restored_dir)
    manifest_path = rd / "manifest.json"
    if not manifest_path.exists():
        return {"ok": False, "error": "manifest.json missing from restore"}
    manifest = json.loads(manifest_path.read_text())

    from saathi.ops.identity import SCHEMA_VERSIONS
    from saathi.ops.db_integrity import check_db
    results = {"checksums": {}, "integrity": {}, "schema_ok": True}
    ok = True

    for dbname, meta in manifest.get("databases", {}).items():
        p = rd / dbname
        if not p.exists():
            results["checksums"][dbname] = "MISSING"; ok = False; continue
        cs = _checksum(p)
        match = cs == meta["checksum"]
        results["checksums"][dbname] = "match" if match else "MISMATCH"
        ok = ok and match
        integ = check_db(p)
        results["integrity"][dbname] = integ["ok"]
        ok = ok and integ["ok"]

    if manifest.get("schema_versions") != SCHEMA_VERSIONS:
        results["schema_ok"] = False  # not a hard fail — informational drift

    return {"ok": ok, "schema_match": manifest.get("schema_versions") == SCHEMA_VERSIONS,
            "details": results, "backup_commit": manifest.get("commit")}


def prune_backups(*, keep: int = 5, dest_dir: Path | None = None) -> dict:
    backups = list_backups(dest_dir)
    to_remove = backups[:-keep] if len(backups) > keep else []
    out_dir = dest_dir or BACKUP_DIR
    removed = 0
    for b in to_remove:
        try:
            (out_dir / b["name"]).unlink(); removed += 1
        except OSError:
            pass
    return {"removed": removed, "kept": min(keep, len(backups))}
