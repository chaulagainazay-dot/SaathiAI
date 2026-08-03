"""M344–M351 — SaathiOS multi-agent development environment.

Development agents deliberate over a *development mission*: they research,
propose, challenge, meet, review and decide. They are not runtime product
agents (``saathi.agent_registry``) and they are not coding-agent sessions
(``saathi.engineering``).

This package sits strictly **above** ``saathi.engineering`` with a one-way
dependency and reuses, rather than re-implements:

* ``saathi.safety.SafetyLevel`` / ``Approval`` — the only authority vocabulary;
* ``saathi.engineering.approval`` — the bound-approval shape;
* ``saathi.engineering.session_ledger`` — hash-chained audit;
* ``saathi.engineering.store`` — durable-write primitives;
* ``saathi.engineering.settings`` — disabled-by-default authority flags.

Nothing here is reachable from the product surface. Every authority flag is
false by default and the destructive ones cannot be enabled by environment.

See ``docs/ai-development/`` and ADR-012.
"""
from __future__ import annotations

from saathi.agentdev.roles import (
    RoleContract,
    RoleValidationError,
    list_roles,
    get_role,
    load_registry,
)
from saathi.agentdev.settings import AgentDevSettings, load_settings

__all__ = [
    "AgentDevSettings",
    "RoleContract",
    "RoleValidationError",
    "get_role",
    "list_roles",
    "load_registry",
    "load_settings",
]
