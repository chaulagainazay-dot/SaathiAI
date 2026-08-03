# Future approval-gated CRM writes (design only)

No write operation is implemented or activated.

Potential later commands are create note, create follow-up task, update opportunity
stage, add relationship tag, update a custom object, and attach an approved research
summary. Delete operations remain out of scope.

Every future command must be a canonical connector intent handled by the existing
Execution Gateway. It must bind actor, organization, workspace, target record,
operation, exact before/after fields, credential reference, idempotency key,
connector version, authority, approval ID, expiry, and evidence policy. Caller input
cannot lower the side-effect classification or approval floor.

The gateway must resolve the registered connector and scoped credential, recheck
Twenty and SaathiOS permissions at execution time, enforce deny-overrides-allow,
write the audit intent before dispatch, perform the smallest mutation, record a
redacted response fingerprint, and make replay return the prior result. Revocation,
expired/mismatched approval, schema drift, ambiguous target, partial failure, or
unknown outcome must stop closed. No direct HTTP client, webhook shortcut,
application logic function, agent, or mission may bypass the gateway.
