"""M14 canonical project-health calculation — evidence-backed, not free-text.

Health is derived from real signals (open risks, blockers, budget variance,
stale activity, unresolved approvals) and always returns the evidence behind
the verdict.
"""
from __future__ import annotations

import time

from saathi.ceo.models import ProjectHealth


def project_health(store, owner: str, *, business_id: str = "",
                   open_blockers: int = 0, budget_id: str | None = None,
                   last_activity_ts: float | None = None,
                   unresolved_approvals: int = 0) -> dict:
    """Compute health from real signals. Every input becomes visible evidence."""
    evidence = []
    penalties = 0

    risks = [r for r in store.list_risks(owner, status="open")
             if not business_id or r["business_id"] == business_id]
    high_risks = [r for r in risks if r["score"] >= 40]
    if high_risks:
        penalties += len(high_risks) * 2
        evidence.append(f"{len(high_risks)} high-severity open risk(s)")

    if open_blockers:
        penalties += open_blockers * 3
        evidence.append(f"{open_blockers} open blocker(s)")

    if unresolved_approvals:
        penalties += unresolved_approvals
        evidence.append(f"{unresolved_approvals} unresolved approval(s)")

    if budget_id:
        from saathi.ceo.finance import budget_variance
        try:
            bv = budget_variance(store, budget_id)
            if bv["over_budget"]:
                penalties += 3
                evidence.append("over budget")
            elif bv["warning"]:
                penalties += 1
                evidence.append("approaching budget limit")
        except KeyError:
            pass

    stale = False
    if last_activity_ts is not None:
        age_days = (time.time() - last_activity_ts) / 86400
        if age_days > 14:
            stale = True
            penalties += 2
            evidence.append(f"no activity for {age_days:.0f} days")

    if open_blockers > 0:
        health = ProjectHealth.BLOCKED
    elif penalties >= 6:
        health = ProjectHealth.AT_RISK
    elif penalties >= 2:
        health = ProjectHealth.ATTENTION
    elif not evidence and last_activity_ts is None:
        health = ProjectHealth.UNKNOWN
        evidence.append("no signals available")
    else:
        health = ProjectHealth.ON_TRACK
        if not evidence:
            evidence.append("no risks, blockers, or budget issues")

    return {"health": health.value, "penalty_points": penalties,
            "evidence": evidence, "stale": stale}
