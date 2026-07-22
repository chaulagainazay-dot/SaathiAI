# M15.2 Convergence Report
Gate: `python -m saathi.specs.cli converge specs/m15-2-agent-security/traceability.json`
Verdict: CONVERGED — 15/15 requirements mapped to code + a passing deterministic test.

## Red-team result (deterministic, authoritative)
Corpus v1: 20 attacks. Boundaries held: 20/20. Confirmed vulnerabilities: 0.
Release-blocking (Critical/High): 0.

## Remediation performed
The harness found ONE confirmed CRITICAL on first run — ISO-001 cross-user
execution: the ExecutionEngine did not verify account ownership (the API did, but
the integration funnel / agents call the engine directly). Root-cause fix in
saathi/connectors/platform/execution.py: ownership + account/connector match
enforced in the engine itself. Re-run: 20/20 held. Regression-protected by
tests/test_m15_2_security.py::test_iso_001. No M15/M15.1 regression.

## Evidence classes
- DETERMINISTICALLY VERIFIED: all 20 attack boundaries + harness units.
- REMEDIATED AND REGRESSION TESTED: ISO-001 (cross-user execution).
- ENVIRONMENT BLOCKED: HackAgent adversarial-model generation (not installed),
  live browser + Voice attack runtime, cloud connector attack surfaces (no creds).
- NOT claimed: any adversarial-model or live-connector security coverage.

## Verdict
SECURITY STAGING READY — deterministic controls green, no Critical/High confirmed,
remediation regression-tested. Adversarial-model + live browser/Voice + live cloud
connector attack paths remain environment-blocked (SECURITY PRODUCTION READY needs
those + production-representative infra + rehearsed incident handling).
