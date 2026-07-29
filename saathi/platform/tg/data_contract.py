"""M177 — Authoritative backtest data classification contract.

Hard policy: AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA

Fixture metrics may only appear when classification is FIXTURE_TEST_ONLY or
SYNTHETIC_VALIDATION and never silently replace a failed historical run.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class DataClassification(str, Enum):
    HISTORICAL_AUTHENTICATED = "HISTORICAL_AUTHENTICATED"
    HISTORICAL_LOCAL_DATASET = "HISTORICAL_LOCAL_DATASET"
    SYNTHETIC_VALIDATION = "SYNTHETIC_VALIDATION"
    FIXTURE_TEST_ONLY = "FIXTURE_TEST_ONLY"
    INCOMPLETE = "INCOMPLETE"
    REJECTED = "REJECTED"


# Classifications that may never feed PAPER_ELIGIBLE promotion
NON_AUTHORITATIVE = frozenset({
    DataClassification.FIXTURE_TEST_ONLY,
    DataClassification.SYNTHETIC_VALIDATION,
    DataClassification.INCOMPLETE,
    DataClassification.REJECTED,
})

AUTHORITATIVE = frozenset({
    DataClassification.HISTORICAL_AUTHENTICATED,
    DataClassification.HISTORICAL_LOCAL_DATASET,
})

AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA = True

# Known M62 fixture dataset names — always synthetic/fixture class
M62_FIXTURE_DATASETS = frozenset({
    "TRENDING", "MEAN_REVERTING", "FLAT", "HIGH_VOLATILITY", "GAP_DOWN", "ILLIQUID",
    "FLASH_CRASH_LIKE", "MISSING_BARS", "OUT_OF_ORDER_BARS", "INVALID_OHLC",
    "CHOPPY", "GAPPED", "DEFECT_DUP",
})


class DataContractError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class DatasetProvenance:
    classification: DataClassification
    dataset_id: str
    dataset_fingerprint: str
    instrument_universe: list[str]
    timeframe: str
    date_range_start: float | None = None
    date_range_end: float | None = None
    bar_count: int = 0
    missing_bars: int = 0
    duplicate_bars: int = 0
    stale_bars: int = 0
    fee_bps: str = "0"
    spread_model: str = ""
    slippage_bps: str = "0"
    strategy_version: str = ""
    policy_version: str = "1.0.0"
    risk_policy_version: str = "1.0.0"
    source_path: str = ""
    notes: list[str] = field(default_factory=list)
    authoritative: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "classification": self.classification.value,
            "dataset_id": self.dataset_id,
            "dataset_fingerprint": self.dataset_fingerprint,
            "instrument_universe": list(self.instrument_universe),
            "timeframe": self.timeframe,
            "date_range_start": self.date_range_start,
            "date_range_end": self.date_range_end,
            "bar_count": self.bar_count,
            "missing_data_stats": {
                "missing_bars": self.missing_bars,
                "duplicate_bars": self.duplicate_bars,
                "stale_bars": self.stale_bars,
            },
            "fee_bps": self.fee_bps,
            "spread_model": self.spread_model,
            "slippage_bps": self.slippage_bps,
            "strategy_version": self.strategy_version,
            "policy_version": self.policy_version,
            "risk_policy_version": self.risk_policy_version,
            "source_path": self.source_path,
            "notes": list(self.notes),
            "authoritative": self.authoritative and self.classification in AUTHORITATIVE,
            "policy": "AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA",
            "paper_only": True,
            "disclaimer": (
                "Synthetic and fixture results are not market evidence. "
                "Historical results do not predict future results."
            ),
        }


def classify_dataset(
    dataset_id: str,
    *,
    explicit: str | DataClassification | None = None,
    is_test_context: bool = False,
    source_path: str = "",
) -> DataClassification:
    if explicit is not None:
        c = DataClassification(explicit) if not isinstance(explicit, DataClassification) else explicit
        return c
    ds = (dataset_id or "").upper()
    if ds in M62_FIXTURE_DATASETS or ds.startswith("FIXTURE") or ds.startswith("SYNTH"):
        return DataClassification.FIXTURE_TEST_ONLY if is_test_context else DataClassification.SYNTHETIC_VALIDATION
    if source_path or ds.startswith("LOCAL_") or ds.startswith("HIST_"):
        return DataClassification.HISTORICAL_LOCAL_DATASET
    if ds.startswith("AUTH_"):
        return DataClassification.HISTORICAL_AUTHENTICATED
    # Unknown non-fixture ids default to incomplete until provenance is attached
    return DataClassification.INCOMPLETE


def fingerprint_payload(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_bars(bars: list[Any]) -> str:
    proj = []
    for b in bars:
        if hasattr(b, "close"):
            proj.append({
                "i": getattr(b, "instrument", getattr(b, "symbol", "")),
                "ts": getattr(b, "start_time", None).timestamp() if hasattr(getattr(b, "start_time", None), "timestamp") else getattr(b, "ts", 0),
                "o": str(getattr(b, "open", "")),
                "h": str(getattr(b, "high", "")),
                "l": str(getattr(b, "low", "")),
                "c": str(getattr(b, "close", "")),
                "v": str(getattr(b, "volume", "")),
            })
        elif isinstance(b, dict):
            proj.append(b)
    return fingerprint_payload(proj)


def assert_authoritative_allowed(classification: DataClassification) -> None:
    if not AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA:
        return
    if classification in NON_AUTHORITATIVE:
        raise DataContractError(
            "AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA",
            f"classification {classification.value} cannot be used as authoritative market evidence",
        )


def is_authoritative(classification: DataClassification | str) -> bool:
    c = DataClassification(classification) if not isinstance(classification, DataClassification) else classification
    return c in AUTHORITATIVE


def build_provenance(
    *,
    dataset_id: str,
    bars: list[Any] | None = None,
    classification: DataClassification | None = None,
    instruments: list[str] | None = None,
    timeframe: str = "1d",
    strategy_version: str = "",
    policy_version: str = "1.0.0",
    fee_bps: str = "10",
    slippage_bps: str = "5",
    spread_model: str = "realistic",
    is_test_context: bool = False,
    source_path: str = "",
    notes: list[str] | None = None,
    missing_bars: int = 0,
    duplicate_bars: int = 0,
    stale_bars: int = 0,
) -> DatasetProvenance:
    cls = classification or classify_dataset(
        dataset_id, is_test_context=is_test_context, source_path=source_path,
    )
    bars = bars or []
    fp = fingerprint_bars(bars) if bars else fingerprint_payload({"dataset_id": dataset_id, "empty": True})
    start = end = None
    if bars:
        def _ts(b):
            st = getattr(b, "start_time", None)
            if st is not None and hasattr(st, "timestamp"):
                return st.timestamp()
            return float(getattr(b, "ts", 0) or 0)
        times = [_ts(b) for b in bars]
        start, end = min(times), max(times)
    univ = instruments or []
    if not univ and bars:
        b0 = bars[0]
        univ = [getattr(b0, "instrument", getattr(b0, "symbol", dataset_id))]
    return DatasetProvenance(
        classification=cls,
        dataset_id=dataset_id,
        dataset_fingerprint=fp,
        instrument_universe=list(univ),
        timeframe=timeframe,
        date_range_start=start,
        date_range_end=end,
        bar_count=len(bars),
        missing_bars=missing_bars,
        duplicate_bars=duplicate_bars,
        stale_bars=stale_bars,
        fee_bps=fee_bps,
        spread_model=spread_model,
        slippage_bps=slippage_bps,
        strategy_version=strategy_version,
        policy_version=policy_version,
        source_path=source_path,
        notes=list(notes or []),
        authoritative=cls in AUTHORITATIVE,
    )


def incomplete_result(
    *,
    reason: str,
    dataset_id: str = "",
    strategy_version: str = "",
    error: str = "",
) -> dict[str, Any]:
    """Fail-closed incomplete payload — never invents metrics."""
    prov = build_provenance(
        dataset_id=dataset_id or "UNKNOWN",
        classification=DataClassification.INCOMPLETE,
        strategy_version=strategy_version,
        notes=[reason, error] if error else [reason],
    )
    return {
        "status": "INCOMPLETE",
        "reason": reason,
        "error": error,
        "metrics": None,
        "authoritative": False,
        "data_classification": DataClassification.INCOMPLETE.value,
        "provenance": prov.to_public(),
        "evaluation_verdict": "INSUFFICIENT_EVIDENCE",
        "paper_only": True,
        "live_authorized": False,
        "fixture_metrics_used": False,
        "disclaimer": "Incomplete run — not market evidence. No fabricated metrics.",
    }


def rejected_result(*, reason: str, dataset_id: str = "", error: str = "") -> dict[str, Any]:
    prov = build_provenance(
        dataset_id=dataset_id or "UNKNOWN",
        classification=DataClassification.REJECTED,
        notes=[reason, error] if error else [reason],
    )
    return {
        "status": "REJECTED",
        "reason": reason,
        "error": error,
        "metrics": None,
        "authoritative": False,
        "data_classification": DataClassification.REJECTED.value,
        "provenance": prov.to_public(),
        "evaluation_verdict": "REJECTED",
        "paper_only": True,
        "live_authorized": False,
        "fixture_metrics_used": False,
    }
