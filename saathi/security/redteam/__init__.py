"""M15.2 Agent Security Red-Team Harness.

A SaathiOS-owned, isolated, deterministic adversarial security harness that
continuously proves the M8–M15.1 boundaries hold under attack: prompt injection,
tool misuse, approval bypass, delegation/privilege escalation, memory poisoning,
cross-user isolation, secret extraction, MCP manipulation, webhook injection,
unsafe retry. Deterministic probes are authoritative; the optional pinned
HackAgent generator is advisory and disabled by default (environment-blocked
when absent). Never on the production request path.
"""
from saathi.security.redteam.config import RedTeamConfig, redact, assert_target_authorized
from saathi.security.redteam.runner import run_all, run_suite
from saathi.security.redteam.report import build_report, release_gate
from saathi.security.redteam import baseline

__all__ = ["RedTeamConfig", "redact", "assert_target_authorized", "run_all",
           "run_suite", "build_report", "release_gate", "baseline"]
