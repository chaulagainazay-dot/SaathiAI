# SaathiOS ↔ Twenty architecture and operations

## Separation

```text
SaathiOS authority plane
├── Identity / organization / workspace scope
├── Approval Center
├── Execution Gateway
├── Mission Runtime
├── Audit ledger
└── Canonical Connector Registry
    └── Twenty read-only declaration (OFF/SHADOW only)
        ├── TwentyClient (injected transport; no built-in network)
        ├── TwentyReadService
        ├── schema mapper + provenance
        ├── webhook verifier → observation only
        └── health contract
             │
             ▼ future governed GET transport
Isolated Twenty service
├── CRM objects and activities
├── generated REST / GraphQL schemas
├── signed webhooks
└── custom objects
```

Twenty remains optional and replaceable. It owns CRM records and CRM-native
workflows. SaathiOS retains identity scope, missions, agents, approvals, audit,
policy, business intelligence, and every external-action decision.

## Current implementation state

`saathi/integrations/twenty/` is versioned contract scaffolding, not live
connectivity. It composes with `ConnectorManifest`, declares only READ capability,
uses OFF/SHADOW rollout compatibility, holds only credential-reference names, and
has no network transport. `FixtureTransport` is deterministic and socket-free.

Supported contract methods:

- list/retrieve companies, people, opportunities, and tasks;
- fetch object metadata and custom-object schema;
- health status contract;
- verify and normalize signed webhooks into observations.

The read mapper attaches SaathiOS organization/workspace scope, read-only state,
provider version, and `FIXTURE_ONLY_NOT_LIVE_VALIDATED` provenance. Unknown objects,
cross-scope calls, non-GET requests, malformed payloads, transport errors, timeouts,
and all write attempts fail closed.

## Secrets policy

Raw credentials are forbidden in config, URLs, logs, fixtures, evidence, and Git.
Only a reference such as `TWENTY_API_CREDENTIAL_REFERENCE` may cross the adapter
boundary. A future governed transport resolves it in-process through the existing
credential subsystem. The current implementation does not resolve or use a token.

## Sandbox operations

Prepared files live at
`/Users/macbookpro/dev-toolkits/twenty-saathios-sandbox`, outside SaathiOS and the
upstream clone. The topology binds only `127.0.0.1:3020`, has an internal Docker
network, disables email/provider integrations/telemetry, and uses names explicitly
prefixed `saathios_twenty_sandbox`. See its README for start/stop/status/log/reset,
backup, upgrade, and uninstall procedures.

The sandbox is not runnable on the audited host until Docker/Compose is installed
under separate owner authority and resources are reassessed.

## Production prerequisites

1. Approved container runtime or private development host with capacity evidence.
2. Published Twenty image digest pinned and vulnerability/licence review recorded.
3. Synthetic instance boot, setup, restart, backup/restore, and upgrade proven.
4. Exact generated REST/GraphQL schemas captured from that synthetic workspace.
5. A least-privilege read-only Twenty role and referenced credential.
6. Existing governed connector HTTP adapter bound through Execution Gateway policy;
   never a direct client hidden in this package.
7. Rate limits, pagination, timeout/retry, circuit breaker, TLS, and SSRF policy tested.
8. Webhook receiver authenticated and privately reachable without direct execution.
9. Tenant mapping, deletion/retention, incident response, and revocation certified.
10. Separate approval milestone before any write method exists.
