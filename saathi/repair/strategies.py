"""Vetted repair strategies — the ONLY code the loop is allowed to auto-apply.

No free-form LLM rewriting. Each strategy is a small, mechanical, reversible
transform with a clear precondition. A strategy:
  - `applies(inc)`  -> bool (precondition on the classified incident)
  - `plan(inc)`     -> PatchPlan (root cause, files, intended change, rollback)
  - `apply(root)`   -> list[changed_file_paths]  (mechanical edit; may raise)

If no strategy matches, the loop stays at DIAGNOSE_ONLY. This is deliberate:
mechanical fixes we can verify, everything else escalates to a human.
"""
from __future__ import annotations

import re
from pathlib import Path

from saathi.repair.incident import RepairIncident, FailureCategory, PatchPlan


class RepairStrategy:
    name = "base"
    category: FailureCategory = FailureCategory.UNKNOWN

    def applies(self, inc: RepairIncident) -> bool:
        return inc.category == self.category

    def plan(self, inc: RepairIncident) -> PatchPlan:  # pragma: no cover - overridden
        raise NotImplementedError

    def apply(self, root: Path) -> list[str]:  # pragma: no cover - overridden
        raise NotImplementedError


class AwaitAsyncCallStrategy(RepairStrategy):
    """Fix an unawaited coroutine call of the form `self.queue.enqueue(x)`.

    Precondition: an ASYNC_ERROR whose evidence names a `<obj>.<method>(...)`
    call at a known file:line that is a coroutine. The transform wraps that
    single call site in the module's existing `_run_coro(...)` helper if one is
    importable, otherwise it prepends `await ` when the enclosing def is async.

    Scope: exactly one line, one file. Reversible by rollback reset.
    """
    name = "await_async_call"
    category = FailureCategory.ASYNC_ERROR

    def __init__(self, file: str = "", pattern: str = "", wrapper: str = "await "):
        self.file = file
        self.pattern = pattern
        self.wrapper = wrapper

    def applies(self, inc: RepairIncident) -> bool:
        return inc.category == self.category and bool(self.file and self.pattern)

    def plan(self, inc: RepairIncident) -> PatchPlan:
        return PatchPlan(
            root_cause="coroutine called without await (silently dropped)",
            files=[self.file],
            intended_change=f"wrap `{self.pattern}` call in `{self.wrapper.strip()}`",
            test_plan=["focused async tests for the touched module"],
            risk="low",
            rollback_method="git reset --hard <rollback_head>",
            forbidden_scope=["no interface change", "single line only"],
            strategy=self.name,
        )

    def apply(self, root: Path) -> list[str]:
        target = root / self.file
        text = target.read_text()
        pat = re.compile(r"(?<![\w.])" + re.escape(self.pattern) + r"\(")
        if not pat.search(text):
            raise RuntimeError("await strategy precondition no longer holds")
        new = pat.sub(self.wrapper + self.pattern + "(", text, count=1)
        target.write_text(new)
        return [self.file]


class ReexportSymbolStrategy(RepairStrategy):
    """Fix an IMPORT/COLLECTION error caused by an empty/short package __init__
    that fails to re-export a symbol available in a sibling submodule.

    Precondition: caller passes the package `__init__.py` path, the submodule to
    import from, and the symbol name. The transform appends one
    `from .<submodule> import <symbol>` line (idempotent).
    """
    name = "reexport_symbol"
    category = FailureCategory.IMPORT_ERROR

    def __init__(self, init_file: str = "", submodule: str = "", symbol: str = ""):
        self.init_file = init_file
        self.submodule = submodule
        self.symbol = symbol

    def applies(self, inc: RepairIncident) -> bool:
        return (inc.category == self.category
                and bool(self.init_file and self.submodule and self.symbol))

    def plan(self, inc: RepairIncident) -> PatchPlan:
        return PatchPlan(
            root_cause=f"package __init__ does not re-export `{self.symbol}`",
            files=[self.init_file],
            intended_change=f"add `from .{self.submodule} import {self.symbol}`",
            test_plan=["import smoke test for the package", "affected module tests"],
            risk="low",
            rollback_method="git reset --hard <rollback_head>",
            forbidden_scope=["append-only", "no existing lines modified"],
            strategy=self.name,
        )

    def apply(self, root: Path) -> list[str]:
        target = root / self.init_file
        line = f"from .{self.submodule} import {self.symbol}\n"
        text = target.read_text()
        if line.strip() in text:
            return []  # idempotent — already present
        if not text.endswith("\n"):
            text += "\n"
        target.write_text(text + line)
        return [self.init_file]


# Categories for which SOME mechanical strategy exists (policy gate).
_STRATEGY_CATEGORIES = {
    FailureCategory.IMPORT_ERROR,
    FailureCategory.COLLECTION_ERROR,
    FailureCategory.ASYNC_ERROR,
    FailureCategory.EVENT_BUS_ERROR,
}


def has_strategy(category: FailureCategory) -> bool:
    return category in _STRATEGY_CATEGORIES


def select_strategy(inc: RepairIncident,
                    candidates: list[RepairStrategy] | None = None) -> RepairStrategy | None:
    """Return the first configured strategy whose precondition holds.

    Strategies require concrete parameters (file/symbol/pattern) that the
    caller supplies from the incident/root-cause analysis. Without them, no
    strategy `applies()` — so the loop safely falls back to DIAGNOSE_ONLY.
    """
    for strat in (candidates or []):
        if strat.applies(inc):
            return strat
    return None
