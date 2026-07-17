"""M29 — Connector dependency graph validation (cycle rejection)."""
from __future__ import annotations

from typing import Iterable, Mapping


class DependencyError(ValueError):
    pass


class DependencyCycleError(DependencyError):
    pass


def validate_dependency_graph(
    edges: Mapping[str, Iterable[str]],
    *,
    known_ids: Iterable[str] | None = None,
) -> dict:
    """Validate explicit dependencies.

    ``edges`` maps connector_id → iterable of dependency connector_ids.
    Cycles raise DependencyCycleError. Missing deps raise DependencyError
    when ``known_ids`` is provided.
    """
    graph: dict[str, list[str]] = {
        str(k): [str(d) for d in (v or [])] for k, v in edges.items()
    }
    known = set(known_ids) if known_ids is not None else set(graph.keys())
    # Ensure all nodes present
    for deps in list(graph.values()):
        for d in deps:
            graph.setdefault(d, [])
            known.add(d)
    for node in list(known):
        graph.setdefault(node, [])

    missing: list[tuple[str, str]] = []
    if known_ids is not None:
        known_set = set(known_ids)
        for src, deps in graph.items():
            if src not in known_set and src in edges:
                # source not registered
                missing.append((src, "<self>"))
            for d in deps:
                if d not in known_set:
                    missing.append((src, d))
        if missing:
            raise DependencyError(
                "undeclared_dependencies:" + ",".join(f"{a}->{b}" for a, b in missing)
            )

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    path: list[str] = []

    def visit(n: str) -> None:
        color[n] = GRAY
        path.append(n)
        for d in graph.get(n, []):
            if color.get(d, WHITE) == GRAY:
                cycle_start = path.index(d)
                cycle = path[cycle_start:] + [d]
                raise DependencyCycleError("dependency_cycle:" + "->".join(cycle))
            if color.get(d, WHITE) == WHITE:
                visit(d)
        path.pop()
        color[n] = BLACK

    for n in sorted(graph.keys()):
        if color[n] == WHITE:
            visit(n)

    return {
        "ok": True,
        "nodes": sorted(graph.keys()),
        "edge_count": sum(len(v) for v in graph.values()),
    }
