"""Bounded, versioned plan templates — never grant permissions silently."""
from __future__ import annotations

from typing import Any

from .models import READONLY_ANALYSIS_TOOL, RiskLevel

TEMPLATE_VERSION = "m95.templates.v1"


def _task(
    tid: str,
    title: str,
    agent: str,
    *,
    depends_on: list[str] | None = None,
    requires_review: bool = False,
    verification: list[str] | None = None,
    max_retries: int = 1,
    priority: int = 50,
    tool_id: str = READONLY_ANALYSIS_TOOL,
) -> dict[str, Any]:
    return {
        "id": tid,
        "title": title,
        "agent_type": agent,
        "tool_id": tool_id,
        "arguments": {"text": title, "task_id": tid},
        "depends_on": depends_on or [],
        "priority": priority,
        "estimated_effort": 1,
        "token_estimate": 200,
        "max_retries": max_retries,
        "requires_review": requires_review,
        "verification": verification or [],
        "concurrency_safe": True,
    }


def _goal_phase_milestone(tasks: list[dict[str, Any]], *, goal: str, phase: str, milestone: str) -> list[dict]:
    return [
        {
            "id": "goal-main",
            "title": goal,
            "phases": [
                {
                    "id": "phase-main",
                    "title": phase,
                    "milestones": [
                        {
                            "id": "ms-main",
                            "title": milestone,
                            "tasks": tasks,
                        }
                    ],
                }
            ],
        }
    ]


TEMPLATES: dict[str, dict[str, Any]] = {
    "repository_audit": {
        "template_id": "repository_audit",
        "version": TEMPLATE_VERSION,
        "title": "Repository audit",
        "domain": "engineering",
        "risk_level": RiskLevel.MEDIUM.value,
        "description": "Audit project state, identify risks, produce implementation plan.",
        "builder": "repository_audit",
    },
    "production_readiness": {
        "template_id": "production_readiness",
        "version": TEMPLATE_VERSION,
        "title": "Production readiness review",
        "domain": "engineering",
        "risk_level": RiskLevel.HIGH.value,
        "description": "Review production readiness and blockers without authorizing production.",
        "builder": "production_readiness",
    },
    "ui_redesign": {
        "template_id": "ui_redesign",
        "version": TEMPLATE_VERSION,
        "title": "Bounded UI redesign mission",
        "domain": "engineering",
        "risk_level": RiskLevel.MEDIUM.value,
        "description": "Plan a bounded UI redesign with review and test gates.",
        "builder": "ui_redesign",
    },
    "security_review": {
        "template_id": "security_review",
        "version": TEMPLATE_VERSION,
        "title": "Security review",
        "domain": "security",
        "risk_level": RiskLevel.HIGH.value,
        "description": "Security-focused review with independent certification.",
        "builder": "security_review",
    },
    "code_implementation": {
        "template_id": "code_implementation",
        "version": TEMPLATE_VERSION,
        "title": "Code implementation mission",
        "domain": "engineering",
        "risk_level": RiskLevel.MEDIUM.value,
        "description": "Plan → implement → test → review → document.",
        "builder": "code_implementation",
    },
    "test_certification": {
        "template_id": "test_certification",
        "version": TEMPLATE_VERSION,
        "title": "Test and certification mission",
        "domain": "engineering",
        "risk_level": RiskLevel.MEDIUM.value,
        "description": "Verification and certification with independent reviewer.",
        "builder": "test_certification",
    },
    "documentation_mission": {
        "template_id": "documentation_mission",
        "version": TEMPLATE_VERSION,
        "title": "Documentation mission",
        "domain": "engineering",
        "risk_level": RiskLevel.LOW.value,
        "description": "Research and documentation update plan.",
        "builder": "documentation_mission",
    },
    "ielts_content": {
        "template_id": "ielts_content",
        "version": TEMPLATE_VERSION,
        "title": "IELTS content-production mission",
        "domain": "ielts",
        "risk_level": RiskLevel.LOW.value,
        "description": "Bounded IELTS content planning within platform module authority.",
        "builder": "ielts_content",
    },
    "hcg_ops": {
        "template_id": "hcg_ops",
        "version": TEMPLATE_VERSION,
        "title": "HCG operations improvement",
        "domain": "hcg",
        "risk_level": RiskLevel.MEDIUM.value,
        "description": "HCG operations analysis and improvement plan (no finance mutation).",
        "builder": "hcg_ops",
    },
    "incident_investigation": {
        "template_id": "incident_investigation",
        "version": TEMPLATE_VERSION,
        "title": "Incident investigation",
        "domain": "ops",
        "risk_level": RiskLevel.HIGH.value,
        "description": "Investigate incident with security and documentation gates.",
        "builder": "incident_investigation",
    },
}


