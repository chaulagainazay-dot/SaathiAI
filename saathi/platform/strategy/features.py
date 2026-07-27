"""M62.4 — time-aware feature generation with structural look-ahead prevention.

Two guarantees:

1. A feature is computed ONLY from bars ending at (and including) the decision bar.
   The guarded ``BacktestContext`` records the maximum bar timestamp any feature or
   signal touched during a decision; the engine fails the run if that maximum ever
   exceeds the decision timestamp. This catches leakage structurally, not by review.

2. A ``FeatureSpec`` with ``forward_offset > 0`` is a future-data request and is
   rejected before any run starts (see ``validation.validate_strategy``).

Numeric precision: Decimal throughout. Missing warm-up windows yield ``None`` (the
feature is "not ready"), never a silently forward-filled value.
"""
from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Any

from saathi.platform.market_data.models import MDBar
from saathi.platform.strategy.models import FeatureSpec, FeatureKind

getcontext().prec = 34


class LookAheadViolation(Exception):
    """Raised the instant a decision touches a bar dated after the decision bar."""


def _sqrt(x: Decimal) -> Decimal:
    if x <= 0:
        return Decimal("0")
    # Decimal.sqrt honours the context precision; deterministic.
    return x.sqrt()


class BacktestContext:
    """The ONLY view a strategy decision gets of the world. It exposes bars strictly
    up to ``cursor`` (the decision bar index) and refuses any access beyond it.

    ``max_accessed_epoch`` is the high-water mark of bar timestamps touched. The
    engine compares it to the decision bar's timestamp after every decision.
    """

    def __init__(self, bars: list[MDBar]):
        # bars MUST be pre-sorted ascending by start_time (engine guarantees this)
        self._bars = bars
        self._cursor = 0
        self.max_accessed_epoch: float = -1.0
        self.decision_epoch: float = -1.0
        self.portfolio: Any = None            # set by engine each bar
        self.last_features: dict[str, Decimal | None] = {}
        self.prev_features: dict[str, Decimal | None] = {}

    # ── engine-controlled cursor ─────────────────────────────────────────
    def _set_cursor(self, i: int) -> None:
        self._cursor = i
        self.decision_epoch = self._bars[i].start_time.timestamp()

    def _touch(self, epoch: float) -> None:
        if epoch > self.max_accessed_epoch:
            self.max_accessed_epoch = epoch

    # ── guarded access (what a strategy may see) ─────────────────────────
    def current_bar(self) -> MDBar:
        b = self._bars[self._cursor]
        self._touch(b.start_time.timestamp())
        return b

    def bar_at(self, offset: int) -> MDBar:
        """offset 0 == decision bar, negative == earlier. Positive is ILLEGAL."""
        if offset > 0:
            # a strategy explicitly reaching into the future — hard fail
            raise LookAheadViolation(f"future bar access offset={offset} at cursor={self._cursor}")
        idx = self._cursor + offset
        if idx < 0:
            raise IndexError("before series start")
        b = self._bars[idx]
        self._touch(b.start_time.timestamp())
        return b

    def future_peek(self, offset: int) -> MDBar:
        """Deliberately UNGUARDED forward access used only to exercise the engine's
        look-ahead instrumentation: it RECORDS the accessed (future) timestamp so the
        engine's post-decision check (max_accessed_epoch > decision_epoch) fails the
        run. A leaking strategy fixture calls this; the run is then rejected."""
        idx = self._cursor + offset
        if idx >= len(self._bars):
            idx = len(self._bars) - 1
        b = self._bars[idx]
        self._touch(b.start_time.timestamp())
        return b

    def window(self, n: int) -> list[MDBar]:
        """Last ``n`` bars up to and including the decision bar."""
        start = max(0, self._cursor - n + 1)
        w = self._bars[start:self._cursor + 1]
        for b in w:
            self._touch(b.start_time.timestamp())
        return w

    def feature(self, name: str) -> Decimal | None:
        return self.last_features.get(name)


def compute_feature(spec: FeatureSpec, window_bars: list[MDBar]) -> Decimal | None:
    """Compute one feature from a window whose LAST element is the decision bar.

    Returns ``None`` when the warm-up window is not yet full (feature not ready).
    Never reaches beyond the provided window, so it cannot see the future.
    """
    lb = spec.lookback
    if lb < 1:
        return None
    # need lb+1 closes for return/momentum (delta), lb for averages/highs
    needs = lb + 1 if spec.kind in (FeatureKind.RETURN, FeatureKind.MOMENTUM, FeatureKind.VOLATILITY) else lb
    if len(window_bars) < needs:
        return None

    def sel(b: MDBar) -> Decimal:
        return {"close": b.close, "open": b.open, "high": b.high, "low": b.low, "volume": b.volume}[spec.source]

    vals = [sel(b) for b in window_bars]
    cur = vals[-1]

    if spec.kind == FeatureKind.SMA:
        w = vals[-lb:]
        return sum(w) / Decimal(len(w))
    if spec.kind == FeatureKind.ROLLING_HIGH:
        return max(vals[-lb:])
    if spec.kind == FeatureKind.ROLLING_LOW:
        return min(vals[-lb:])
    if spec.kind == FeatureKind.VOLUME_AVG:
        w = [b.volume for b in window_bars][-lb:]
        return sum(w) / Decimal(len(w))
    if spec.kind == FeatureKind.RETURN:
        base = vals[-lb - 1]
        if base == 0:
            return None
        return (cur - base) / base
    if spec.kind == FeatureKind.MOMENTUM:
        base = vals[-lb - 1]
        return cur - base
    if spec.kind == FeatureKind.PRICE_DEVIATION:
        w = vals[-lb:]
        sma = sum(w) / Decimal(len(w))
        if sma == 0:
            return None
        return (cur - sma) / sma
    if spec.kind == FeatureKind.VOLATILITY:
        closes = vals[-lb - 1:]
        rets = []
        for i in range(1, len(closes)):
            if closes[i - 1] == 0:
                continue
            rets.append((closes[i] - closes[i - 1]) / closes[i - 1])
        if len(rets) < 2:
            return None
        mean = sum(rets) / Decimal(len(rets))
        var = sum((r - mean) ** 2 for r in rets) / Decimal(len(rets) - 1)
        return _sqrt(var)
    return None


def compute_all(specs: list[FeatureSpec], ctx: BacktestContext) -> dict[str, Decimal | None]:
    """Compute every feature for the current cursor, using only guarded windows."""
    out: dict[str, Decimal | None] = {}
    for spec in specs:
        w = ctx.window(spec.lookback + 1)
        out[spec.name] = compute_feature(spec, w)
    return out
