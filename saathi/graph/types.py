"""Knowledge Graph ontology — node and edge types (M2 Phase 4).

A richer ontology than Episode/Knowledge/Pattern: the graph models goals,
strategies, capabilities, decisions, and everything between, so SaathiAI can
answer questions no isolated memory can — "which capabilities contribute most
toward my financial goal?", "why are we using Renderer Y?", "which ADR
introduced this rule?".

AP-19 — Relationships are first-class knowledge: an edge is often more valuable
than the nodes it connects.
"""
from __future__ import annotations

from enum import Enum


class NodeType(str, Enum):
    GOAL = "Goal"
    STRATEGY = "Strategy"
    CAPABILITY = "Capability"
    PRODUCT = "Product"
    DEPARTMENT = "Department"
    AGENT = "Agent"
    TOOL = "Tool"
    WORKFLOW = "Workflow"
    KNOWLEDGE = "Knowledge"
    EPISODE = "Episode"
    EXPERIMENT = "Experiment"
    IMPROVEMENT = "Improvement"
    DECISION = "Decision"        # ADR
    RISK = "Risk"
    METRIC = "Metric"
    TASK = "Task"
    DOCUMENT = "Document"
    USER = "User"
    MODEL = "Model"
    PROVIDER = "Provider"


class EdgeType(str, Enum):
    ACHIEVED_BY = "ACHIEVED_BY"          # Goal      → Strategy
    IMPLEMENTED_BY = "IMPLEMENTED_BY"    # Strategy  → Capability
    USED_BY = "USED_BY"                  # Capability→ Product
    IMPROVED_BY = "IMPROVED_BY"          # Capability→ Improvement
    DERIVED_FROM = "DERIVED_FROM"        # Knowledge → Episode
    VALIDATED = "VALIDATED"              # Experiment→ Improvement
    GOVERNS = "GOVERNS"                  # Decision  → Capability
    IMPLEMENTS = "IMPLEMENTS"            # Task      → Capability
    DEFINES = "DEFINES"                  # Document  → Architecture/Capability
    DEPENDS_ON = "DEPENDS_ON"            # Capability→ Capability
    SUPPORTS = "SUPPORTS"                # Evidence  → Knowledge
    SUPERSEDES = "SUPERSEDES"            # new       → old (evolution)
    MEASURED_BY = "MEASURED_BY"          # Capability→ Metric
    CONTRIBUTES_TO = "CONTRIBUTES_TO"    # Capability→ Goal
    ROUTES_TO = "ROUTES_TO"              # Router    → Provider