def list_templates() -> list[dict[str, Any]]:
    return [
        {
            "template_id": t["template_id"],
            "version": t["version"],
            "title": t["title"],
            "domain": t["domain"],
            "risk_level": t["risk_level"],
            "description": t["description"],
            "grants_permissions": False,
            "skips_validation": False,
        }
        for t in TEMPLATES.values()
    ]


def build_template_plan(
    template_id: str,
    *,
    objective: str,
    domain: str = "",
) -> dict[str, Any]:
    meta = TEMPLATES.get(template_id)
    if not meta:
        raise ValueError(f"unknown template {template_id!r}")
    builder = meta["builder"]
    fn = _BUILDERS[builder]
    goals = fn(objective=objective, domain=domain or meta["domain"])
    return {
        "objective": objective[:4000],
        "max_parallel_tasks": 2,
        "budget": {
            "estimated_effort": 20,
            "max_elapsed_seconds": 7200,
            "max_token_estimate": 12000,
            "max_commits": 4,
            "max_tests": 10,
            "max_browser_runs": 2,
            "max_cycles": 30,
            "max_no_progress_cycles": 3,
        },
        "template_id": template_id,
        "template_version": TEMPLATE_VERSION,
        "domain": domain or meta["domain"],
        "risk_level": meta["risk_level"],
        "goals": goals,
    }


def _repository_audit(*, objective: str, domain: str) -> list[dict]:
    tasks = [
        _task("research-context", "Research authorized project context", "ResearcherAgent", priority=90),
        _task(
            "architecture-scan",
            "Architecture and reuse review",
            "ArchitectAgent",
            depends_on=["research-context"],
            priority=80,
            requires_review=True,
        ),
        _task(
            "risk-analysis",
            "Identify risks and blockers",
            "SecurityAgent",
            depends_on=["research-context"],
            priority=75,
            requires_review=True,
        ),
        _task(
            "implementation-plan",
            "Produce implementation plan",
            "PlannerAgent",
            depends_on=["architecture-scan", "risk-analysis"],
            priority=70,
            verification=["plan-present"],
        ),
        _task(
            "independent-review",
            "Independent plan review",
            "ReviewerAgent",
            depends_on=["implementation-plan"],
            priority=60,
            requires_review=True,
            verification=["review-pass"],
        ),
        _task(
            "document-findings",
            "Document findings",
            "DocumentationAgent",
            depends_on=["independent-review"],
            priority=40,
        ),
    ]
    return _goal_phase_milestone(
        tasks,
        goal="Repository audit",
        phase="Audit",
        milestone="Findings and plan",
    )


def _production_readiness(*, objective: str, domain: str) -> list[dict]:
    tasks = [
        _task("research-readiness", "Gather readiness evidence", "ResearcherAgent", priority=90),
        _task(
            "security-gate",
            "Security and policy gate review",
            "SecurityAgent",
            depends_on=["research-readiness"],
            priority=85,
            requires_review=True,
        ),
        _task(
            "test-status",
            "Summarize test and cert status",
            "TestAgent",
            depends_on=["research-readiness"],
            priority=80,
            verification=["tests-summarized"],
        ),
        _task(
            "blocker-list",
            "Enumerate production blockers",
            "ArchitectAgent",
            depends_on=["security-gate", "test-status"],
            priority=70,
        ),
        _task(
            "readiness-review",
            "Independent readiness review",
            "ReviewerAgent",
            depends_on=["blocker-list"],
            priority=60,
            requires_review=True,
        ),
        _task(
            "certify-limitations",
            "Record certification with limitations",
            "CertificationAgent",
            depends_on=["readiness-review"],
            priority=50,
            verification=["limitations-recorded"],
        ),
    ]
    return _goal_phase_milestone(
        tasks,
        goal="Production readiness",
        phase="Review",
        milestone="Blockers and verdict",
    )


