"""M17.1 Computer Agent CLI — permissions, workspace, live smoke, report.

    python -m saathi.computer_agent.cli permissions
    python -m saathi.computer_agent.cli providers
    python -m saathi.computer_agent.cli connectors
    python -m saathi.computer_agent.cli describe <tool_id>
    python -m saathi.computer_agent.cli perceive [desktop|browser]
    python -m saathi.computer_agent.cli workspace-create|workspace-inspect|workspace-reset
    python -m saathi.computer_agent.cli workspace-cleanup [--dry-run]
    python -m saathi.computer_agent.cli browser-smoke
    python -m saathi.computer_agent.cli live-report

Exit codes: 0 ok · 1 skipped/blocked · 2 bad usage. Never actuates a real
desktop without permission; live browser runs only when a browser binary exists.
"""
from __future__ import annotations

import json
import sys

from saathi.computer_agent.providers import provider_availability, default_provider
from saathi.computer_agent.agent import ComputerAgent
from saathi.computer_agent import permissions, workspace
from saathi.connectors.platform import registry as R


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: permissions|providers|connectors|describe|perceive|"
              "workspace-*|browser-smoke|live-report", file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]

    if cmd == "permissions":
        print(json.dumps(permissions.summary(), indent=2)); return 0
    if cmd == "providers":
        print(json.dumps(provider_availability(), indent=2)); return 0
    if cmd == "connectors":
        print(json.dumps([c.to_dict() for c in R.all_connectors()
                          if c.category == "computer"], indent=2)); return 0
    if cmd == "describe":
        if not rest:
            print("describe needs a tool_id", file=sys.stderr); return 2
        print(json.dumps(ComputerAgent(owner="ajay").describe(tool_id=rest[0]), indent=2))
        return 0
    if cmd == "perceive":
        surface = rest[0] if rest else "desktop"
        print(json.dumps(default_provider(surface).perceive().to_dict(), indent=2, default=str))
        return 0
    if cmd == "workspace-create":
        print(json.dumps(workspace.create(), indent=2)); return 0
    if cmd == "workspace-inspect":
        print(json.dumps(workspace.inspect(), indent=2)); return 0
    if cmd == "workspace-reset":
        print(json.dumps(workspace.reset(), indent=2)); return 0
    if cmd == "workspace-cleanup":
        print(json.dumps(workspace.cleanup(dry_run="--dry-run" in rest), indent=2)); return 0
    if cmd == "browser-smoke":
        from saathi.computer_agent.live_workflow import run_browser_smoke
        r = run_browser_smoke()
        print(json.dumps(r, indent=2, default=str))
        return 0 if r["status"] == "completed" else 1
    if cmd == "live-report":
        from saathi.computer_agent.live_report import build_report
        print(json.dumps(build_report(), indent=2, default=str)); return 0
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
