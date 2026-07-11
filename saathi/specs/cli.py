"""SaathiOS Spec Kit wrapper CLI.

    python -m saathi.specs.cli version
    python -m saathi.specs.cli health
    python -m saathi.specs.cli init <milestone-slug>
    python -m saathi.specs.cli validate <traceability.json>
    python -m saathi.specs.cli converge <traceability.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from saathi.specs.traceability import (
    ROOT, load_traceability, validate_traceability, converge,
)

VERSION = "1.0.0"
CONSTITUTION = ROOT / ".specify" / "memory" / "constitution.md"


def _health() -> dict:
    return {"version": VERSION,
            "constitution_present": CONSTITUTION.exists(),
            "specs_dir_present": (ROOT / "specs").exists(),
            "preset_present": (ROOT / ".specify" / "presets" / "saathios").exists()}


def _init(slug: str) -> dict:
    d = ROOT / "specs" / slug
    (d / "checklists").mkdir(parents=True, exist_ok=True)
    (d / "contracts").mkdir(parents=True, exist_ok=True)
    tj = d / "traceability.json"
    if not tj.exists():
        tj.write_text(json.dumps(
            {"milestone": slug, "constitution_version": "1.0", "requirements": []},
            indent=2))
    return {"initialized": str(d)}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: version|health|init|validate|converge", file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "version":
        print(VERSION); return 0
    if cmd == "health":
        print(json.dumps(_health(), indent=2)); return 0
    if cmd == "init":
        if not rest:
            print("init needs a milestone slug", file=sys.stderr); return 2
        print(json.dumps(_init(rest[0]), indent=2)); return 0
    if cmd == "validate":
        if not rest:
            print("validate needs a traceability.json path", file=sys.stderr); return 2
        problems = validate_traceability(load_traceability(rest[0]))
        print(json.dumps({"problems": problems, "ok": not problems}, indent=2))
        return 0 if not problems else 1
    if cmd == "converge":
        if not rest:
            print("converge needs a traceability.json path", file=sys.stderr); return 2
        result = converge(rest[0])
        print(json.dumps(result, indent=2))
        return 0 if result["verdict"] == "CONVERGED" else 1
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
