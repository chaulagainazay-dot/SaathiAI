"""M20.7 console CLI — `python -m saathi.m20_console <cmd>`.

  status       unified engineering + inference read-only status
  flags        flag inventory + effective values
  disable      print disable procedure
  discover     CLI entrypoint map
  domains      isolation guarantees
  engineering  engineering snapshot only
  inference    inference snapshot only

Never launches agents, never generates, never pushes.
"""
from __future__ import annotations

import json
import sys


def _emit(o) -> None:
    print(json.dumps(o, indent=1, default=str))


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "status":
        from saathi.m20_console.status import m20_console_status
        _emit(m20_console_status())
        return 0
    if cmd == "flags":
        from saathi.m20_console.flags import flag_snapshot
        _emit(flag_snapshot())
        return 0
    if cmd == "disable":
        from saathi.m20_console.flags import disable_procedure
        _emit(disable_procedure())
        return 0
    if cmd == "discover":
        from saathi.m20_console.status import cli_discovery
        _emit(cli_discovery())
        return 0
    if cmd == "domains":
        from saathi.m20_console.flags import domains_isolated
        _emit(domains_isolated())
        return 0
    if cmd == "engineering":
        from saathi.m20_console.status import engineering_snapshot
        _emit(engineering_snapshot())
        return 0
    if cmd == "inference":
        from saathi.m20_console.status import inference_snapshot
        _emit(inference_snapshot())
        return 0
    _emit({"error": "unknown_command", "cmd": cmd, "hint": "help"})
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
