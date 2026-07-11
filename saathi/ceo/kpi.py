"""M14 KPI engine — canonical percentage convention + metric-source truthfulness.

Reuses the verified `dream_progress_pct` (1.0 == 1% of target). When a KPI has
no verified observation, the engine returns UNAVAILABLE — it never fabricates a
value. Ratio-vs-percentage regression is guarded by tests.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from saathi.ceo.models import EvidenceTier
from saathi.financial_mission_control import dream_progress_pct, DREAM_TARGET

FRESH_SEC = 86400 * 2  # observations older than 2 days are "stale"


@dataclass
class KPIValue:
    kpi_id: str
    name: str
    kpi_type: str
    value: float | None
    unit: str
    target: float
    previous: float | None
    trend: str            # up | down | flat | unknown
    pct_to_target: float | None
    confidence: float
    freshness_sec: float | None
    evidence_tier: str
    source: str
    available: bool
    warn: bool
    critical: bool

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _trend(cur: float | None, prev: float | None) -> str:
    if cur is None or prev is None:
        return "unknown"
    if cur > prev * 1.001:
        return "up"
    if cur < prev * 0.999:
        return "down"
    return "flat"


def compute_kpi(store, kpi_id: str) -> KPIValue:
    kdef = store.get_kpi(kpi_id)
    if not kdef:
        raise KeyError(kpi_id)
    hist = store.observation_history(kpi_id, limit=2)
    if not hist:
        # NO verified data source — return UNAVAILABLE, never a guessed value
        return KPIValue(kpi_id=kpi_id, name=kdef["name"], kpi_type=kdef["kpi_type"],
                       value=None, unit=kdef["unit"], target=kdef["target"],
                       previous=None, trend="unknown", pct_to_target=None,
                       confidence=0.0, freshness_sec=None,
                       evidence_tier=EvidenceTier.UNAVAILABLE.value,
                       source="none", available=False, warn=False, critical=False)
    latest = hist[0]
    prev = hist[1]["value"] if len(hist) > 1 else None
    value = latest["value"]
    age = time.time() - latest["observed_at"]

    # canonical percentage-to-target (percentage points; 100 == target met)
    pct = None
    if kdef["target"]:
        if kdef["kpi_type"] == "dream_progress":
            pct = dream_progress_pct(value)  # 1.0 == 1% of DREAM_TARGET
        else:
            pct = round(value / kdef["target"] * 100, 2)

    warn = crit = False
    if kdef.get("critical_threshold") is not None and value <= kdef["critical_threshold"]:
        crit = True
    elif kdef.get("warn_threshold") is not None and value <= kdef["warn_threshold"]:
        warn = True

    return KPIValue(kpi_id=kpi_id, name=kdef["name"], kpi_type=kdef["kpi_type"],
                   value=value, unit=kdef["unit"], target=kdef["target"],
                   previous=prev, trend=_trend(value, prev), pct_to_target=pct,
                   confidence=0.9 if age < FRESH_SEC else 0.5, freshness_sec=round(age, 1),
                   evidence_tier=(EvidenceTier.CALCULATED.value if pct is not None
                                  else EvidenceTier.OBSERVED.value),
                   source=latest["source"], available=True, warn=warn, critical=crit)


def goal_progress(store, goal_id: str) -> dict:
    """Goal progress from canonical observations, NOT from agent text."""
    g = store.get_goal(goal_id)
    if not g:
        raise KeyError(goal_id)
    current = g["current_value"]
    tier = EvidenceTier.OBSERVED.value
    if g.get("kpi_id"):
        kv = compute_kpi(store, g["kpi_id"])
        if kv.available:
            current = kv.value
            tier = EvidenceTier.CALCULATED.value
        else:
            tier = EvidenceTier.UNAVAILABLE.value
    pct = (round(current / g["target_value"] * 100, 1)
           if g["target_value"] else None)
    return {"goal_id": goal_id, "current": current, "target": g["target_value"],
            "pct": pct, "unit": g["unit"], "evidence_tier": tier,
            "achieved": bool(g["target_value"] and current >= g["target_value"])}
