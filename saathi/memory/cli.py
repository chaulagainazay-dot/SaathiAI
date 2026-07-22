"""M9 Memory CLI — `python -m saathi.memory.cli <cmd>`.

Commands:
  inspect            engine + provider + stats (read-only)
  search "<query>"   scoped hybrid retrieval (read-only)
  health             stats + embedding coverage (read-only)
  reindex [--batch N] bounded, resumable re-embedding
  conflicts          list open conflicts (read-only)
  stats              memory stats (read-only)
  export [ns]        export memories as JSON (read-only)
  decay              age stale/expired memories (mutating; explicit)

Exit codes: 0 ok · 1 has-open-conflicts/incomplete · 2 bad command.
"""
from __future__ import annotations

import json
import sys

from saathi.memory.engine import default_engine, plan_query

EXIT_OK, EXIT_ATTN, EXIT_BAD = 0, 1, 2


def _emit(obj) -> None:
    print(json.dumps(obj, indent=1, default=str))


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return EXIT_OK
    cmd, *rest = argv
    eng = default_engine()

    if cmd in ("inspect", "health", "stats"):
        _emit({"embedder": eng.embedder.provider,
               "embedding_version": eng.embedder.version,
               "stats": eng.store.stats()})
        return EXIT_OK
    if cmd == "search":
        if not rest:
            _emit({"error": "usage: search \"<query>\""})
            return EXIT_BAD
        plan = plan_query(user="ajay", top_k=10)
        results, mode, _ = eng.retrieve(rest[0], plan=plan, actor="cli")
        _emit({"mode": mode, "results": [
            {"score": r.final_score, "type": r.memory_type,
             "content": r.content[:120], "reason": r.reason} for r in results]})
        return EXIT_OK
    if cmd == "conflicts":
        c = eng.store.conflicts()
        _emit({"open_conflicts": c})
        return EXIT_ATTN if c else EXIT_OK
    if cmd == "reindex":
        batch = 200
        if len(rest) >= 2 and rest[0] == "--batch":
            try:
                batch = int(rest[1])
            except ValueError:
                return EXIT_BAD
        r = eng.reindex(batch=batch)
        _emit(r)
        return EXIT_OK if r["complete"] else EXIT_ATTN
    if cmd == "export":
        ns = [rest[0]] if rest else None
        items = eng.store.list_items(namespaces=ns, limit=100_000)
        _emit({"count": len(items), "memories": items})
        return EXIT_OK
    if cmd == "decay":
        _emit(eng.decay())
        return EXIT_OK

    print(f"unknown command: {cmd}\n{__doc__}")
    return EXIT_BAD


if __name__ == "__main__":
    raise SystemExit(main())
