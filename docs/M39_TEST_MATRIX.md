# M39 — Test Matrix

| Area | Coverage | Mode |
|------|----------|------|
| Live preflight fail-closed | yes | offline |
| Missing feature flag | yes | offline |
| Missing acknowledgement | yes | offline |
| Missing secret reference | yes | offline |
| Rejected raw secret input | yes | offline |
| Provider allowlist | yes | offline |
| Endpoint allowlist | yes | offline |
| Method allowlist | yes | offline |
| Identity mismatch | yes | offline fixture |
| Unexpected scope | yes | offline |
| Call-budget exhaustion | yes | offline |
| Aggregate budget exhaustion | yes | offline |
| Separate session handles/leases | yes | offline fixture |
| Cleanup independence | yes | offline fixture |
| Kill-switch | yes | offline |
| Recovery after interruption | yes | offline |
| Duplicate recovery | yes | offline |
| External revocation state | yes | offline |
| Canary recommendation logic | yes | offline |
| Authority non-escalation | yes | offline |
| Leak scan no expose | yes | offline |
| Sanitized provider errors | yes | offline |
| Live single session | NOT_EXERCISED | blocked without secret |
| Live multi session | NOT_EXERCISED | blocked without secret |

Focused module: `tests/test_m39_live_validation.py`
