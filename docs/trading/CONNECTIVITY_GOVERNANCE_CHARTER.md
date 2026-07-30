# Trading Connectivity Governance Charter

**Version:** 1.0.0  
**Milestones:** M312–M319  
**Status:** GOVERNANCE ONLY — NO PROVIDER CONNECTION

## Purpose

Define who may request, approve, scope, expire, revoke, and emergency-stop any future provider connectivity **before** any connection may be considered.

## Principles (20)

1. No connectivity by default
2. All authority is explicit
3. Authority is narrowly scoped
4. Authority expires
5. Authority is revocable
6. Authority does not cascade automatically
7. Read authority does not imply write authority
8. Market-data access does not imply account access
9. Account access does not imply order access
10. Paper execution does not imply live execution
11. Live execution cannot be granted in this milestone
12. Credentials must never be pasted into chat or stored in evidence
13. Provider capabilities must be allowlisted
14. Unsupported capabilities must fail closed
15. Human approval is required for every authority expansion
16. Every decision must be auditable
17. Emergency shutdown must dominate all other authority
18. LLM recommendations are non-authoritative
19. No model or agent may approve its own authority
20. No milestone may silently inherit higher authority

## Human Accountability

- Explicit human requestor and approver identities
- Maker-checker separation (no self-approval)
- No LLM approval or activation
- Emergency powers require a human actor
- Recovery after shutdown requires human review

## Prohibited Operations

Broker login, OAuth, real API keys, credential storage/validation, account/balance/position access, order submit/modify/cancel, transfer, withdrawal, live trading, external paper execution, canary activation, production activation, authenticated provider calls.

## Approval Rule

**Approval does not equal activation.** Maximum approval state in M312–M319 is `APPROVED_NOT_ACTIVE`.

## Maturity

Current certified maturity: **GOVERNANCE_ONLY**  
Maximum state: **CONNECTIVITY_GOVERNANCE_READY_NO_PROVIDER_CONNECTION**

## Evidence

See `docs/trading/m312_m319_evidence/M312_CONNECTIVITY_GOVERNANCE_CHARTER.json`.
