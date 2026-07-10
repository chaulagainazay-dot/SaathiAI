"""M10 task graph — DAG with cycle detection and ready-task scheduling."""
from __future__ import annotations

from saathi.agent_runtime.models import Task


class CycleError(Exception):
    pass


class TaskGraph:
    def __init__(self, tasks: list[Task]):
        self.tasks: dict[str, Task] = {t.task_id: t for t in tasks}
        if len(self.tasks) != len(tasks):
            raise ValueError("duplicate task ids")
        self._validate_deps()
        self.detect_cycle()  # fail before execution

    def _validate_deps(self) -> None:
        for t in self.tasks.values():
            for d in t.dependencies:
                if d not in self.tasks:
                    raise ValueError(f"task {t.task_id} depends on unknown {d}")

    def detect_cycle(self) -> None:
        """Kahn's algorithm; raises CycleError with the involved nodes."""
        indeg = {tid: 0 for tid in self.tasks}
        for t in self.tasks.values():
            for _d in t.dependencies:
                indeg[t.task_id] += 1
        queue = [tid for tid, n in indeg.items() if n == 0]
        seen = 0
        while queue:
            tid = queue.pop()
            seen += 1
            for other in self.tasks.values():
                if tid in other.dependencies:
                    indeg[other.task_id] -= 1
                    if indeg[other.task_id] == 0:
                        queue.append(other.task_id)
        if seen != len(self.tasks):
            stuck = [tid for tid, n in indeg.items() if n > 0]
            raise CycleError(f"cycle detected among: {stuck}")

    def ready(self) -> list[Task]:
        """Pending tasks whose dependencies are all done."""
        done = {t.task_id for t in self.tasks.values() if t.status == "done"}
        out = []
        for t in self.tasks.values():
            if t.status in ("pending", "ready") and all(d in done for d in t.dependencies):
                out.append(t)
        return out

    def blocked(self) -> list[Task]:
        """Pending tasks with a failed/cancelled dependency (cannot proceed)."""
        bad = {t.task_id for t in self.tasks.values()
               if t.status in ("failed", "cancelled", "skipped")}
        out = []
        for t in self.tasks.values():
            if t.status in ("pending", "ready") and any(d in bad for d in t.dependencies):
                out.append(t)
        return out

    def all_done(self) -> bool:
        return all(t.status in ("done", "skipped", "cancelled")
                   for t in self.tasks.values())

    def topo_order(self) -> list[str]:
        self.detect_cycle()
        indeg = {tid: len(t.dependencies) for tid, t in self.tasks.items()}
        order, queue = [], sorted([tid for tid, n in indeg.items() if n == 0])
        while queue:
            tid = queue.pop(0)
            order.append(tid)
            for other in self.tasks.values():
                if tid in other.dependencies:
                    indeg[other.task_id] -= 1
                    if indeg[other.task_id] == 0:
                        queue.append(other.task_id)
            queue.sort()
        return order
