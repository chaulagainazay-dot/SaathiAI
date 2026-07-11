"""M16 Control Center CLI (read-only).

    python -m saathi.control_center.cli overview [owner]
    python -m saathi.control_center.cli attention [owner]
    python -m saathi.control_center.cli health
    python -m saathi.control_center.cli security
    python -m saathi.control_center.cli release
    python -m saathi.control_center.cli timeline
    python -m saathi.control_center.cli search "<query>" [owner]

Read-only — never mutates. Exit 0 unless attention has a critical item (2) or a
subsystem is unavailable-only (1).
"""
from __future__ import annotations

import json
import sys

from saathi.control_center.aggregator import ControlCenterAggregator
from saathi.control_center import search as _search


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: overview|attention|health|security|release|timeline|search",
              file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    owner = (rest[-1] if rest and not rest[-1].startswith("-") else "ajay")

    if cmd == "search":
        if not rest:
            print("search needs a query", file=sys.stderr); return 2
        print(json.dumps(_search.federated_search(owner=owner, query=rest[0]), indent=2))
        return 0

    agg = ControlCenterAggregator(owner)
    if cmd == "overview":
        ov = agg.overview()
        print(json.dumps(ov, indent=2, default=str))
        crit = any(i["severity"] == "critical" for i in ov["requires_attention"])
        return 2 if crit else (1 if ov["degraded_sources"] else 0)
    if cmd == "attention":
        ov = agg.overview()
        print(json.dumps(ov["requires_attention"], indent=2))
        return 2 if any(i["severity"] == "critical" for i in ov["requires_attention"]) else 0
    if cmd == "health":
        print(json.dumps(agg.platform_health().to_dict(), indent=2, default=str)); return 0
    if cmd == "security":
        print(json.dumps(agg.security_posture().to_dict(), indent=2, default=str)); return 0
    if cmd == "release":
        print(json.dumps(agg.release_readiness().to_dict(), indent=2, default=str)); return 0
    if cmd == "timeline":
        print(json.dumps(agg.recent_events().to_dict(), indent=2, default=str)); return 0
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
