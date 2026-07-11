# M15.2 Agent Security Audit

## Starting state
Commit `b353f44` (M15.1). 1237 passed. STAGING READY (connectors).

## Attack surfaces + trust boundaries audited
Chat, M10 orchestrator/delegation (`agent_runtime/gateway_exec.py` — already
routes tool requests policy→approval→gateway, no-op/awaiting_approval states),
M9 memory scopes, connector integration funnel, ExecutionEngine, ExecutionGateway,
approval binding, credential resolver, MCP wrapper, webhook platform, sync,
Voice confirmation, CEO evidence, event bus. Untrusted content crossing any
boundary is treated as DATA.

## Existing protections (verified by probes)
Approval binding to exact action, risk-4 manual-only, idempotency, uncertain/
non-idempotent no-retry, secret redaction, credential scope validation, MCP
risk clamp, webhook HMAC+replay, direct-call scanner.

## Weak assumption found + remediated
**ExecutionEngine did not verify account ownership** — the M15.1 API enforced it
(`_own_account` → 403) but the integration funnel / M10 agents call the engine
directly, so a cross-user execution succeeded (probe ISO-001, CRITICAL). Fixed at
the engine boundary: ownership + account/connector match now enforced inside
`ExecutionEngine.execute`. Re-run 20/20 hold; regression test added. This is
exactly the value of a red-team harness: it found a real gap the unit tests
missed and drove a boundary fix (not a test patch).

## Harness architecture
`saathi/security/redteam/`: config (target/prod-block/redaction/budget, HackAgent
pinned 0.3.0 optional, cloud-sync off), findings (deterministic authoritative,
judge advisory), targets (isolated in-process temp db, isolated user/attacker),
probes (20 deterministic attacks against real boundaries), runner, baseline +
compare, report + release-gate, hackagent wrapper (env-blocked when absent),
CLI, read-only report API (`/api/v1/security/redteam/*`, prod-disabled).
Corpus: `security/redteam/attacks/corpus.yaml` (v1, 20 attacks) + `targets.yaml`.

## Coverage + honest limits
- DETERMINISTICALLY VERIFIED: prompt/indirect injection, goal hijack, tool misuse,
  approval bypass (changed-input/replay/forged), privilege/delegation, memory
  poisoning, cross-user isolation, secret extraction, MCP, webhook, unsafe retry,
  CEO evidence.
- ENVIRONMENT BLOCKED: HackAgent adversarial-model generation (optional dep not
  installed), interactive browser + Voice attack runtime, live cloud connector
  attack surfaces (no credentials). Not faked, not claimed.

## Remediation priorities (remaining)
Install + run HackAgent bounded suites against a staging server; exercise live
browser + Voice attack paths; test representative live connectors — all gated on
credentials + running authenticated staging infra (SECURITY PRODUCTION READY).

## Note on HackAgent
HackAgent is an isolated, pinned (0.3.0), Apache-2.0 dev-security test runner —
advisory only, local mode, cloud sync off, never on the production request path.
