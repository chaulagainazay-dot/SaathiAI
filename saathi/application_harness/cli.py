"""M17.3 application-harness CLI (read-only inspection + safe live pilot).

    python -m saathi.application_harness.cli list
    python -m saathi.application_harness.cli inspect <harness_id>
    python -m saathi.application_harness.cli operations <harness_id>
    python -m saathi.application_harness.cli resolve <application> <operation>
    python -m saathi.application_harness.cli import-cli-anything <registry.json>
    python -m saathi.application_harness.cli health
    python -m saathi.application_harness.cli live-report

Read-only commands never mutate; import marks entries untrusted; execution/trust
changes go through canonical policy (not exposed as free CLI mutations here).
"""
from __future__ import annotations

import json
import sys

from saathi.application_harness import registry, resolver, importer
from saathi.application_harness.pilots import ffmpeg as F


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: list|inspect|operations|resolve|import-cli-anything|health|live-report",
              file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "list":
        print(json.dumps(registry.summary(), indent=2)); return 0
    if cmd == "inspect":
        d = registry.get(rest[0]) if rest else None
        print(json.dumps(d.to_dict() if d else {"error": "not found"}, indent=2, default=str))
        return 0 if d else 1
    if cmd == "operations":
        if rest and rest[0] == "ffmpeg":
            print(json.dumps([o.to_dict() for o in F.operations()], indent=2)); return 0
        print("[]"); return 0
    if cmd == "resolve":
        if len(rest) < 2:
            print("resolve needs <application> <operation>", file=sys.stderr); return 2
        h = registry.get(rest[0]) or next((d for d in registry.all_harnesses()
                                           if d.application_name == rest[0]), None)
        r = resolver.resolve(application=rest[0], operation=rest[1], harness=h)
        print(json.dumps(r.to_dict(), indent=2)); return 0
    if cmd == "import-cli-anything":
        if not rest:
            print("needs a registry.json path", file=sys.stderr); return 2
        raw = open(rest[0]).read()
        res = importer.import_registry(raw)
        print(json.dumps({"imported": res["imported"], "rejected": len(res["rejected"]),
                          "trust": res["trust"]}, indent=2)); return 0
    if cmd == "health":
        print(json.dumps({"ffmpeg": F.available(), "registry": registry.summary()},
                         indent=2)); return 0
    if cmd == "live-report":
        from saathi.application_harness.live_report import build_report
        print(json.dumps(build_report(), indent=2, default=str)); return 0
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
