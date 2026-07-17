# M30 — Sandbox Harness

**Module:** `saathi.connectors.conformance.sandbox`

## Guarantees

| Property | Value |
|----------|-------|
| Real secrets | none |
| Paid services | none |
| Uncontrolled internet | none |
| Arbitrary filesystem | blocked (temp dir only) |
| Arbitrary subprocess | blocked (allowlisted ops / fake runner) |
| Arbitrary domains | policy + fake browser allowlist |
| Deterministic | clock + fixed IDs + fake transports |
| Cleanup | context manager / `close()` |

## Components

* `FakeHttpTransport` — process-local HTTP
* `FakeMcpServer` — in-process tool stub
* `FakeBrowserGateway` — session ownership / domain stub
* `FakeLocalToolExecutor` — allowlisted ops only
* `DeterministicClock`
* `TemporaryEvidenceStore` / `TemporaryApprovalStore` / `TemporaryIncidentStore`

## Runtime path

Harness constructs a real `GovernedConnectorRuntime` and M29 builtin manifests
with sandboxed adapters. Policy, side-effects, rollout, and approvals are the
production modules — not reimplemented.
