# M53 Reconciliation Model

## Attention classifications

`APPROVAL_REQUIRED`, `APPROVAL_EXPIRED`, `APPROVAL_REJECTED`,
`PAUSED_AFTER_RESTART`, `DISPATCH_OUTCOME_UNCERTAIN`,
`CANCELLATION_PENDING`, `TIMEOUT_PENDING`, `CONTEXT_INVALIDATED`,
`BINDING_SUSPENDED`, `BINDING_REVOKED`, `IDEMPOTENCY_CONFLICT`, and
`MANUAL_REVIEW_REQUIRED`.

Classifications are derived from persisted runtime, approval, binding, and
audit evidence. Absence of evidence is never converted into dispatch certainty.

## Operator actions

Supported bounded actions are mark reviewed, attach note, leave paused, cancel
before dispatch, confirm an elapsed timeout, revalidate context, request a new
approval, reject resume, resolve failed, resolve cancelled, and resume.

Controls:

- every request requires owner/admin runtime-operation permission and an
  execution-scoped idempotency key;
- duplicate reconciliation is rejected before any state action;
- terminal state mutation is rejected;
- resume is permitted only when no dispatch was recorded and returns through
  `PlatformAgentRuntime`;
- a recorded dispatch is never replayed automatically or manually;
- notes/evidence references are bounded safe text, not arbitrary payloads;
- every accepted or rejected decision is audited.

SQLite provides deterministic single-host compare/version behavior, not
multi-host consensus.
