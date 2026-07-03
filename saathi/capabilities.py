"""Platform Capability Registry — the operational heartbeat of SaathiAI.

The live, queryable source of truth for the Capability Maturity Matrix: for each
platform capability, its version and where it stands across Designed → Built →
Tested → Production. Mission Control renders this; BUILD_STATUS.md mirrors it.

Keeping it as data (not just a hand-edited markdown table) means the dashboard,
Telegram, and future automation can all read the same maturity state.

Testable in isolation (AP-12): construct, seed, query — no server.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class Capability:
    name: str
    version: str
    designed: bool = False
    built: bool = False
    tested: bool = False
    production: bool = False

    @property
    def maturity(self) -> str:
        # The furthest stage reached (stages are cumulative).
        if self.production:
            return "production"
        if self.tested:
            return "tested"
        if self.built:
            return "built"
        if self.designed:
            return "designed"
        return "planned"


class CapabilityRegistry:
    def __init__(self) -> None:
        self._caps: dict[str, Capability] = {}

    def register(self, cap: Capability) -> None:
        self._caps[cap.name] = cap

    def set_status(self, name: str, **flags) -> Capability:
        cap = self._caps[name]
        for k, v in flags.items():
            setattr(cap, k, v)
        return cap

    def get(self, name: str) -> Capability | None:
        return self._caps.get(name)

    def all(self) -> list[Capability]:
        return list(self._caps.values())

    def snapshot(self) -> list[dict]:
        return [asdict(c) | {"maturity": c.maturity} for c in self._caps.values()]

    def production_ready(self) -> list[str]:
        return [c.name for c in self._caps.values() if c.production]


def default_registry() -> CapabilityRegistry:
    """Seeded with SaathiAI's current maturity (mirrors BUILD_STATUS, 2026-07-02)."""
    r = CapabilityRegistry()
    D = dict  # noqa
    for name, ver, des, blt, tst, prod in [
        ("Storage Intelligence", "1.0", True, True, True, True),
        ("Event Fabric",         "1.0", True, True, True, False),
        ("Agent Runtime (BMA)",  "1.0", True, True, True, True),
        ("Agent Registry",       "1.0", True, True, True, True),
        ("Model Router",         "1.0", True, True, True, True),
        ("Tool Registry",        "1.0", True, True, True, True),
        ("Memory",               "0.9", True, True, False, False),
        ("Platform Memory",      "1.0", True, True, True, False),
        ("Memory Promotion Engine", "1.0", True, True, True, False),
        ("Knowledge Governance (Review Queue)", "1.0", True, True, True, False),
        ("Learning Engine",      "1.0", True, True, True, False),
        ("Capability Improvement Registry", "1.0", True, True, True, False),
        ("Knowledge Graph",      "1.0", True, True, True, False),
        ("Knowledge Publication Engine", "1.0", True, True, True, False),
        ("Content Factory",      "1.0", True, True, True, False),
        ("Revenue Engine",       "1.0", True, True, True, False),
        ("Audience Intelligence", "1.0", True, True, True, False),
        ("Business OS",          "1.0", True, True, True, False),
        ("Enterprise KPI Engine", "1.0", True, True, True, False),
        ("Executive Intelligence", "1.0", True, True, True, False),
        ("Investment Intelligence", "1.0", True, True, True, False),
        ("Capital Allocation Engine", "1.0", True, True, True, False),
        ("Research Department", "1.0", True, True, True, False),
        ("Research Confidence Framework", "1.0", True, True, True, False),
        ("Opportunity Intelligence", "1.0", True, True, True, False),
        ("Opportunity Memory", "1.0", True, True, True, False),
        ("Runtime Governance Engine", "1.0", True, True, True, True),
        ("Mission Control",      "0.8", True, True, True, True),
        ("Voice OS",             "0.6", True, True, False, False),
        ("AI Studio",            "0.5", True, True, False, False),
        ("Discovery Engine",     "0.4", True, True, False, False),
    ]:
        r.register(Capability(name, ver, des, blt, tst, prod))
    return r


# Process-wide registry.
registry = default_registry()
