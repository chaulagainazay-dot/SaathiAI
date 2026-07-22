"""CLI: python -m saathi.codebase_memory <cmd>

Commands: health | index | refresh | search | symbol | status | rebuild
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from saathi.codebase_memory.service import CodebaseMemoryRuntime


def _print(data: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, default=str))
        return
    if "hits" in data:
        print(f"ok={data.get('ok')} mode={data.get('mode')} hits={len(data.get('hits') or [])}")
        for h in data.get("hits") or []:
            warn = f" WARN={','.join(h.get('warnings') or [])}" if h.get("warnings") else ""
            print(
                f"  [{h.get('score')}] {h.get('citation')} "
                f"fresh={h.get('freshness')}{warn}"
            )
            if h.get("explanation"):
                print(f"    {h['explanation']}")
            snip = (h.get("snippet") or "").replace("\n", " ")[:120]
            print(f"    {snip}")
        return
    # generic pretty
    for k in (
        "status", "namespace", "branch", "commit_sha", "indexed_commit",
        "files", "chunks", "symbols", "exclusions", "degraded_reason",
        "ok", "files_indexed", "chunks_written", "secret_exclusions", "error",
    ):
        if k in data:
            print(f"{k}: {data[k]}")
    if "repository_id" in data:
        print(f"repository_id: {data['repository_id']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="saathi.codebase_memory", description="M18.2 governed codebase memory")
    p.add_argument("command", choices=[
        "health", "index", "refresh", "search", "symbol", "status", "rebuild",
    ])
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--root", default=None, help="repository root")
    p.add_argument("--json", action="store_true")
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--docs", action="store_true", help="documentation-only search")
    p.add_argument("--tests", action="store_true", help="tests-only search")
    args = p.parse_args(argv)

    rt = CodebaseMemoryRuntime(args.root)
    cmd = args.command

    if cmd in ("health", "status"):
        data = rt.health()
        _print(data, as_json=args.json)
        st = data.get("status")
        if st in ("CORRUPT", "UNAVAILABLE"):
            return 2
        if st in ("STALE", "EMPTY", "DEGRADED", "REBUILD_REQUIRED", "DISABLED"):
            return 1
        return 0

    if cmd == "index":
        data = rt.index(dry_run=args.dry_run)
        _print(data, as_json=args.json)
        return 0 if data.get("ok") else 2

    if cmd == "refresh":
        data = rt.refresh()
        _print(data, as_json=args.json)
        return 0 if data.get("ok") else 2

    if cmd == "rebuild":
        data = rt.rebuild(dry_run=args.dry_run)
        _print(data, as_json=args.json)
        return 0 if data.get("ok") else 2

    if cmd == "search":
        if not args.query:
            print("usage: search <query>", file=sys.stderr)
            return 2
        data = rt.search(
            args.query, top_k=args.top_k,
            documentation_only=args.docs, tests_only=args.tests,
        )
        _print(data, as_json=args.json)
        if data.get("denied"):
            return 2
        return 0 if data.get("ok") else 1

    if cmd == "symbol":
        if not args.query:
            print("usage: symbol <name>", file=sys.stderr)
            return 2
        data = rt.symbol(args.query, top_k=args.top_k)
        _print(data, as_json=args.json)
        return 0 if data.get("ok") else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
