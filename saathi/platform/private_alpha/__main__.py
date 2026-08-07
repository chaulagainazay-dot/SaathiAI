"""CLI: python -m saathi.platform.private_alpha <command>

Commands:
  prepare [--install-deps]
  doctor
  init --ack-local-only [--email E --password P]
  open
  manifest
  backup [label]
  backups
  verify-backup <archive>
  restore-dry <archive>
  restore <archive> --target DIR
  support-bundle
  certify
  playbooks
  upgrade-preflight
  dr-drill --work-dir DIR
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _emit(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, *rest = argv

    if cmd == "prepare":
        from .prepare import prepare

        r = prepare(install_deps="--install-deps" in rest)
        _emit(r)
        return 0 if r.get("ok") else 1

    if cmd == "doctor":
        from .prepare import doctor

        r = doctor()
        _emit(r)
        return 0 if r.get("ok") else 1

    if cmd == "init":
        from .prepare import init_first_run

        ack = "--ack-local-only" in rest
        email = ""
        password = ""
        if "--email" in rest:
            email = rest[rest.index("--email") + 1]
        if "--password" in rest:
            password = rest[rest.index("--password") + 1]
        r = init_first_run(
            acknowledge_local_only=ack,
            email=email,
            password=password,
        )
        # never print secrets
        r.pop("_token", None)
        if r.get("owner") and isinstance(r["owner"], dict):
            r["owner"].pop("token", None)
        _emit(r)
        return 0 if r.get("ok") else 1

    if cmd == "open":
        from .prepare import open_entry

        _emit(open_entry())
        return 0

    if cmd == "manifest":
        from .manifest import build_release_manifest, compatibility_matrix, write_manifest

        path = write_manifest()
        _emit(
            {
                "written": str(path),
                "manifest": build_release_manifest(),
                "compatibility": compatibility_matrix(),
            }
        )
        return 0

    if cmd == "backup":
        from .backup_restore import create_system_backup

        label = rest[0] if rest and not rest[0].startswith("-") else ""
        _emit(create_system_backup(label=label))
        return 0

    if cmd == "backups":
        from .backup_restore import list_system_backups

        _emit({"backups": list_system_backups()})
        return 0

    if cmd == "verify-backup" and rest:
        from .backup_restore import verify_system_backup

        v = verify_system_backup(rest[0])
        _emit(v)
        return 0 if v.get("ok") else 6

    if cmd == "restore-dry" and rest:
        from .backup_restore import dry_run_restore

        _emit(dry_run_restore(rest[0]))
        return 0

    if cmd == "restore" and len(rest) >= 3 and rest[1] == "--target":
        from .backup_restore import restore_system_backup

        try:
            _emit(restore_system_backup(rest[0], target=Path(rest[2])))
            return 0
        except Exception as exc:
            _emit({"ok": False, "error": str(exc)})
            return 6

    if cmd == "support-bundle":
        from .support import export_support_bundle

        _emit(export_support_bundle())
        return 0

    if cmd == "certify":
        from .certification import run_private_alpha_certification

        r = run_private_alpha_certification()
        _emit(r)
        return 0 if r.get("fail_count", 1) == 0 else 1

    if cmd == "playbooks":
        from .incidents import list_playbooks

        _emit({"playbooks": list_playbooks()})
        return 0

    if cmd == "upgrade-preflight":
        from .upgrade import upgrade_preflight

        _emit(upgrade_preflight())
        return 0

    if cmd == "dr-drill":
        from .backup_restore import disaster_recovery_drill

        work = Path("data/alpha/dr-drill")
        if "--work-dir" in rest:
            work = Path(rest[rest.index("--work-dir") + 1])
        r = disaster_recovery_drill(work_dir=work)
        _emit(r)
        return 0 if r.get("ok") else 1

    if cmd == "lifecycle-contract":
        from .lifecycle import safety_contract

        _emit(safety_contract())
        return 0

    print(f"unknown command: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
