"""M62.4 — deterministic signal generation from declarative rules.

A rule compares a feature (``left``) against a feature or numeric constant (``right``)
with a comparator, and emits an action. CROSS_ABOVE / CROSS_BELOW use the previous
bar's feature values (already computed, never the future). Rules are evaluated in
declaration order; the first ENTER/EXIT that fires wins for the bar (deterministic
priority). Duplicate identical signals on the same bar are collapsed.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from saathi.platform.strategy.models import SignalRule, Comparator, SignalAction


def _as_number(token: str) -> Decimal | None:
    try:
        return Decimal(str(token))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _resolve(token: str, features: dict[str, Decimal | None]) -> Decimal | None:
    if token in features:
        return features[token]
    return _as_number(token)


def _compare(left: Decimal, comp: Comparator, right: Decimal) -> bool:
    if comp == Comparator.GT:
        return left > right
    if comp == Comparator.GTE:
        return left >= right
    if comp == Comparator.LT:
        return left < right
    if comp == Comparator.LTE:
        return left <= right
    return False


def evaluate_signals(
    rules: list[SignalRule],
    features: dict[str, Decimal | None],
    prev_features: dict[str, Decimal | None],
) -> tuple[SignalAction | None, str]:
    """Return the winning action (or None) and a human-readable signal reference.

    A rule is SKIPPED (not fired) if any operand it needs is None (feature not warm).
    This is a fail-safe: an unwarmed feature never triggers a trade.
    """
    for idx, rule in enumerate(rules):
        left = features.get(rule.left)
        if left is None:
            continue
        if rule.comparator in (Comparator.CROSS_ABOVE, Comparator.CROSS_BELOW):
            prev_left = prev_features.get(rule.left)
            right_now = _resolve(rule.right, features)
            right_prev = _resolve(rule.right, prev_features)
            if prev_left is None or right_now is None or right_prev is None:
                continue
            if rule.comparator == Comparator.CROSS_ABOVE:
                fired = prev_left <= right_prev and left > right_now
            else:
                fired = prev_left >= right_prev and left < right_now
        else:
            right = _resolve(rule.right, features)
            if right is None:
                continue
            fired = _compare(left, rule.comparator, right)
        if fired:
            return rule.action, f"rule[{idx}]:{rule.left}{rule.comparator.value}{rule.right}"
    return None, ""
