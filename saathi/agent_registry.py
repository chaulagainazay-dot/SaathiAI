"""Agent Registry — every agent declares a contract (SES-002 Part 4).

The audit gap this closes: sub-agents were hardcoded in `agents/master.py` with
no declared contracts. SES-002 is explicit — "an agent without a written
contract is not a finished agent." This is the central registry where agents
register their contract, and it ties an agent to the platform's other
capability layers: a Model Router label, a max Safety level, and an approval
requirement (Runtime Governance Engine).

Deliberately captures the contract fields that are *used* today, not all 13
SES-002 fields speculatively (Development Rule #1). Fields grow as the agent
system needs them.

Testable in isolation (AP-12): construct, register, query — no runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from saathi.model_router import ModelLabel
from saathi.safety import SafetyLevel, Approval


@dataclass
class AgentContract:
    agent_id: str
    department: str
    purpose: str
    model_label: ModelLabel                 # which Model Router capability it needs
    max_safety: SafetyLevel                 # highest action level it may request
    memory_access: str                      # e.g. "read-all/write-self"
    allowed_tools: frozenset[str] = field(default_factory=frozenset)  # empty = none/declared elsewhere
    approval: Approval = Approval.AUTOMATIC  # default approval for its actions

    def summary(self) -> dict:
        d = asdict(self)
        d["model_label"] = self.model_label.value
        d["max_safety"] = self.max_safety.name
        d["approval"] = self.approval.value
        d["allowed_tools"] = sorted(self.allowed_tools)
        return d


class AgentRegistry:
    def __init__(self) -> None:
        self._contracts: dict[str, AgentContract] = {}
        self._instances: dict[str, object] = {}

    def register(self, contract: AgentContract, instance: object | None = None) -> None:
        self._contracts[contract.agent_id] = contract
        if instance is not None:
            self._instances[contract.agent_id] = instance

    def get(self, agent_id: str) -> AgentContract | None:
        return self._contracts.get(agent_id)

    def instance(self, agent_id: str) -> object | None:
        return self._instances.get(agent_id)

    def by_department(self, department: str) -> list[AgentContract]:
        return [c for c in self._contracts.values() if c.department == department]

    def all(self) -> list[AgentContract]:
        return list(self._contracts.values())

    def snapshot(self) -> list[dict]:
        return [c.summary() for c in self._contracts.values()]

    def uncontracted(self, agent_ids: list[str]) -> list[str]:
        """Given the agent ids actually wired into the runtime, which have no
        contract? (The SES-002 compliance check.)"""
        return [a for a in agent_ids if a not in self._contracts]


def default_registry() -> AgentRegistry:
    """Contracts for the agents that exist today — the IELTS tutoring sub-agents
    (BMA sub_agents in agents/master.py). Reconciles code to SES-002."""
    r = AgentRegistry()
    tutor = "IELTS Tutor"
    for skill in ("writing", "speaking", "reading", "listening",
                  "grammar", "vocabulary", "pronunciation"):
        r.register(AgentContract(
            agent_id=f"{skill}_subagent",
            department=tutor,
            purpose=f"Evaluate and coach IELTS {skill}",
            model_label=ModelLabel.STANDARD,
            max_safety=SafetyLevel.L1,       # produces feedback; no external side effects
            memory_access="read-all/write-self",
            approval=Approval.AUTOMATIC,
        ))
    return r


# Process-wide registry.
registry = default_registry()
