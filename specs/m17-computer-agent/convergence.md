# M17 Convergence Report
Gate: converge specs/m17-computer-agent/traceability.json → CONVERGED 10/10.
Red-team (deterministic): 34/34 boundaries hold (5 new computer-agent probes), 0 blocking.

## Remediation
Expansion probe COMPUTER-001 initially expected approval_required for an agent
risk-4 delete; the M15.3 scope engine BLOCKS agent risk-4 outright (stronger).
Probe corrected to accept the safer `blocked` outcome — no code weakened.

## Evidence classes
- IMPLEMENTED + AUTOMATED-TESTED: perception model, provider abstraction,
  operations-as-connectors, verification contract, replay, agent runner (12 tests).
- RED-TEAM TESTED: destructive-needs-approval, password-not-in-replay, agent-no-
  self-approve-purchase, cross-user desktop isolation, never-assume-success.
- DESKTOP-TESTED / BROWSER-TESTED (live): NONE. Live desktop control + real
  browser actuation are ENVIRONMENT-BLOCKED (no installed+enabled provider / no
  Accessibility permission / no vision credentials). Deterministic provider is
  authoritative; importable != verified live control (honestly reported).

## Verdict
DESKTOP STAGING READY — the computer-agent perception → gateway-routed execution →
visual-verification → sanitized-replay spine is deterministically verified and
red-team-tested, with destructive ops risk-gated and every action flowing through
ExecutionGateway (no bypass). Live desktop/browser actuation on real authenticated
applications remains environment-blocked — required for DIGITAL WORKER PILOT/
PRODUCTION READY.
