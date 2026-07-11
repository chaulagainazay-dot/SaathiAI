"""M16 Unified Control Center — read/observation + safe control layer.

One command center over the CANONICAL SaathiOS subsystems (connectors, security
red-team, ops release gates, event bus, live-validation). It is NOT an execution
engine: it never calls providers, never writes to subsystem stores, never
bypasses ExecutionGateway. Mutations are rendered as action descriptors that
point at canonical subsystem APIs. Aggregation is bounded and degrades honestly
on partial subsystem failure; every cell carries source + freshness.
"""
from saathi.control_center.aggregator import ControlCenterAggregator, Cell, guarded
from saathi.control_center import search, actions

__all__ = ["ControlCenterAggregator", "Cell", "guarded", "search", "actions"]
