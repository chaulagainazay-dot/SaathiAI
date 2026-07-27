"""M62.4 — dataset splitting + walk-forward evaluation.

Time series are NEVER shuffled. Splits are chronological, contiguous, and
non-overlapping; ``check_splits`` detects overlap or reordering. TEST is treated as
untouched until final evaluation — the caller records which parameters were selected
BEFORE any test metric is read (``selected_before_test``).

Walk-forward supports expanding and rolling windows. Every fold records its train /
validation / test ranges, parameters, trade count, dataset hash, and status. Failed
folds are surfaced, never averaged away.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class SplitKind(str, Enum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"


@dataclass(frozen=True)
class Split:
    kind: SplitKind
    start_epoch: float
    end_epoch: float          # exclusive upper bound

    def contains(self, epoch: float) -> bool:
        return self.start_epoch <= epoch < self.end_epoch

    def to_public(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "start_epoch": self.start_epoch, "end_epoch": self.end_epoch}


def make_chronological_splits(epochs: list[float], *, train: float = 0.6, validation: float = 0.2) -> list[Split]:
    """Split sorted epochs into contiguous TRAIN/VALIDATION/TEST by fraction. TEST is
    whatever remains. Raises on non-sorted input (no shuffling permitted)."""
    if epochs != sorted(epochs):
        raise ValueError("epochs must be chronologically sorted (time series are not shuffled)")
    if not (0 < train < 1 and 0 <= validation < 1 and train + validation < 1):
        raise ValueError("invalid split fractions")
    n = len(epochs)
    if n < 3:
        raise ValueError("need >= 3 observations to split")
    i_train = max(1, int(n * train))
    i_val = max(i_train + 1, int(n * (train + validation)))
    i_val = min(i_val, n - 1)
    step = epochs[-1] - epochs[-2] if n >= 2 else 1.0
    upper = epochs[-1] + step
    return [
        Split(SplitKind.TRAIN, epochs[0], epochs[i_train]),
        Split(SplitKind.VALIDATION, epochs[i_train], epochs[i_val]),
        Split(SplitKind.TEST, epochs[i_val], upper),
    ]


def check_splits(splits: list[Split]) -> list[str]:
    """Detect overlap, gaps into disorder, or non-chronological ordering."""
    errors: list[str] = []
    ordered = sorted(splits, key=lambda s: s.start_epoch)
    for a, b in zip(ordered, ordered[1:]):
        if b.start_epoch < a.end_epoch:
            errors.append(f"overlap: {a.kind.value}[..{a.end_epoch}) & {b.kind.value}[{b.start_epoch}..)")
    # enforce canonical TRAIN < VALIDATION < TEST ordering when all present
    kinds = [s.kind for s in ordered]
    if SplitKind.TEST in kinds and SplitKind.TRAIN in kinds:
        test = next(s for s in ordered if s.kind == SplitKind.TEST)
        train = next(s for s in ordered if s.kind == SplitKind.TRAIN)
        if test.start_epoch < train.end_epoch:
            errors.append("TEST begins before TRAIN ends")
    for s in splits:
        if s.end_epoch <= s.start_epoch:
            errors.append(f"{s.kind.value} has non-positive span")
    return errors


def partition_epochs(epochs: list[float], split: Split) -> list[float]:
    return [e for e in epochs if split.contains(e)]


# ── walk-forward ─────────────────────────────────────────────────────────────
@dataclass
class Fold:
    index: int
    train_range: tuple[float, float]
    validation_range: tuple[float, float]
    test_range: tuple[float, float]
    parameters: dict[str, Any]
    dataset_hash: str
    strategy_version: int
    metrics: dict[str, Any] = field(default_factory=dict)
    trade_count: int = 0
    status: str = "PENDING"          # PENDING | OK | FAILED | EMPTY
    selected_before_test: bool = True

    def to_public(self) -> dict[str, Any]:
        return {"index": self.index, "train_range": list(self.train_range),
                "validation_range": list(self.validation_range), "test_range": list(self.test_range),
                "parameters": self.parameters, "dataset_hash": self.dataset_hash,
                "strategy_version": self.strategy_version, "metrics": self.metrics,
                "trade_count": self.trade_count, "status": self.status,
                "selected_before_test": self.selected_before_test}


def build_folds(
    epochs: list[float],
    *,
    n_folds: int = 3,
    mode: str = "expanding",     # expanding | rolling
    train_min: int = 10,
    test_size: int = 5,
) -> list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]]:
    """Return list of (train_range, validation_range, test_range) epoch tuples.

    Ranges are half-open [start, end). Validation is the tail of train used for
    parameter selection; TEST always follows the train/validation window in time.
    """
    if epochs != sorted(epochs):
        raise ValueError("epochs must be sorted")
    n = len(epochs)
    if n < train_min + test_size:
        raise ValueError("not enough observations for the requested walk-forward")
    step = (epochs[-1] - epochs[-2]) if n >= 2 else 1.0

    folds = []
    max_start = n - test_size
    # place test windows sequentially after the initial train_min
    positions = list(range(train_min, max_start + 1, test_size))
    if not positions:
        positions = [train_min]
    positions = positions[:n_folds]
    for k, tstart in enumerate(positions):
        tend = min(tstart + test_size, n)
        train_start_idx = 0 if mode == "expanding" else max(0, tstart - train_min)
        train_end_idx = tstart
        val_start_idx = max(train_start_idx + 1, train_end_idx - test_size)
        train_range = (epochs[train_start_idx], epochs[val_start_idx])
        val_range = (epochs[val_start_idx], epochs[train_end_idx])
        test_upper = epochs[tend - 1] + step
        test_range = (epochs[tstart], test_upper)
        folds.append((train_range, val_range, test_range))
    return folds


def aggregate_folds(folds: list[Fold]) -> dict[str, Any]:
    """Aggregate WITHOUT hiding failures. Reports counts of ok/failed/empty and the
    worst test drawdown observed across all folds."""
    ok = [f for f in folds if f.status == "OK"]
    failed = [f for f in folds if f.status == "FAILED"]
    empty = [f for f in folds if f.status == "EMPTY"]
    worst_dd = Decimal("0")
    returns = []
    for f in ok:
        dd = f.metrics.get("max_drawdown")
        if dd is not None:
            worst_dd = max(worst_dd, Decimal(str(dd)))
        r = f.metrics.get("total_return")
        if r is not None:
            returns.append(Decimal(str(r)))
    consistent = len(failed) == 0 and (not returns or all(r is not None for r in returns))
    avg_return = (sum(returns) / Decimal(len(returns))) if returns else None
    return {
        "n_folds": len(folds), "ok": len(ok), "failed": len(failed), "empty": len(empty),
        "worst_test_drawdown": str(worst_dd),
        "avg_test_return": (str(avg_return) if avg_return is not None else None),
        "consistent": consistent,
        "folds": [f.to_public() for f in folds],
    }
