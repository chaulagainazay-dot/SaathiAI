"""Agent session adapters for M20.0 Engineering Orchestrator."""
from __future__ import annotations

from saathi.engineering.adapters.base import AgentSessionAdapter, AdapterLaunchError
from saathi.engineering.adapters.claude_code import ClaudeCodeAdapter
from saathi.engineering.adapters.mock import MockAgentAdapter

ADAPTERS = {
    "mock": MockAgentAdapter,
    "claude_code": ClaudeCodeAdapter,
}


def get_adapter(name: str, **kwargs) -> AgentSessionAdapter:
    key = (name or "mock").strip().lower()
    if key not in ADAPTERS:
        raise AdapterLaunchError(f"unknown_adapter:{name}")
    return ADAPTERS[key](**kwargs)


__all__ = [
    "AgentSessionAdapter",
    "AdapterLaunchError",
    "ClaudeCodeAdapter",
    "MockAgentAdapter",
    "get_adapter",
    "ADAPTERS",
]
