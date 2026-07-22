"""M15.3 enterprise connector platform layer — OAuth lifecycle, canonical scope/
permission engine, circuit breakers + layered rate limiting, provider error
taxonomy, and the live-validation framework. Extends (never replaces) the M15
platform; all execution still flows through ExecutionEngine → ExecutionGateway
with M15.2 ownership enforcement intact.
"""
from saathi.connectors.platform.enterprise import scopes, oauth, resilience, errors, live_validation

__all__ = ["scopes", "oauth", "resilience", "errors", "live_validation"]
