# Twenty webhook security specification

No production webhook endpoint is exposed in this milestone.

The local verifier implements the upstream HMAC-SHA256 contract over
`timestamp + ":" + raw_body`, constant-time comparison, millisecond timestamp
normalization, bounded freshness, payload-size limits, credential-reference
resolution, event allowlisting, organization/workspace routing, and replay keys
scoped by organization + workspace + event nonce/id.

Accepted payloads are normalized as `CRM_OBSERVATION` with
`direct_execution=false` and `mission_state=PROPOSAL_ONLY`. Rejected and accepted
outcomes emit redacted audit metadata; raw bodies, signatures, and secrets are not
sent to the audit sink. Duplicate, stale, malformed, oversized, unsupported, and
bad-signature events fail closed.

Required production flow:

```text
Twenty webhook
→ size/rate boundary
→ credential-reference resolution
→ signature + timestamp + nonce verification
→ event allowlist + tenant routing
→ idempotent durable inbox
→ redacted audit entry
→ observation or bounded mission proposal
→ SaathiOS policy evaluation
→ human approval where required
→ existing Execution Gateway only
```

The in-memory replay set is adequate only for deterministic unit tests. Production
requires a durable unique constraint with retention, atomic insert-before-accept,
dead-letter quarantine, bounded retry, delivery metrics, secret rotation overlap,
and an incident kill switch. Webhook arrival must never directly send email, write
CRM data, alter an account, perform financial/trading work, or invoke tools.
