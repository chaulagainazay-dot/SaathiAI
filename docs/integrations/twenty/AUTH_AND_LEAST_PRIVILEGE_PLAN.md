# Twenty authentication and least-privilege plan

Status: `AUTH_MODEL_READY_WITH_LIMITATIONS`

No account, user, role, token, credential reference, or secret is created here.

## Proposed model

| Field | Future requirement |
| --- | --- |
| Authentication | Expiring Twenty API key sent as a bearer token over private TLS |
| Account type | Dedicated synthetic validation workspace; no production identity |
| Integration principal | Dedicated API key, not a human session or admin credential |
| Role | Custom validation role with view-only object/field access |
| Object scope | Only approved synthetic native/custom objects |
| Mutations | Edit, delete, destroy, import, export, workflow, email, settings mutation denied |
| Metadata | Read only if Twenty enforces it for the role; otherwise block that phase |
| Expiry | Session end plus at most one hour; absolute maximum 24 hours |
| Rotation | New credential per approved validation window |
| Revocation | Revoke immediately on abort and before host deletion |
| Storage | Existing SaathiOS secret backend; Git stores only a credential-reference name |
| Operator access | Named runtime operator for creation/revocation; integration cannot reveal raw value |
| Audit | Creator role, role ID, expiry, reference, request fingerprint, endpoint, outcome; never raw token |

Upstream source documentation confirms that API keys can expire, be regenerated
or deleted, and inherit an assigned role. Roles can allow seeing records while
denying edit/delete/destroy and can restrict fields and workspace actions.

## Material limitations

- Core and metadata APIs expose mutation operations; safety must be technically
  enforced by the assigned role and independently tested with denied mutations.
- It is not yet proven that the pinned runtime permits all required metadata and
  schema reads while denying every mutation.
- API keys without a role inherit default permissions and are forbidden.
- Agent instructions, HTTP method filtering, and adapter declarations are defense
  in depth, not substitutes for runtime role enforcement.

If any intended endpoint requires broader permissions, or any mutation succeeds,
raise `AUTH_SCOPE_TOO_BROAD` or `UNEXPECTED_WRITE_DETECTED`, revoke the key, stop
the runtime phase, and preserve redacted evidence.
