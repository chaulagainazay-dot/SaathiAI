"""M17 Universal Computer Agent — desktop/browser/vision as governed connectors.

SaathiOS operates desktop apps and browsers by registering computer operations as
M15 connector tools, so every action flows through the SAME ExecutionEngine →
ExecutionGateway → risk/approval → evidence path. There is NO new execution
engine. Perception is provider-abstracted (Playwright/CDP/accessibility/OCR/
vision), deterministic by default; live desktop control is environment-blocked
(no installed provider / no permission here) and honestly reported. Mutating ops
run a post-action visual verification (never assume success); destructive ops
(delete/purchase/send/deploy) are risk-gated and require approval. Replays are
sanitized (never passwords/OTP/secrets).
"""
from saathi.computer_agent import operations  # registers connectors on import
from saathi.computer_agent.agent import ComputerAgent
from saathi.computer_agent.perception import Screen, UIElement, ElementType
from saathi.computer_agent.providers import provider_availability, default_provider
from saathi.computer_agent.replay import Replay

__all__ = ["ComputerAgent", "Screen", "UIElement", "ElementType",
           "provider_availability", "default_provider", "Replay", "operations"]
