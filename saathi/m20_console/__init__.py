"""M20.7 — Shared console for Engineering Orchestrator + Governed Inference.

Read-only aggregation and flag discovery. Does **not** merge domains, replace
ModelRouter, ExecutionGateway, Mission Engine, or run ledgers.
"""
from __future__ import annotations

from saathi.m20_console.flags import disable_procedure, domains_isolated, flag_snapshot
from saathi.m20_console.status import m20_console_status

__all__ = [
    "disable_procedure",
    "domains_isolated",
    "flag_snapshot",
    "m20_console_status",
]
