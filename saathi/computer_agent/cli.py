"""M17 Computer Agent CLI (read-only + describe; execution stays gateway-routed).

    python -m saathi.computer_agent.cli providers
    python -m saathi.computer_agent.cli connectors
    python -m saathi.computer_agent.cli describe <tool_id>
    python -m saathi.computer_agent.cli perceive [desktop|browser]

Never actuates a real desktop. `describe` shows risk/approval before any action.
"""
from __future__ import annotations

import json
import sys

from saathi.computer_agent.providers import provider_availability, default_provider
from saathi.computer_agent.agent import ComputerAgent
from saathi.connectors.platform import registry as R


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: providers|connectors|describe|perceive", file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "providers":
        print(json.dumps(provider_availability(), indent=2)); return 0
    if cmd == "connectors":
        conns = [c.to_dict() for c in R.all_connectors() if c.category == "computer"]
        print(json.dumps(conns, indent=2)); return 0
    if cmd == "describe":
        if not rest:
            print("describe needs a tool_id", file=sys.stderr); return 2
        ag = ComputerAgent(owner="ajay")
        print(json.dumps(ag.describe(tool_id=rest[0]), indent=2)); return 0
    if cmd == "perceive":
        surface = rest[0] if rest else "desktop"
        print(json.dumps(default_provider(surface).perceive().to_dict(), indent=2, default=str))
        return 0
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
