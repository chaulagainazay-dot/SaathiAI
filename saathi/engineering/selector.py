"""M20.0 — Deterministic candidate selection (no LLM-only decisions)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from saathi.engineering.models import (
    EngineeringBacklogItem,
    ItemStatus,
    Priority,
    RiskLevel,
)
from saathi.engineering.store import EngineeringStore

# Explicit factor weights — deterministic policy, not model judgment
WEIGHTS = {
    "security_critical": 1000,
    "security_high": 500,
    "ci_regression": 400,
    "priority_p0": 300,
    "priority_p1": 200,
    "priority_p2": 100,
    "priority_p3": 50,
    "priority_p4": 20,
    "user_value": 5,  # * user_value 0-10
    "revenue_impact": 4,  # * revenue 0-10
    "architecture_reuse": 3,  # * reuse 0-10
    "validation_feasibility": 40,
    "rollback_quality": 30,
    "dependency_ready": 50,
    "clean_repo_bonus": 20,
    "approval_penalty": -25,  # still selectable but lower if approval needed
    "blocker_penalty": -200,  # per unresolved blocker type count
}


@dataclass
class SelectionResult:
    selected: EngineeringBacklogItem | None
    rejected: list[dict[str, Any]] = field(default_factory=list)
    score_explanation: dict[str, Any] = field(default_factory=dict)
    required_approvals: list[str] = field(default_factory=list)
    expected_validation_plan: list[str] = field(default_factory=list)
    ranking: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected.to_dict() if self.selected else None,
            "rejected": self.rejected,
            "score_explanation": self.score_explanation,
            "required_approvals": self.required_approvals,
            "expected_validation_plan": self.expected_validation_plan,
            "ranking": self.ranking,
        }


def _priority_score(p: str) -> int:
    return {
        Priority.P0.value: WEIGHTS["priority_p0"],
        Priority.P1.value: WEIGHTS["priority_p1"],
        Priority.P2.value: WEIGHTS["priority_p2"],
        Priority.P3.value: WEIGHTS["priority_p3"],
        Priority.P4.value: WEIGHTS["priority_p4"],
    }.get(p, WEIGHTS["priority_p3"])


def score_item(
    item: EngineeringBacklogItem,
    *,
    deps_ok: bool,
    repo_clean: bool = True,
    tools_available: bool = True,
    environment_ready: bool = True,
) -> tuple[int, dict[str, Any]]:
    """Return (score, explanation). Higher is better."""
    parts: dict[str, Any] = {}
    total = 0

    if item.is_security_issue:
        if item.risk_level == RiskLevel.CRITICAL.value:
            total += WEIGHTS["security_critical"]
            parts["security"] = WEIGHTS["security_critical"]
        elif item.risk_level == RiskLevel.HIGH.value:
            total += WEIGHTS["security_high"]
            parts["security"] = WEIGHTS["security_high"]
        else:
            total += 100
            parts["security"] = 100

    if item.is_ci_regression:
        total += WEIGHTS["ci_regression"]
        parts["ci_regression"] = WEIGHTS["ci_regression"]

    ps = _priority_score(item.priority)
    total += ps
    parts["priority"] = ps

    uv = WEIGHTS["user_value"] * max(0, min(10, int(item.user_value)))
    total += uv
    parts["user_value"] = uv

    ri = WEIGHTS["revenue_impact"] * max(0, min(10, int(item.revenue_impact)))
    total += ri
    parts["revenue_impact"] = ri

    ar = WEIGHTS["architecture_reuse"] * max(0, min(10, int(item.architecture_reuse)))
    total += ar
    parts["architecture_reuse"] = ar

    if item.required_validations:
        total += WEIGHTS["validation_feasibility"]
        parts["validation_feasibility"] = WEIGHTS["validation_feasibility"]

    if item.rollback_requirement:
        total += WEIGHTS["rollback_quality"]
        parts["rollback_quality"] = WEIGHTS["rollback_quality"]

    if deps_ok:
        total += WEIGHTS["dependency_ready"]
        parts["dependency_ready"] = WEIGHTS["dependency_ready"]

    if repo_clean:
        total += WEIGHTS["clean_repo_bonus"]
        parts["clean_repo"] = WEIGHTS["clean_repo_bonus"]

    if not tools_available:
        total -= 100
        parts["tools_missing"] = -100

    if not environment_ready:
        total -= 150
        parts["environment_not_ready"] = -150

    if item.approval_requirement:
        total += WEIGHTS["approval_penalty"]
        parts["approval_penalty"] = WEIGHTS["approval_penalty"]

    if item.unresolved_blockers:
        pen = WEIGHTS["blocker_penalty"] * len(item.unresolved_blockers)
        total += pen
        parts["blockers"] = pen

    parts["total"] = total
    return total, parts


def select_candidate(
    store: EngineeringStore,
    *,
    repo_clean: bool = True,
    tools_available: bool = True,
    environment_ready: bool = True,
    readiness_state: str = "ready",
) -> SelectionResult:
    """Deterministic selection across backlog."""
    rejected: list[dict[str, Any]] = []
    ranked: list[tuple[int, EngineeringBacklogItem, dict]] = []

    if readiness_state in ("unsafe", "blocked"):
        for item in store.list_items():
            rejected.append({
                "item_id": item.item_id,
                "reason": f"repository_{readiness_state}",
            })
        return SelectionResult(
            selected=None,
            rejected=rejected,
            score_explanation={"policy": f"reject_all_repo_{readiness_state}"},
        )

    for item in store.list_items():
        if item.status not in (ItemStatus.READY.value, ItemStatus.PROPOSED.value):
            rejected.append({
                "item_id": item.item_id,
                "reason": f"status_not_selectable:{item.status}",
            })
            continue
        if item.unresolved_blockers and item.status == ItemStatus.BLOCKED.value:
            rejected.append({
                "item_id": item.item_id,
                "reason": "blocked_with_unresolved",
                "blockers": list(item.unresolved_blockers),
            })
            continue
        if item.status == ItemStatus.BLOCKED.value:
            rejected.append({
                "item_id": item.item_id,
                "reason": "status_blocked",
            })
            continue

        deps_ok, dep_issues = store.dependency_ready(item)
        if not deps_ok:
            rejected.append({
                "item_id": item.item_id,
                "reason": "dependencies_not_ready",
                "details": dep_issues,
            })
            continue

        if item.unresolved_blockers:
            rejected.append({
                "item_id": item.item_id,
                "reason": "unresolved_blockers",
                "blockers": list(item.unresolved_blockers),
            })
            continue

        sc, expl = score_item(
            item,
            deps_ok=deps_ok,
            repo_clean=repo_clean,
            tools_available=tools_available,
            environment_ready=environment_ready,
        )
        ranked.append((sc, item, expl))

    # Stable sort: score desc, then item_id asc
    ranked.sort(key=lambda t: (-t[0], t[1].item_id))
    ranking = [
        {"item_id": it.item_id, "score": sc, "explanation": ex}
        for sc, it, ex in ranked
    ]

    if not ranked:
        return SelectionResult(
            selected=None,
            rejected=rejected,
            score_explanation={"policy": "no_eligible_candidates"},
            ranking=ranking,
        )

    best_score, best, best_expl = ranked[0]
    approvals = []
    if best.approval_requirement:
        approvals.append("human_approval_required")
    if readiness_state == "requires_approval":
        approvals.append("repository_readiness_approval")

    plan = list(best.required_validations) or [
        "focused_unit_tests",
        "secret_scan",
        "git_diff_check",
    ]

    return SelectionResult(
        selected=best,
        rejected=rejected,
        score_explanation={
            "selected_id": best.item_id,
            "score": best_score,
            "factors": best_expl,
            "policy": "deterministic_weighted_v1",
            "llm_override": False,
        },
        required_approvals=approvals,
        expected_validation_plan=plan,
        ranking=ranking,
    )
