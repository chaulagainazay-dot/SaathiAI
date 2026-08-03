# M361B read-only endpoint enforcement

Conclusion: `AUTH_MODEL_READY_WITH_LIMITATIONS`

No account, role, API key, token, OAuth client, or endpoint was created or used.
This is a static assessment of the pinned upstream documentation and existing
SaathiOS contracts.

Upstream supports expiring API keys assigned to custom roles. A role can enable
record visibility while leaving edit, delete, and destroy disabled, and can
restrict objects, fields, settings, and actions. However, Core and Metadata API
surfaces both expose mutations. A role is the intended provider-side control;
HTTP method filtering and the SaathiOS allowlist are defense in depth only.

## Planned endpoint matrix

| Endpoint/operation | Purpose | Type | Required future role | Classification | Mutation risk | Required negative test | Limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/healthz` | readiness only | GET | none or minimum documented health access | `TECHNICALLY_READ_ONLY` | low | POST/PUT/PATCH/DELETE rejected or route absent | auth behavior must be confirmed on pinned runtime |
| `/rest/{companies|people|opportunities|tasks}` | list synthetic records | GET | custom role: See Records only for approved objects/fields | `READ_ONLY_BY_ROLE_BUT_NOT_ENDPOINT` | same API family exposes create/update/delete | POST, PATCH, DELETE, batch create/upsert all denied | provider enforcement not live-proven |
| `/rest/{object}/{record_id}` | retrieve one synthetic record | GET | same custom role | `READ_ONLY_BY_ROLE_BUT_NOT_ENDPOINT` | same credential may reach mutation routes if role is wrong | PATCH and DELETE known synthetic ID denied | row-level restriction may require premium plan; do not assume it |
| `/rest/metadata/objects` | enumerate schemas | GET | explicit minimum settings/data-model visibility | `UNKNOWN` | Metadata API is explicitly a create/modify/delete management surface | metadata POST/PATCH/DELETE denied and no settings mutation allowed | documentation does not prove a read-only Metadata permission combination |
| `/rest/metadata/objects/{id}` | inspect custom-object schema | GET | same minimum metadata visibility | `UNKNOWN` | object/field mutation routes share the API family | create/update/delete object and field denied | block M364 if provider-side denial cannot be proven |
| `/graphql/` query | optional record/relationship query | GraphQL query | same object/field read role | `READ_ONLY_BY_ROLE_BUT_NOT_ENDPOINT` | queries and mutations share one endpoint | create/update/delete/upsert mutations denied | enable only after schema and role tests pass |
| `/metadata/` query | optional metadata GraphQL query | GraphQL query | explicit minimum metadata visibility | `UNKNOWN` | metadata mutations share one endpoint | object/field/settings mutations denied | not acceptable on client allowlist alone |
| approved custom-object Core GET | validate synthetic custom schema records | GET | explicit See Records/See Field rule for that object | `READ_ONLY_BY_ROLE_BUT_NOT_ENDPOINT` | object mutation routes exist | create/update/delete/upsert denied | custom object is synthetic and owner-approved only |

## Required role and denial proof

The future credential must be a dedicated, expiring API key assigned to a custom
role. It must not inherit default permissions. Required positive permissions are
only approved record/field visibility and, if provider-enforceable, minimum
metadata visibility. Edit, delete, destroy, import, export, email, workflow,
settings mutation, API-key administration, role administration, and data-model
mutation remain disabled.

M363–M364 must prove all listed mutation denials with a known synthetic target,
then verify the target is unchanged. It must also test unassigned/default-role
rejection, expired and revoked credentials, cross-object/field denial,
cross-workspace denial, GraphQL aliases/batches/upserts, Metadata mutations, and
admin routes. Any successful mutation yields `AUTH_SCOPE_TOO_BROAD`, immediate
credential revocation, phase abort, and redacted evidence.

OAuth is not relevant or authorized. If Metadata reads require a role that can
write, Metadata validation is `NOT_ACCEPTABLE` and must be removed from the
approved runtime scope rather than relying on prompts or the client allowlist.
