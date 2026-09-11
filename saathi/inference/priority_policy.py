"""Priority model classes and bounded budget policy.

The module supplies constraints to the existing ModelRouter. It does not
select or execute providers and therefore is not a second routing system.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from saathi.model_router import ModelLabel, Prefer


class MissionModelClass(str, Enum):
    LOCAL_ROUTINE = "local_routine"
    LOW_COST_CLOUD = "low_cost_cloud"
    CODING_PRIMARY = "coding_primary"
    MULTIMODAL = "multimodal"
    CRITICAL_EXPENSIVE = "critical_expensive"


@dataclass(frozen=True)
class RouteConstraints:
    label: ModelLabel
    prefer: Prefer
    approval_required: bool
    max_tool_iterations: int = 20
    max_parallel_cloud_agents: int = 1
    max_retries: int = 2


ROUTE_CONSTRAINTS = {
    MissionModelClass.LOCAL_ROUTINE: RouteConstraints(ModelLabel.PRIVATE, Prefer.COST, False),
    MissionModelClass.LOW_COST_CLOUD: RouteConstraints(ModelLabel.STANDARD, Prefer.COST, False),
    MissionModelClass.CODING_PRIMARY: RouteConstraints(ModelLabel.REASONING, Prefer.COST, False),
    MissionModelClass.MULTIMODAL: RouteConstraints(ModelLabel.MULTIMODAL, Prefer.COST, False),
    MissionModelClass.CRITICAL_EXPENSIVE: RouteConstraints(ModelLabel.REASONING, Prefer.QUALITY, True),
}


@dataclass(frozen=True)
class CloudBudgetPolicy:
    monthly_budget_usd: Decimal = Decimal("20")
    warning_threshold_usd: Decimal = Decimal("15")
    hard_stop_usd: Decimal = Decimal("19")
    emergency_reserve_usd: Decimal = Decimal("1")
    max_parallel_cloud_agents: int = 1
    max_retries: int = 2
    max_tool_iterations: int = 20
    expensive_model_requires_approval: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key, value in tuple(data.items()):
            if isinstance(value, Decimal):
                data[key] = str(value)
        return data

    def authorize(
        self,
        *,
        cumulative_monthly_cost: Decimal | str,
        estimated_mission_cost: Decimal | str,
        expensive: bool = False,
        approved: bool = False,
    ) -> tuple[bool, str]:
        try:
            spent = Decimal(str(cumulative_monthly_cost))
            estimate = Decimal(str(estimated_mission_cost))
        except (InvalidOperation, ValueError):
            return False, "invalid_cost"
        if spent < 0 or estimate < 0:
            return False, "negative_cost"
        if expensive and self.expensive_model_requires_approval and not approved:
            return False, "approval_required"
        projected = spent + estimate
        if projected > self.hard_stop_usd:
            return False, "monthly_hard_stop"
        if projected > self.monthly_budget_usd - self.emergency_reserve_usd:
            return False, "emergency_reserve_protected"
        return True, "warning_threshold" if projected >= self.warning_threshold_usd else "ok"


DEFAULT_CLOUD_BUDGET = CloudBudgetPolicy()


def constraints_for(model_class: MissionModelClass | str) -> RouteConstraints:
    return ROUTE_CONSTRAINTS[MissionModelClass(model_class)]
