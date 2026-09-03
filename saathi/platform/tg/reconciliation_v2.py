"""RECONCILIATION-V2 — multi-market snapshot reconciliation authority.

Extends reconciliation across the markets the program now spans, without creating a
competing books authority: the Canonical Fund Ledger stays the source of truth and
this layer only CLASSIFIES agreement between an expected (ledger) view and an
observed (venue/broker) snapshot.

Sources: paper crypto, paper NEPSE, and a future REAL read-only account snapshot.

Non-negotiable semantics:
  * MISMATCH / UNKNOWN / DATA_INSUFFICIENT are fail-closed states.
  * A later healthy snapshot NEVER silently clears an open finding. Ambiguity is
    cleared only by an explicit, recorded resolution.
  * Absent observation is DATA_INSUFFICIENT — never "assume equal".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class ReconSource(str, Enum):
    PAPER_CRYPTO = "PAPER_CRYPTO"
    PAPER_NEPSE = "PAPER_NEPSE"
    REAL_READONLY = "REAL_READONLY"   # future; read-only, never order-capable


class ReconStatus(str, Enum):
    HEALTHY = "HEALTHY"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


# Everything except HEALTHY blocks downstream trading until explicitly resolved.
_FAIL_CLOSED = {ReconStatus.MISMATCH, ReconStatus.UNKNOWN, ReconStatus.DATA_INSUFFICIENT}


@dataclass(frozen=True)
class ReconFinding:
    source: ReconSource
    instrument_id: str
    status: ReconStatus
    expected: Decimal | None
    observed: Decimal | None
    detail: str = ""

    @property
    def blocking(self) -> bool:
        return self.status in _FAIL_CLOSED


@dataclass
class ReconResult:
    source: ReconSource
    status: ReconStatus
    findings: tuple[ReconFinding, ...] = ()

    @property
    def blocking(self) -> bool:
        return self.status in _FAIL_CLOSED

    def to_public(self) -> dict:
        return {
            "source": self.source.value,
            "status": self.status.value,
            "blocking": self.blocking,
            "findings": [
                {
                    "instrument_id": f.instrument_id,
                    "status": f.status.value,
                    "expected": None if f.expected is None else str(f.expected),
                    "observed": None if f.observed is None else str(f.observed),
                    "detail": f.detail,
                }
                for f in self.findings
            ],
        }


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def reconcile_snapshot(
    expected: dict,
    observed: dict | None,
    *,
    source: ReconSource,
    tolerance: Decimal | str = "0",
) -> ReconResult:
    """Classify agreement between an expected (ledger) and observed (venue) view.

    `expected` / `observed` map instrument_id -> quantity. `observed=None` means the
    venue view could not be obtained at all: DATA_INSUFFICIENT, never HEALTHY.
    """
    tol = _dec(tolerance)

    if observed is None:
        return ReconResult(
            source, ReconStatus.DATA_INSUFFICIENT,
            (ReconFinding(source, "*", ReconStatus.DATA_INSUFFICIENT, None, None,
                          "observed snapshot unavailable"),),
        )

    findings: list[ReconFinding] = []
    for instrument_id in sorted(set(expected) | set(observed)):
        exp_raw = expected.get(instrument_id)
        obs_raw = observed.get(instrument_id)

        if exp_raw is None:
            # Venue reports a position the books do not know about.
            findings.append(ReconFinding(
                source, instrument_id, ReconStatus.MISMATCH, None, _dec(obs_raw),
                "observed instrument absent from expected/ledger view",
            ))
            continue
        if obs_raw is None:
            # Books expect a position the venue did not report: not proof of zero.
            findings.append(ReconFinding(
                source, instrument_id, ReconStatus.DATA_INSUFFICIENT, _dec(exp_raw), None,
                "expected instrument missing from observed snapshot",
            ))
            continue

        exp, obs = _dec(exp_raw), _dec(obs_raw)
        if abs(exp - obs) > tol:
            findings.append(ReconFinding(
                source, instrument_id, ReconStatus.MISMATCH, exp, obs,
                f"quantity differs by {abs(exp - obs)} (tolerance {tol})",
            ))

    if not findings:
        return ReconResult(source, ReconStatus.HEALTHY, ())
    # Worst status wins; MISMATCH outranks DATA_INSUFFICIENT for reporting.
    status = ReconStatus.MISMATCH if any(
        f.status == ReconStatus.MISMATCH for f in findings
    ) else ReconStatus.DATA_INSUFFICIENT
    return ReconResult(source, status, tuple(findings))


@dataclass
class _OpenItem:
    source: ReconSource
    instrument_id: str
    status: ReconStatus
    detail: str
    resolved: bool = False
    resolution: str = ""


class ReconciliationAuthorityV2:
    """Holds open findings until they are EXPLICITLY resolved.

    A subsequent healthy snapshot does not clear an open item — that is the whole
    point of the authority. Downstream trading stays blocked while items are open.
    """

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], _OpenItem] = {}

    def record(self, result: ReconResult) -> None:
        for f in result.findings:
            if not f.blocking:
                continue
            key = (f.source.value, f.instrument_id)
            existing = self._items.get(key)
            if existing is not None and not existing.resolved:
                continue  # already open; never downgrade or overwrite silently
            if existing is not None and existing.resolved:
                # A resolved item can re-open on a NEW finding.
                pass
            self._items[key] = _OpenItem(f.source, f.instrument_id, f.status, f.detail)

    def open_items(self) -> list[dict]:
        return [
            {
                "source": i.source.value,
                "instrument_id": i.instrument_id,
                "status": i.status.value,
                "detail": i.detail,
            }
            for i in self._items.values()
            if not i.resolved
        ]

    def is_blocked(self, source: ReconSource | None = None) -> bool:
        for i in self._items.values():
            if i.resolved:
                continue
            if source is None or i.source == source:
                return True
        return False

    def resolve(self, source: ReconSource, instrument_id: str, *, actor: str, note: str) -> bool:
        """Explicitly resolve one open finding. Requires an actor and a note."""
        if not actor or not note:
            raise ValueError("explicit resolution requires actor and note")
        item = self._items.get((source.value, instrument_id))
        if item is None or item.resolved:
            return False
        item.resolved = True
        item.resolution = f"{actor}: {note}"
        return True
