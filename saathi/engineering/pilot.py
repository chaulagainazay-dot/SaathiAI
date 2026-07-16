"""M20.0 — Harmless first pilot: documentation-consistency supervision.

Does not require a real write-enabled coding agent when using mock adapter.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.engineering.models import (
    EngineeringBacklogItem,
    ItemStatus,
    Priority,
    RiskLevel,
    new_id,
)
from saathi.engineering.orchestrator import EngineeringOrchestrator, OrchestratorResult
from saathi.engineering.settings import EngineeringSettings, load_settings
from saathi.engineering.store import EngineeringStore


PILOT_ITEM_ID = "eng_m20_0_pilot_docs"


def pilot_backlog_item() -> EngineeringBacklogItem:
    return EngineeringBacklogItem(
        item_id=PILOT_ITEM_ID,
        milestone_id="M20.0",
        title="Documentation consistency pilot (harmless)",
        description=(
            "Supervise a low-risk documentation consistency check for the "
            "Engineering Orchestrator pilot. No production changes, no trading, "
            "no deploy, no merge."
        ),
        repository_id="saathiai",
        branch_policy="milestone/*",
        priority=Priority.P3.value,
        status=ItemStatus.READY.value,
        risk_level=RiskLevel.LOW.value,
        source_of_authority="M20.0 milestone brief",
        acceptance_criteria=[
            "Orchestrator selects this pilot item deterministically when alone",
            "Repository readiness is evaluated",
            "Bounded prompt is generated with TG isolation rules",
            "Mock agent session completes under supervision",
            "Validation plan records pass/fail honestly",
            "Durable handoff is written",
        ],
        required_validations=[
            "secret_scan",
            "trading_guardian_isolation",
            "permission_tests",
        ],
        out_of_scope=[
            "merge to main",
            "deployment",
            "live trading",
            "production credentials",
            "unrestricted shell",
            "multi-repo parallel writes",
        ],
        approval_requirement=False,
        retry_limit=3,
        estimated_complexity="small",
        capability_requirements=["inspect_engineering_backlog", "launch_readonly_agent"],
        environment_requirements=["local_git"],
        rollback_requirement="No code mutation in mock pilot; discard session state under data/engineering/",
        stop_conditions=[
            "policy violation",
            "secret detected",
            "stall",
            "trading attempt",
        ],
        evidence_references=[
            "docs/M20_0_ENGINEERING_ORCHESTRATOR_AUDIT.md",
            "docs/AUTONOMOUS_ROADMAP.md",
        ],
        is_security_issue=False,
        is_ci_regression=False,
        user_value=6,
        revenue_impact=0,
        architecture_reuse=9,
        unresolved_blockers=[],
    )


def seed_pilot(store: EngineeringStore) -> EngineeringBacklogItem:
    existing = store.get_item(PILOT_ITEM_ID)
    if existing:
        return existing
    item = pilot_backlog_item()
    return store.add_item(item)


def run_first_pilot(
    *,
    store_dir: str | Path | None = None,
    repository_root: str | Path | None = None,
    enable_orchestrator: bool = True,
    enable_launch: bool = True,
    write_enabled: bool = False,
    adapter_name: str = "mock",
) -> dict[str, Any]:
    """Run the harmless end-to-end pilot with mock adapter by default."""
    settings = load_settings(
        orchestrator_enabled=enable_orchestrator,
        agent_launching_enabled=enable_launch,
        repository_writes_enabled=write_enabled,
        commits_enabled=False,
        pushes_enabled=False,
        store_dir=str(store_dir) if store_dir else "",
        allowed_agent_adapters=["mock", "claude_code"],
    )
    # Explicit overrides (load_settings uses env; kwargs applied)
    settings.orchestrator_enabled = enable_orchestrator
    settings.agent_launching_enabled = enable_launch
    settings.repository_writes_enabled = write_enabled
    settings.commits_enabled = False
    settings.pushes_enabled = False
    if store_dir:
        settings.store_dir = str(store_dir)

    orch = EngineeringOrchestrator(
        settings=settings,
        store=EngineeringStore(settings.store_path()),
        repository_root=repository_root,
    )
    item = seed_pilot(orch.store)
    # ensure ready
    if item.status != ItemStatus.READY.value:
        item.status = ItemStatus.READY.value
        orch.store.upsert_item(item)

    selection = orch.select()
    plan = orch.plan(item.item_id, knowledge_context="M20.0 pilot — docs consistency only.")
    result: OrchestratorResult = orch.launch(
        item.item_id,
        adapter_name=adapter_name,
        knowledge_context="M20.0 pilot — docs consistency only.",
        write_enabled=write_enabled,
        poll_until_done=True,
        max_polls=4,
    )
    return {
        "pilot_item_id": item.item_id,
        "selection": selection,
        "plan_prompt_version": (plan.get("prompt") or {}).get("prompt_version"),
        "result": result.to_dict(),
        "status": orch.status(),
    }
