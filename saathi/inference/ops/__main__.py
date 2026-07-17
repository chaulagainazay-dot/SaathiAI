"""CLI: python -m saathi.inference.ops <command>"""
from __future__ import annotations

import json
import sys
from typing import Optional

from saathi.inference.ops.models import RolloutMode
from saathi.inference.ops.service import get_ops_service


def _emit(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(
            """M26 inference operations

  python -m saathi.inference.ops start
  python -m saathi.inference.ops status
  python -m saathi.inference.ops readiness
  python -m saathi.inference.ops health
  python -m saathi.inference.ops drain
  python -m saathi.inference.ops stop
  python -m saathi.inference.ops restart
  python -m saathi.inference.ops recover
  python -m saathi.inference.ops mode <OFF|SHADOW|CANARY|ACTIVE|DRAINING>
  python -m saathi.inference.ops rollback
  python -m saathi.inference.ops accept-check [--key K] [--caller C]

Default rollout mode is OFF. ACTIVE requires production certification.
Does not own the external Ollama process. Cloud fallback stays disabled.
"""
        )
        return 0

    svc = get_ops_service()
    cmd = argv[0]

    if cmd == "start":
        _emit(svc.start())
        return 0
    if cmd == "stop":
        force = "--force" in argv
        _emit(svc.stop(force=force))
        return 0
    if cmd == "restart":
        _emit(svc.restart())
        return 0
    if cmd == "drain":
        _emit(svc.drain())
        return 0
    if cmd == "recover":
        _emit(svc.recover())
        return 0
    if cmd == "status":
        _emit(svc.status())
        return 0
    if cmd == "health":
        _emit(svc.health().to_dict())
        return 0
    if cmd == "readiness":
        _emit(svc.readiness().to_dict())
        return 0
    if cmd == "mode":
        if len(argv) < 2:
            print("usage: mode <OFF|SHADOW|CANARY|ACTIVE|DRAINING>", file=sys.stderr)
            return 2
        try:
            m = RolloutMode(argv[1].upper())
        except ValueError:
            print(f"invalid mode: {argv[1]}", file=sys.stderr)
            return 2
        out = svc.set_mode(m, reason="cli")
        _emit(out)
        return 0 if out.get("ok") else 1
    if cmd == "rollback":
        _emit(svc.rollback())
        return 0
    if cmd in ("accept-check", "accept"):
        key = ""
        caller = ""
        if "--key" in argv:
            key = argv[argv.index("--key") + 1]
        if "--caller" in argv:
            caller = argv[argv.index("--caller") + 1]
        ok, reason = svc.accepts_new_work(request_key=key, caller_id=caller)
        _emit({"accepted": ok, "reason": reason})
        return 0 if ok else 1

    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
