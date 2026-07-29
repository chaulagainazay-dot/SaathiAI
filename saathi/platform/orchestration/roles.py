"""Policy-bound agent roles — not free-form personas."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from saathi.platform.mission_runtime.models import AgentType

from .models import ApprovalRequirement, MAX_RETRIES_DEFAULT


# Capabilities are declarative labels only; they never grant tool authority.
CAP_PLAN = "plan"
CAP_RESEARCH = "research"
CAP_ARCHITECTURE = "architecture"
CAP_IMPLEMENT = "implement"
CAP_REVIEW = "review"
CAP_TEST = "test"
CAP_BROWSER = "browser"
CAP_SECURITY_REVIEW = "security_review"
CAP_DOCUMENT = "document"
CAP_CERTIFY = "certify"
CAP_OPERATE = "operate"
CAP_DOMAIN = "domain_analysis"

# Never granted by model request alone
FORBIDDEN_ALL = frozenset(
    {
        "direct_tool_execution",
        "forge_approval",
        "bypass_rbac",
        "access_credentials",
        "mutate_production",
        "self_grant_permission",
        "disable_audit",
        "suppress_evidence",
        "trading_execution",
        "public_exposure",
    }
)


@dataclass(frozen=True)
class AgentRolePolicy:
    role_id: str
    agent_type: str  # Mission AgentType value
    purpose: str
    allowed_capabilities: tuple[str, ...]
    forbidden_capabilities: tuple[str, ...]
    required_context: tuple[str, ...]
    output_contract: str
    approval_requirement: str
    concurrency_limit: int
    max_retries: int
    timeout_sec: float
    evidence_requirements: tuple[str, ...]
    certification_expectations: str
    can_self_certify: bool = False
    can_final_review: bool = False

    def to_public(self) -> dict[str, Any]:
        d = asdict(self)
        d["execution_authority"] = "PlatformAgentRuntime"
        d["model_cannot_elevate"] = True
        return d


def _policy(
    role_id: str,
    agent_type: AgentType,
    purpose: str,
    allowed: list[str],
    *,
    approval: str = ApprovalRequirement.NO_APPROVAL_REQUIRED.value,
    concurrency: int = 2,
    retries: int = MAX_RETRIES_DEFAULT,
    timeout: float = 120.0,
    evidence: list[str] | None = None,
    cert: str = "evidence_linked",
    final_review: bool = False,
    self_cert: bool = False,
    context: list[str] | None = None,
    output: str = "structured_task_result",
) -> AgentRolePolicy:
    return AgentRolePolicy(
        role_id=role_id,
        agent_type=agent_type.value,
        purpose=purpose,
        allowed_capabilities=tuple(allowed),
        forbidden_capabilities=tuple(sorted(FORBIDDEN_ALL)),
        required_context=tuple(context or ("mission", "workspace")),
        output_contract=output,
        approval_requirement=approval,
        concurrency_limit=max(1, min(concurrency, 4)),
        max_retries=max(0, min(retries, 5)),
        timeout_sec=max(5.0, min(timeout, 600.0)),
        evidence_requirements=tuple(evidence or ("task_result",)),
        certification_expectations=cert,
        can_self_certify=self_cert,
        can_final_review=final_review,
    )


class AgentRoleRegistry:
    """Fixed role directory; registration confers no tool permission."""

    def __init__(self) -> None:
        roles = [
            _policy(
                "planner",
                AgentType.PLANNER,
                "Decompose objectives into a bounded work graph",
                [CAP_PLAN],
                evidence=["plan_definition", "validation_report"],
                output="mission_plan_definition",
            ),
            _policy(
                "architect",
                AgentType.ARCHITECT,
                "Review architecture and platform reuse",
                [CAP_ARCHITECTURE, CAP_REVIEW],
                evidence=["architecture_notes"],
                final_review=True,
            ),
            _policy(
                "researcher",
                AgentType.RESEARCHER,
                "Retrieve and summarize authorized context",
                [CAP_RESEARCH],
                evidence=["research_summary", "source_refs"],
            ),
            _policy(
                "implementer",
                AgentType.IMPLEMENTER,
                "Propose the smallest complete implementation change",
                [CAP_IMPLEMENT],
                approval=ApprovalRequirement.APPROVAL_REQUIRED_BEFORE_MUTATION.value,
                evidence=["change_summary"],
                self_cert=False,
                final_review=False,
            ),
            _policy(
                "reviewer",
                AgentType.REVIEWER,
                "Independent evidence-backed review",
                [CAP_REVIEW],
                evidence=["review_verdict"],
                final_review=True,
            ),
            _policy(
                "test",
                AgentType.TEST,
                "Run deterministic verification via registered tools",
                [CAP_TEST],
                evidence=["test_report"],
            ),
            _policy(
                "browser",
                AgentType.BROWSER,
                "Browser certification via governed browser tools",
                [CAP_BROWSER],
                approval=ApprovalRequirement.APPROVAL_REQUIRED_BEFORE_EXTERNAL_CALL.value,
                evidence=["browser_cert"],
                concurrency=1,
            ),
            _policy(
                "security",
                AgentType.SECURITY,
                "Security, isolation, and policy boundary review",
                [CAP_SECURITY_REVIEW, CAP_REVIEW],
                evidence=["security_findings"],
                final_review=True,
                approval=ApprovalRequirement.APPROVAL_REQUIRED_BEFORE_EXECUTION.value,
            ),
            _policy(
                "documentation",
                AgentType.DOCUMENTATION,
                "Update authoritative project documentation",
                [CAP_DOCUMENT],
                evidence=["doc_update_ref"],
            ),
            _policy(
                "certification",
                AgentType.CERTIFICATION,
                "Issue final verdict only from recorded evidence",
                [CAP_CERTIFY],
                evidence=["certification_record"],
                final_review=True,
                self_cert=False,
                cert="independent_evidence_only",
            ),
            _policy(
                "operator",
                AgentType.OPERATOR,
                "Operate mission controls under human authority",
                [CAP_OPERATE],
                evidence=["operator_action"],
                concurrency=1,
            ),
            _policy(
                "domain_specialist",
                AgentType.DOMAIN,
                "Apply domain templates within existing authorities",
                [CAP_DOMAIN, CAP_RESEARCH],
                evidence=["domain_analysis"],
                context=["mission", "workspace", "domain"],
            ),
        ]
        self._by_id = {r.role_id: r for r in roles}
        self._by_agent = {r.agent_type: r for r in roles}

    def get(self, role_id: str) -> AgentRolePolicy:
        if role_id in self._by_id:
            return self._by_id[role_id]
        if role_id in self._by_agent:
            return self._by_agent[role_id]
        raise ValueError(f"unknown agent role {role_id!r}")

    def get_by_agent_type(self, agent_type: str) -> AgentRolePolicy:
        if agent_type not in self._by_agent:
            raise ValueError(f"unknown agent type {agent_type!r}")
        return self._by_agent[agent_type]

    def list_roles(self) -> list[dict[str, Any]]:
        return [r.to_public() for r in self._by_id.values()]

    def known_agent_types(self) -> set[str]:
        return set(self._by_agent.keys())


# Keywords → preferred role for deterministic assignment
TASK_ROLE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("security", "rbac", "isolation", "threat", "secret"), "security"),
    (("test", "pytest", "verify", "regression"), "test"),
    (("browser", "playwright", "ui cert"), "browser"),
    (("document", "docs", "readme", "write-up"), "documentation"),
    (("certif", "verdict", "sign-off"), "certification"),
    (("research", "audit", "investigate", "analyze context"), "researcher"),
    (("architect", "design", "structure"), "architect"),
    (("implement", "code", "build", "patch", "fix"), "implementer"),
    (("plan", "decompose", "milestone"), "planner"),
    (("operate", "pause", "resume", "cancel"), "operator"),
    (("ielts", "hcg", "domain", "crm", "erp"), "domain_specialist"),
    (("review", "inspect"), "reviewer"),
]
