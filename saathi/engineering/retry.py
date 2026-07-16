"""M20.0 — Bounded retry controller (no blind loops)."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from saathi.engineering.models import (
    NON_RECOVERABLE_FAILURES,
    RECOVERABLE_FAILURES,
)


@dataclass
class RetryRecord:
    failure_category: str
    hypothesis: str
    change_attempted: str
    result: str
    retry_count: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetryDecision:
    allow: bool
    reason: str
    retry_count: int
    max_retries: int
    category: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RetryController:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self._history: dict[str, list[RetryRecord]] = {}

    def history_for(self, issue_key: str) -> list[RetryRecord]:
        return list(self._history.get(issue_key, []))

    def classify_recoverable(self, category: str) -> bool:
        if category in NON_RECOVERABLE_FAILURES:
            return False
        return category in RECOVERABLE_FAILURES

    def decide(
        self,
        issue_key: str,
        category: str,
        *,
        hypothesis: str = "",
        identical_signature: str = "",
    ) -> RetryDecision:
        hist = self._history.setdefault(issue_key, [])
        count = len(hist)

        if category in NON_RECOVERABLE_FAILURES:
            return RetryDecision(
                allow=False,
                reason=f"non_recoverable:{category}",
                retry_count=count,
                max_retries=self.max_retries,
                category=category,
            )

        if category not in RECOVERABLE_FAILURES:
            return RetryDecision(
                allow=False,
                reason=f"unclassified_failure:{category}",
                retry_count=count,
                max_retries=self.max_retries,
                category=category,
            )

        if count >= self.max_retries:
            return RetryDecision(
                allow=False,
                reason="max_retries_reached",
                retry_count=count,
                max_retries=self.max_retries,
                category=category,
            )

        # Blind identical failure loop
        if identical_signature:
            same = [
                h for h in hist
                if h.failure_category == category
                and h.hypothesis == identical_signature
            ]
            if len(same) >= 2:
                return RetryDecision(
                    allow=False,
                    reason="repeated_identical_failure",
                    retry_count=count,
                    max_retries=self.max_retries,
                    category="repeated_identical_failure",
                )

        return RetryDecision(
            allow=True,
            reason="recoverable_retry_allowed",
            retry_count=count,
            max_retries=self.max_retries,
            category=category,
        )

    def record(
        self,
        issue_key: str,
        category: str,
        *,
        hypothesis: str,
        change_attempted: str,
        result: str,
    ) -> RetryRecord:
        hist = self._history.setdefault(issue_key, [])
        rec = RetryRecord(
            failure_category=category,
            hypothesis=hypothesis,
            change_attempted=change_attempted,
            result=result,
            retry_count=len(hist) + 1,
        )
        hist.append(rec)
        return rec
