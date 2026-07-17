"""CLI: python -m saathi.connectors.registry <cmd>"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional


def _emit(o: object) -> None:
    print(json.dumps(o, indent=2, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help"):
        print(
            """M29 connector identity registry

  python -m saathi.connectors.registry docs [--markdown] [--out PATH]
  python -m saathi.connectors.registry list
  python -m saathi.connectors.registry inspect <connector_id>
  python -m saathi.connectors.registry validate <connector_id>
  python -m saathi.connectors.registry bootstrap
  python -m saathi.connectors.registry trust-matrix

Default connector rollout remains OFF. No live accounts. No API keys.
"""
        )
        return 0

    cmd = argv[0]

    if cmd == "trust-matrix":
        from saathi.connectors.registry.trust import trust_summary
        _emit({"schema": "m29.trust_matrix.v1", "trust": trust_summary()})
        return 0

    if cmd == "bootstrap":
        from saathi.connectors.gov.registry import reset_registry, get_registry
        from saathi.connectors.gov.runtime import reset_runtime, get_runtime

        reset_registry()
        reset_runtime()
        rt = get_runtime(rollout_mode="OFF")
        ids = rt.register_builtin_adapters()
        _emit({
            "ok": True,
            "registered": ids,
            "mode": rt.mode.value,
            "registry_ids": get_registry().list_ids(),
            "m29": True,
        })
        return 0

    if cmd == "list":
        from saathi.connectors.gov.runtime import get_runtime
        from saathi.connectors.gov.registry import get_registry

        rt = get_runtime()
        if not get_registry().list_ids():
            rt.register_builtin_adapters()
        _emit({
            "connectors": get_registry().list_ids(),
            "records": [r.to_dict() for r in get_registry().all_records()],
        })
        return 0

    if cmd == "inspect":
        if len(argv) < 2:
            print("usage: inspect <connector_id>", file=sys.stderr)
            return 2
        from saathi.connectors.gov.runtime import get_runtime
        from saathi.connectors.gov.registry import get_registry

        rt = get_runtime()
        if not get_registry().list_ids():
            rt.register_builtin_adapters()
        try:
            _emit(get_registry().inspect(argv[1]))
            return 0
        except KeyError:
            _emit({"ok": False, "error": "unknown_connector", "connector_id": argv[1]})
            return 1

    if cmd == "validate":
        if len(argv) < 2:
            print("usage: validate <connector_id>", file=sys.stderr)
            return 2
        from saathi.connectors.gov.runtime import get_runtime
        from saathi.connectors.gov.registry import get_registry

        rt = get_runtime()
        if not get_registry().list_ids():
            rt.register_builtin_adapters()
        out = get_registry().validate(argv[1])
        _emit(out)
        return 0 if out.get("ok") else 1

    if cmd == "docs":
        from saathi.connectors.gov.runtime import get_runtime
        from saathi.connectors.gov.registry import get_registry
        from saathi.connectors.registry.docs import (
            generate_registry_docs,
            render_registry_docs_markdown,
        )

        rt = get_runtime()
        if not get_registry().list_ids():
            rt.register_builtin_adapters()
        docs = generate_registry_docs(get_registry())
        markdown = "--markdown" in argv or "-m" in argv
        out_path = None
        if "--out" in argv:
            out_path = Path(argv[argv.index("--out") + 1])
        if markdown:
            text = render_registry_docs_markdown(docs)
            if out_path:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(text, encoding="utf-8")
                _emit({"ok": True, "format": "markdown", "path": str(out_path)})
            else:
                print(text)
            return 0
        if out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(docs, indent=2, default=str) + "\n", encoding="utf-8")
            _emit({"ok": True, "format": "json", "path": str(out_path), "connector_count": len(docs["connector_catalog"])})
            return 0
        _emit(docs)
        return 0

    print(f"unknown: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
