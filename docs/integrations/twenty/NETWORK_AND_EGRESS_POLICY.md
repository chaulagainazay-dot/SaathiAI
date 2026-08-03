# Twenty private network and egress policy

Default policy:

```text
DENY_PUBLIC_EXPOSURE
DENY_UNNECESSARY_EGRESS
DENY_EMAIL
DENY_EXTERNAL_OAUTH
DENY_THIRD_PARTY_INTEGRATIONS
ALLOW_ONLY_EXPLICIT_VALIDATION_PATHS
```

## Required reachability

| Source | Destination | Port/protocol | Purpose | Control |
| --- | --- | --- | --- | --- |
| Named operator | private host | SSH or management plane | provisioning/diagnostics | VPN/IP allowlist, MFA, time-bounded |
| Named operator browser | private Twenty UI | HTTPS 443 | synthetic setup and inspection | private DNS/TLS, operator only |
| SaathiOS validation process | private Twenty server | HTTPS 443 | health and approved read-only REST/GraphQL | exact private address, credential reference |
| Twenty server/worker | PostgreSQL | TCP 5432 | internal runtime data | container/private subnet only |
| Twenty server/worker | Redis | TCP 6379 | internal queues/cache | container/private subnet only |
| Twenty runtime | private SaathiOS webhook receiver | HTTPS 443 | M365 validation only | disabled until private delivery is proven |
| Operator provisioning session | approved registries/package sources | HTTPS 443 | digest-resolved artifacts only | temporary explicit allowlist; disabled at runtime |
| Runtime | private DNS/NTP | provider-specific | name/time integrity | explicit resolver/time source only |

PostgreSQL, Redis, admin UI, and webhook receivers must never bind publicly. No
wildcard ingress, `0.0.0.0/0` security group, public IP dependency, public DNS,
or plaintext remote access is allowed. Application TLS must use an approved
private certificate chain and hostname; certificate verification cannot be disabled.

## Egress controls

- Default-deny after artifact acquisition.
- Log denied destinations without payloads or secrets.
- Block SMTP, IMAP, CalDAV, external OAuth, analytics/telemetry, update checks,
  workflow HTTP actions, webhooks other than the approved private receiver, and
  third-party app integrations.
- Inventory attempted DNS names and destinations during idle and test phases.
- Temporarily allowed registry traffic must be tied to immutable digests and end
  before validation begins.
- SaathiOS may call only `/healthz` and explicitly approved read-only REST or
  conditional GraphQL paths. Mutating methods and endpoints are denied in both
  the network proxy and the runtime role.

## Webhook conflict

The inspected upstream documentation says a configured webhook URL must be
publicly accessible and that all event types are sent. This conflicts with the
private-only policy. The future program must first prove that the pinned
self-hosted runtime accepts a private route. If it does not, M365 remains blocked
unless the owner separately approves a hardened public receiver. A tunnel,
temporary public URL, or relaxed firewall is not an implicit workaround.

Any public exposure, unexpected egress, external email/OAuth traffic, telemetry
that cannot be disabled, or data-service exposure triggers immediate isolation
and the applicable abort condition.
