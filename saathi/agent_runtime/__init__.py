"""M10 Multi-Agent Runtime — bounded, observable, memory-aware, gateway-only.

Orchestrator plans a task DAG, runs memory-scoped agent turns through the
ExecutionGateway, gates high-risk actions behind explicit approval (agents
cannot self-approve), delegates with narrowing-only permissions, verifies with
evidence, reviews independently, retries transient failures within budget, and
checkpoints for resume.
"""
from saathi.agent_runtime.models import (
    AgentDefinition, RunState, RiskClass, Task, MessageType,
    validate_transition, can_transition, is_terminal, validate_output,
    IllegalTransition,
)
from saathi.agent_runtime import registry
from saathi.agent_runtime.graph import TaskGraph, CycleError
from saathi.agent_runtime import policy
from saathi.agent_runtime.store import RunStore
from saathi.agent_runtime.gateway_exec import AgentExecutor
from saathi.agent_runtime.orchestrator import Orchestrator, default_orchestrator
from saathi.agent_runtime.strategies import STRATEGIES, choose_strategy
from saathi.agent_runtime import contracts as contracts  # M48.1 fail-closed layer

__all__ = [
    "AgentDefinition", "RunState", "RiskClass", "Task", "MessageType",
    "validate_transition", "can_transition", "is_terminal", "validate_output",
    "IllegalTransition", "registry", "TaskGraph", "CycleError", "policy",
    "RunStore", "AgentExecutor", "Orchestrator", "default_orchestrator",
    "STRATEGIES", "choose_strategy", "contracts",
]
