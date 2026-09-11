"""CI-LANES-1 — certification lane definitions.

One place that defines what each certification lane runs and whether it is allowed
to touch the network. The governing rule: **deterministic core certification must
never require live network**. Only the explicitly-labelled canary lane may.

Each lane carries a pytest marker expression and/or keyword selector so CI and a
developer run the identical selection.
"""
from __future__ import annotations

from dataclasses import dataclass


# Marker expression that excludes every non-deterministic category.
OFFLINE_MARKERS = "not browser and not live and not external and not network"


@dataclass(frozen=True)
class Lane:
    name: str
    marker_expr: str
    keyword: str = ""
    network_allowed: bool = False
    required_for_certification: bool = True
    description: str = ""

    def pytest_args(self, target: str = "tests") -> list[str]:
        args = [target, "-q", "-m", self.marker_expr]
        if self.keyword:
            args += ["-k", self.keyword]
        return args


LANES: tuple[Lane, ...] = (
    Lane("OFFLINE_CORE", OFFLINE_MARKERS, "",
         description="whole deterministic suite; the gate for every milestone"),
    Lane("TRADING_AUTHORITY", OFFLINE_MARKERS,
         "guardian or policy or risk or approval or gateway or execution",
         description="authority boundaries: guardian, risk, approval, execution"),
    Lane("RESEARCH", OFFLINE_MARKERS, "research or evidence or thesis or durability",
         description="research evidence, challenge protocol, durability"),
    Lane("SIGNAL", OFFLINE_MARKERS, "signal or intent",
         description="signal/intent contracts; no execution authority"),
    Lane("BACKTEST", OFFLINE_MARKERS, "backtest or cost or oos or walk_forward or strategy",
         description="convergence, cost policy, OOS and point-in-time discipline"),
    Lane("NEPSE", OFFLINE_MARKERS, "nepse or calendar or meroshare or tms",
         description="NEPSE calendar, transactions, ledger proposals"),
    Lane("CRYPTO", OFFLINE_MARKERS, "crypto or binance or dataset",
         description="crypto dataset, adapters and strategy qualification"),
    Lane("PORTFOLIO", OFFLINE_MARKERS, "portfolio or construction or allocation or attribution",
         description="construction, risk, attribution"),
    Lane("PAPER", OFFLINE_MARKERS, "paper or oms or simulation or activation",
         description="paper OMS, execution simulation, paper cycle"),
    Lane("REPLAY", OFFLINE_MARKERS, "replay or historical or point_in_time or pit",
         description="deterministic replay and point-in-time safety"),
    Lane("RESILIENCE_SECURITY", OFFLINE_MARKERS, "resilience or security or reconcil",
         description="degradation policy, egress guard, reconciliation"),
    Lane("BROWSER_UI", "browser", "", network_allowed=False,
         required_for_certification=False,
         description="browser certification; excluded from the deterministic core"),
    Lane("PUBLIC_LIVE_DATA_CANARY", "live or network or external", "",
         network_allowed=True, required_for_certification=False,
         description="ONLY lane permitted live public market data; never gates core"),
)

LANES_BY_NAME = {lane.name: lane for lane in LANES}


def core_lanes() -> tuple[Lane, ...]:
    """Lanes that gate milestone certification. All must be offline."""
    return tuple(lane for lane in LANES if lane.required_for_certification)


def network_lanes() -> tuple[Lane, ...]:
    return tuple(lane for lane in LANES if lane.network_allowed)


def certification_policy() -> dict:
    return {
        "core_offline_only": True,
        "core_lane_count": len(core_lanes()),
        "network_lane_count": len(network_lanes()),
        "network_lanes": [lane.name for lane in network_lanes()],
        "core_marker_expression": OFFLINE_MARKERS,
        "note": "a live-data failure can never block deterministic certification",
    }
