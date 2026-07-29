"""Bounded skill CLI — local packages only, no remote URLs or package installs."""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="saathi-skill", description="SaathiOS Skill Runtime CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List registered skills (requires platform bootstrap in-process)")
    sub.add_parser("discover", help="Discover local built-in packages")
    p_inspect = sub.add_parser("inspect", help="Inspect skill id")
    p_inspect.add_argument("skill_id")
    p_val = sub.add_parser("validate", help="Validate local package id (not a URL)")
    p_val.add_argument("package_id")
    p_reg = sub.add_parser("register", help="Register local package id")
    p_reg.add_argument("package_id")
    p_en = sub.add_parser("enable", help="Enable skill")
    p_en.add_argument("skill_id")
    p_dis = sub.add_parser("disable", help="Disable skill")
    p_dis.add_argument("skill_id")
    p_h = sub.add_parser("health", help="Health check")
    p_h.add_argument("skill_id")
    p_dep = sub.add_parser("dependencies", help="Resolve dependencies")
    p_dep.add_argument("skill_id")
    p_up = sub.add_parser("upgrade", help="Upgrade skill")
    p_up.add_argument("skill_id")
    p_up.add_argument("--to", required=True)
    p_up.add_argument("--package-id", required=True)
    p_rb = sub.add_parser("rollback", help="Rollback skill")
    p_rb.add_argument("skill_id")
    p_q = sub.add_parser("quarantine", help="Quarantine skill")
    p_q.add_argument("skill_id")
    p_q.add_argument("--reason", default="cli")
    p_ev = sub.add_parser("evidence", help="List executions/evidence")
    p_ev.add_argument("skill_id")

    args = parser.parse_args(argv)

    # Reject remote URLs everywhere
    for val in vars(args).values():
        if isinstance(val, str) and (
            val.startswith("http://")
            or val.startswith("https://")
            or val.startswith("git@")
        ):
            print(json.dumps({"error": "REMOTE_URL_FORBIDDEN", "value": val}))
            return 2

    print(
        json.dumps(
            {
                "note": "CLI scaffold — use authenticated platform APIs or pytest fixtures for full operations.",
                "command": args.cmd,
                "args": {k: v for k, v in vars(args).items() if k != "cmd"},
                "remote_install": False,
                "marketplace": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