def _ui_redesign(*, objective: str, domain: str) -> list[dict]:
    tasks = [
        _task("research-ui", "Research current UI surfaces", "ResearcherAgent", priority=90),
        _task(
            "design-plan",
            "Bounded redesign plan",
            "ArchitectAgent",
            depends_on=["research-ui"],
            priority=80,
        ),
        _task(
            "implement-ui",
            "Propose UI implementation slice",
            "ImplementerAgent",
            depends_on=["design-plan"],
            priority=70,
        ),
        _task(
            "test-ui",
            "UI verification plan",
            "TestAgent",
            depends_on=["implement-ui"],
            priority=60,
            verification=["ui-tests"],
        ),
        _task(
            "review-ui",
            "Independent UI review",
            "ReviewerAgent",
            depends_on=["test-ui"],
            priority=50,
            requires_review=True,
        ),
    ]
    return _goal_phase_milestone(
        tasks, goal="UI redesign", phase="Design and verify", milestone="Slice"
    )


def _security_review(*, objective: str, domain: str) -> list[dict]:
    tasks = [
        _task("scope-security", "Scope security review", "PlannerAgent", priority=90),
        _task(
            "security-analysis",
            "Security analysis",
            "SecurityAgent",
            depends_on=["scope-security"],
            priority=85,
            requires_review=True,
        ),
        _task(
            "independent-sec-review",
            "Independent security review",
            "ReviewerAgent",
            depends_on=["security-analysis"],
            priority=70,
            requires_review=True,
        ),
        _task(
            "sec-docs",
            "Document security findings",
            "DocumentationAgent",
            depends_on=["independent-sec-review"],
            priority=50,
        ),
    ]
    return _goal_phase_milestone(
        tasks, goal="Security review", phase="Analysis", milestone="Findings"
    )


def _code_implementation(*, objective: str, domain: str) -> list[dict]:
    tasks = [
        _task("plan-impl", "Decompose implementation", "PlannerAgent", priority=90),
        _task(
            "architect-impl",
            "Architecture check",
            "ArchitectAgent",
            depends_on=["plan-impl"],
            priority=85,
        ),
        _task(
            "implement",
            "Implementation slice",
            "ImplementerAgent",
            depends_on=["architect-impl"],
            priority=80,
        ),
        _task(
            "test-impl",
            "Focused tests",
            "TestAgent",
            depends_on=["implement"],
            priority=70,
            verification=["focused-tests"],
        ),
        _task(
            "review-impl",
            "Independent review",
            "ReviewerAgent",
            depends_on=["test-impl"],
            priority=60,
            requires_review=True,
        ),
        _task(
            "docs-impl",
            "Update documentation",
            "DocumentationAgent",
            depends_on=["review-impl"],
            priority=40,
        ),
    ]
    return _goal_phase_milestone(
        tasks, goal="Implementation", phase="Build", milestone="Slice complete"
    )


def _test_certification(*, objective: str, domain: str) -> list[dict]:
    tasks = [
        _task("plan-tests", "Plan verification", "PlannerAgent", priority=90),
        _task(
            "run-tests",
            "Execute verification summary",
            "TestAgent",
            depends_on=["plan-tests"],
            priority=80,
            verification=["suite-summary"],
        ),
        _task(
            "browser-cert",
            "Browser certification summary",
            "BrowserAgent",
            depends_on=["plan-tests"],
            priority=75,
        ),
        _task(
            "review-cert",
            "Independent certification review",
            "ReviewerAgent",
            depends_on=["run-tests", "browser-cert"],
            priority=60,
            requires_review=True,
        ),
        _task(
            "issue-cert",
            "Issue evidence-backed verdict",
            "CertificationAgent",
            depends_on=["review-cert"],
            priority=50,
            verification=["cert-record"],
        ),
    ]
    return _goal_phase_milestone(
        tasks, goal="Certification", phase="Verify", milestone="Verdict"
    )


