"""M13.5 ops CLI — `python -m saathi.ops <cmd>` (also `python -m saathi.ops.cli`).

  status            backend listening + stale-process detection (read-only)
  health            storage + db integrity + config summary (read-only)
  config-check      validate config, redact secrets (read-only)
  storage           storage report + thresholds (read-only)
  cleanup [--apply] preview (default) or apply temp/partial cleanup
  db-check          per-db integrity_check (read-only)
  backup [label]    create a real checksum-verified backup
  backups           list backups (read-only)
  verify-backup <archive>  restore into a temp dir + verify (read-only to live)
  restore <archive> --target <dir>   restore into an ISOLATED dir
  verify-restore <dir>     verify a restored copy (read-only)
  prune-backups [--keep N]
  release-check     run staging release gates (exit codes 0-12)
  identity          runtime version identity (read-only)

Read-only commands never mutate live data. Cleanup is preview-first.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _emit(o) -> None:
    print(json.dumps(o, indent=1, default=str))


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 0
    cmd, *rest = argv

    if cmd == "status":
        from saathi.ops.process import backend_status
        s = backend_status()
        _emit(s)
        return 10 if s.get("stale") else 0
    if cmd == "health":
        from saathi.ops.storage import storage_report
        from saathi.ops.db_integrity import check_all
        from saathi.ops.config_check import check_config
        _emit({"storage": storage_report(), "database": check_all(),
               "config": {"ok": check_config()["ok"]}})
        return 0
    if cmd == "config-check":
        from saathi.ops.config_check import check_config
        c = check_config()
        _emit(c)
        return 4 if not c["ok"] else 0
    if cmd == "storage":
        from saathi.ops.storage import storage_report
        s = storage_report()
        _emit(s)
        return 9 if not s["healthy"] else 0
    if cmd == "cleanup":
        from saathi.ops.storage import run_cleanup
        _emit(run_cleanup(apply="--apply" in rest))
        return 0
    if cmd == "db-check":
        from saathi.ops.db_integrity import check_all
        r = check_all()
        _emit(r)
        return 5 if not r["all_ok"] else 0
    if cmd == "identity":
        from saathi.ops.identity import identity
        _emit(identity())
        return 0
    if cmd == "backup":
        from saathi.ops.backup import create_backup
        _emit(create_backup(label=rest[0] if rest else ""))
        return 0
    if cmd == "backups":
        from saathi.ops.backup import list_backups
        _emit({"backups": list_backups()})
        return 0
    if cmd == "verify-backup" and rest:
        import tempfile
        from saathi.ops.backup import restore_backup, verify_restore
        with tempfile.TemporaryDirectory() as d:
            r = restore_backup(rest[0], target=Path(d) / "r")
            v = verify_restore(r["restored_to"])
        _emit(v)
        return 0 if v["ok"] else 6
    if cmd == "restore" and len(rest) >= 3 and rest[1] == "--target":
        from saathi.ops.backup import restore_backup
        try:
            _emit(restore_backup(rest[0], target=Path(rest[2])))
            return 0
        except RuntimeError as exc:
            _emit({"error": str(exc)}); return 6
    if cmd == "verify-restore" and rest:
        from saathi.ops.backup import verify_restore
        v = verify_restore(rest[0])
        _emit(v)
        return 0 if v["ok"] else 6
    if cmd == "prune-backups":
        from saathi.ops.backup import prune_backups
        keep = 5
        if "--keep" in rest:
            try:
                keep = int(rest[rest.index("--keep") + 1])
            except (ValueError, IndexError):
                pass
        _emit(prune_backups(keep=keep))
        return 0
    if cmd == "release-check":
        from saathi.ops.release_gate import release_check
        code, report = release_check(strict_dirty="--strict-dirty" in rest)
        _emit({"exit_code": code, **report})
        return code

    print(f"unknown command: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
