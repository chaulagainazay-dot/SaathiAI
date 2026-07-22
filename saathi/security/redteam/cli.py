"""M15.2 red-team harness CLI.

    python -m saathi.security.redteam.cli health
    python -m saathi.security.redteam.cli list-targets
    python -m saathi.security.redteam.cli list-attacks
    python -m saathi.security.redteam.cli run [--suite <category>]
    python -m saathi.security.redteam.cli report [--suite <category>]
    python -m saathi.security.redteam.cli baseline
    python -m saathi.security.redteam.cli compare

Exit codes: 0 = no release-blocking findings, 1 = release-blocking finding(s)
present, 2 = bad usage.
"""
from __future__ import annotations

import json
import sys

from saathi.security.redteam.config import RedTeamConfig
from saathi.security.redteam.hackagent import availability
from saathi.security.redteam import runner, baseline, report as R
from saathi.security.redteam.runner import load_corpus


def _suite_arg(rest):
    if "--suite" in rest:
        i = rest.index("--suite")
        return rest[i + 1] if i + 1 < len(rest) else None
    return None


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: health|list-targets|list-attacks|run|report|baseline|compare",
              file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    cfg = RedTeamConfig()

    if cmd == "health":
        print(json.dumps({"config": {"mode": cfg.mode, "cloud_sync": cfg.cloud_sync,
              "target": cfg.target}, "hackagent": availability()}, indent=2))
        return 0
    if cmd == "list-targets":
        print(json.dumps({"targets": ["inproc"], "mode": cfg.mode,
                          "production_blocked": True}, indent=2))
        return 0
    if cmd == "list-attacks":
        print(json.dumps(load_corpus(), indent=2))
        return 0
    if cmd == "run":
        res = runner.run_suite(suite=_suite_arg(rest), config=cfg)
        print(json.dumps(res["summary"], indent=2))
        return 0 if res["summary"]["release_blocking"] == 0 else 1
    if cmd == "report":
        rep = R.build_report(suite=_suite_arg(rest), config=cfg)
        print(json.dumps(rep, indent=2))
        return 0 if rep["totals"]["release_blocking"] == 0 else 1
    if cmd == "baseline":
        print(json.dumps(baseline.generate(cfg), indent=2))
        return 0
    if cmd == "compare":
        print(json.dumps(baseline.compare(cfg), indent=2))
        return 0
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
