"""CLI: python -m saathi.connectors.gov <cmd>"""
from __future__ import annotations

import json
import sys
from typing import Optional

from saathi.connectors.gov.models import ConnectorRequest
from saathi.connectors.gov.registry import reset_registry
from saathi.connectors.gov.runtime import get_runtime, reset_runtime


def _emit(o: object) -> None:
    print(json.dumps(o, indent=2, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help"):
        print(
            """M27 governed connector framework

  python -m saathi.connectors.gov status
  python -m saathi.connectors.gov bootstrap
  python -m saathi.connectors.gov mode <OFF|SHADOW|CANARY|ACTIVE|DRAINING>
  python -m saathi.connectors.gov list
  python -m saathi.connectors.gov exec <connector_id> <operation> [--url URL]

Default mode OFF. No live accounts. No cloud enablement.
"""
        )
        return 0

    cmd = argv[0]
    if cmd == "bootstrap":
        reset_registry()
        reset_runtime()
        rt = get_runtime(rollout_mode="OFF")
        ids = rt.register_builtin_adapters()
        _emit({"ok": True, "registered": ids, "mode": rt.mode.value})
        return 0
    if cmd == "status":
        rt = get_runtime()
        if not rt.registry.list_ids():
            rt.register_builtin_adapters()
        _emit(rt.status())
        return 0
    if cmd == "list":
        rt = get_runtime()
        if not rt.registry.list_ids():
            rt.register_builtin_adapters()
        _emit({"connectors": rt.registry.list_ids()})
        return 0
    if cmd == "mode":
        if len(argv) < 2:
            print("usage: mode <OFF|SHADOW|CANARY|ACTIVE|DRAINING>", file=sys.stderr)
            return 2
        rt = get_runtime()
        out = rt.set_mode(argv[1].upper())
        _emit(out)
        return 0 if out.get("ok") else 1
    if cmd == "exec":
        if len(argv) < 3:
            print("usage: exec <connector_id> <operation>", file=sys.stderr)
            return 2
        rt = get_runtime()
        if not rt.registry.list_ids():
            rt.register_builtin_adapters()
        url = ""
        if "--url" in argv:
            url = argv[argv.index("--url") + 1]
        req = ConnectorRequest(
            connector_id=argv[1],
            operation=argv[2],
            url=url,
            method="GET",
        )
        _emit(rt.execute(req).to_dict())
        return 0

    print(f"unknown: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
