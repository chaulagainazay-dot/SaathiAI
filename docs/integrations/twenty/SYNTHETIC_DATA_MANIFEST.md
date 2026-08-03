# Twenty synthetic-data manifest

All identifiers and values must be generated specifically for validation. Names
must be unmistakably synthetic, email domains must end in `.invalid`, phone-like
fields must use non-dialable labels, and secrets must be generated outside Git.
No production-derived templates or copied records are permitted.

| Fixture ID | Object type / count | Purpose | Expected validation | Cleanup |
| --- | --- | --- | --- | --- |
| `SYN-WORKSPACE-A` | workspace / 1 | primary tenant | workspace-scoped schemas and reads | delete with runtime volumes |
| `SYN-WORKSPACE-B` | workspace / 1 | isolation tenant | deny cross-workspace access | delete with runtime volumes |
| `SYN-USERS-A` | users / 4 | owner, operator, read-role, negative-role fixtures | role assignment and least privilege | revoke/delete before host removal |
| `SYN-USERS-B` | users / 2 | foreign-tenant principals | cross-tenant denial | delete with workspace B |
| `SYN-COMPANIES-A` | companies / 125 | pagination and filters | stable cursors, limits, ordering, malformed cursor denial | delete with workspace A |
| `SYN-PEOPLE-A` | people / 130 | pagination, relationships, redaction | company joins, field permissions, no real email/phone | delete with workspace A |
| `SYN-OPPORTUNITIES-A` | opportunities / 12 | native-object reads | stages, amounts marked synthetic, relationships | delete with workspace A |
| `SYN-TASKS-A` | tasks / 12 | task schema/read contract | status, assignee, dates, pagination | delete with workspace A |
| `SYN-NOTES-A` | notes / 8 | text and relation contract | safe content mapping and redaction | delete with workspace A |
| `SYN-ACTIVITIES-A` | activities / 8 | activity timeline | ordering and relation mapping | delete with workspace A |
| `SYN-METADATA-A` | native object/field metadata | generated schema capture | REST/conditional GraphQL parity | removed with workspace A |
| `SYN-CUSTOM-ASSET` | custom object / 12 records | custom-object validation | generated endpoints, pagination, schema | remove object and records |
| `SYN-CUSTOM-FIELDS` | text, number, boolean, date, relation fields | type coverage | schema/type/nullability mapping | remove with custom object |
| `SYN-WEBHOOK-VALID` | allowed signed events / 8 | signature and observation tests | accepted once; redacted observation only | purge observation test store |
| `SYN-WEBHOOK-NEGATIVE` | malformed/duplicate/stale/unsupported/out-of-order events / 12 | fail-closed webhook behavior | rejected or safely ordered; no execution | purge test store |
| `SYN-ARCHIVE-DELETE` | archived/soft-deleted records / 6 | lifecycle read behavior | filters and visibility match schema | purge during workspace cleanup |
| `SYN-TENANT-CANARY` | unique markers in both workspaces / 4 | isolation detection | no marker crosses tenant boundary | delete with both workspaces |

Generator rules:

- Use deterministic seed `M361-SYNTHETIC-V1` and record generator version/hash.
- Use UUIDs generated for the disposable environment only.
- Use names prefixed `Synthetic`, domains such as `example.invalid`, and strings
  such as `NON_DIALABLE_001` instead of telephone numbers.
- Use fictional currency values marked `synthetic=true`; no portfolio, billing,
  patient, hospital, employee, supplier, or customer information.
- Record counts and checksums before and after restore; do not store raw credential
  values or unredacted webhook bodies in evidence.
- Cleanup is incomplete until both workspaces, observations, backups, snapshots,
  volumes, credentials, and host storage have been verified removed.