def _documentation_mission(*, objective: str, domain: str) -> list[dict]:
    tasks = [
        _task("research-docs", "Research current docs", "ResearcherAgent", priority=90),
        _task(
            "write-docs",
            "Documentation update plan",
            "DocumentationAgent",
            depends_on=["research-docs"],
            priority=70,
        ),
        _task(
            "review-docs",
            "Doc review",
            "ReviewerAgent",
            depends_on=["write-docs"],
            priority=50,
            requires_review=True,
        ),
    ]
    return _goal_phase_milestone(
        tasks, goal="Documentation", phase="Write", milestone="Docs"
    )


def _ielts_content(*, objective: str, domain: str) -> list[dict]:
    tasks = [
        _task("domain-ielts", "IELTS domain context", "DomainSpecialistAgent", priority=90),
        _task(
            "plan-content",
            "Content production plan",
            "PlannerAgent",
            depends_on=["domain-ielts"],
            priority=80,
        ),
        _task(
            "review-content-plan",
            "Review content plan",
            "ReviewerAgent",
            depends_on=["plan-content"],
            priority=60,
            requires_review=True,
        ),
    ]
    return _goal_phase_milestone(
        tasks, goal="IELTS content", phase="Plan", milestone="Content plan"
    )


def _hcg_ops(*, objective: str, domain: str) -> list[dict]:
    tasks = [
        _task("domain-hcg", "HCG domain context", "DomainSpecialistAgent", priority=90),
        _task(
            "ops-analysis",
            "Operations improvement analysis",
            "ArchitectAgent",
            depends_on=["domain-hcg"],
            priority=80,
        ),
        _task(
            "security-hcg",
            "Policy boundary check (no finance mutation)",
            "SecurityAgent",
            depends_on=["ops-analysis"],
            priority=70,
            requires_review=True,
        ),
        _task(
            "review-hcg",
            "Independent ops review",
            "ReviewerAgent",
            depends_on=["security-hcg"],
            priority=60,
            requires_review=True,
        ),
    ]
    return _goal_phase_milestone(
        tasks, goal="HCG ops", phase="Analyze", milestone="Recommendations"
    )


def _incident_investigation(*, objective: str, domain: str) -> list[dict]:
    tasks = [
        _task("triage", "Incident triage", "OperatorAgent", priority=95),
        _task(
            "investigate",
            "Investigate with authorized context",
            "ResearcherAgent",
            depends_on=["triage"],
            priority=85,
        ),
        _task(
            "security-incident",
            "Security impact review",
            "SecurityAgent",
            depends_on=["investigate"],
            priority=80,
            requires_review=True,
        ),
        _task(
            "document-incident",
            "Document incident findings",
            "DocumentationAgent",
            depends_on=["security-incident"],
            priority=50,
        ),
        _task(
            "review-incident",
            "Independent incident review",
            "ReviewerAgent",
            depends_on=["document-incident"],
            priority=40,
            requires_review=True,
        ),
    ]
    return _goal_phase_milestone(
        tasks, goal="Incident", phase="Investigate", milestone="Report"
    )


_BUILDERS = {
    "repository_audit": _repository_audit,
    "production_readiness": _production_readiness,
    "ui_redesign": _ui_redesign,
    "security_review": _security_review,
    "code_implementation": _code_implementation,
    "test_certification": _test_certification,
    "documentation_mission": _documentation_mission,
    "ielts_content": _ielts_content,
    "hcg_ops": _hcg_ops,
    "incident_investigation": _incident_investigation,
}


def infer_template(objective: str, domain: str = "") -> str:
    o = (objective or "").lower()
    d = (domain or "").lower()
    if "ielts" in o or d == "ielts":
        return "ielts_content"
    if "hcg" in o or d == "hcg":
        return "hcg_ops"
    if "security" in o or "threat" in o:
        return "security_review"
    if "production" in o or "readiness" in o:
        return "production_readiness"
    if "ui" in o or "redesign" in o or "ux" in o:
        return "ui_redesign"
    if "incident" in o or "outage" in o:
        return "incident_investigation"
    if "document" in o or "docs" in o:
        return "documentation_mission"
    if "test" in o and "cert" in o:
        return "test_certification"
    if "implement" in o or "code" in o or "build" in o:
        return "code_implementation"
    if "audit" in o or "review" in o or "plan" in o:
        return "repository_audit"
    return "repository_audit"
