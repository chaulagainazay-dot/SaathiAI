"""M344–M359 — SaathiOS multi-agent development environment.

Development agents deliberate over a *development mission*: they research,
propose, challenge, meet, review and decide. They are not runtime product
agents (``saathi.agent_registry``) and they are not coding-agent sessions
(``saathi.engineering``).

This package sits strictly **above** ``saathi.engineering`` with a one-way
dependency. Its only imports outside the standard library are:

* ``saathi.safety.SafetyLevel`` / ``Approval`` — the only authority vocabulary;
* ``saathi.config.ROOT`` — the repository root.

What it takes from ``saathi.engineering`` is *design contract*, not code: the
bound-approval field set, the append-only history shape, the atomic
``.tmp`` → ``os.replace`` write pattern, and the
denials-re-applied-after-override settings rule are each re-implemented for the
different nouns this layer handles.

Nothing here is reachable from the product surface. Every authority flag is
false by default and the destructive ones cannot be enabled by environment.

Terminology on this surface is pinned by
:mod:`saathi.agentdev.terminology` (M352). See ``docs/ai-development/``,
ADR-012 and ADR-013.
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
from saathi.agentdev.terminology import (
    Classification,
    PinnedTerm,
    audit_surface,
    classify,
    lexicon_report,
)

__all__ = [
    "AgentDevSettings",
    "Classification",
    "PinnedTerm",
    "RoleContract",
    "RoleValidationError",
    "audit_surface",
    "classify",
    "get_role",
    "lexicon_report",
    "list_roles",
    "load_registry",
    "load_settings",
]
