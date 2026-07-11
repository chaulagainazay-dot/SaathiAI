"""M15 connector platform CLI (read-only observability + governed execute).

    python -m saathi.connectors.platform.cli list
    python -m saathi.connectors.platform.cli tools [capability]
    python -m saathi.connectors.platform.cli health
    python -m saathi.connectors.platform.cli capabilities
    python -m saathi.connectors.platform.cli exec <owner> <tool_id> [k=v ...]

`exec` runs through the ExecutionEngine — side-effect tools without a bound
approval return approval_required (never silently executed).
"""
from __future__ import annotations

import json
import sys

from saathi.connectors.platform import registry as R, health, catalog
from saathi.connectors.platform.execution import default_engine, ExecRequest


def _kv(rest):
    args = {}
    for tok in rest:
        if "=" in tok:
            k, v = tok.split("=", 1)
            args[k] = v
    return args


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: list|tools|health|capabilities|exec", file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "list":
        print(json.dumps([c.to_dict() for c in R.all_connectors()], indent=2)); return 0
    if cmd == "tools":
        tools = (R.tools_for_capability(rest[0]) if rest else R.all_tools())
        print(json.dumps([t.to_dict() for t in tools], indent=2)); return 0
    if cmd == "capabilities":
        print(json.dumps(catalog.all_capabilities(), indent=2)); return 0
    if cmd == "health":
        print(json.dumps(health.platform_health(), indent=2)); return 0
    if cmd == "exec":
        if len(rest) < 2:
            print("exec needs <owner> <tool_id>", file=sys.stderr); return 2
        owner, tool_id = rest[0], rest[1]
        r = default_engine().execute(ExecRequest(owner=owner, tool_id=tool_id,
                                                 args=_kv(rest[2:])))
        print(json.dumps(r.to_dict(), indent=2, default=str))
        return 0 if r.status in ("success", "partial") else 1
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
