# M320–M327 — Credentialless Provider Contracts & Mock Connectivity

## Scope

M320–M327 adds a provider-neutral contract layer for deterministic, offline
market fixtures. It composes with the M312–M319 connectivity-governance
registry, authority lattice, approval semantics, audit store, security scans,
maturity model, and certification framework.

The milestone does not connect to a broker or exchange. Platform operator
authentication protects the existing Control Center and API, but provider
authentication does not exist.

## Authority and non-implication

The contract is governed by this fail-closed chain:

```text
contract presence ≠ capability activation
capability declaration ≠ permission
permission ≠ connectivity
connectivity ≠ account access
account access ≠ order authority
```

Deny overrides allow. An approval remains `APPROVED_NOT_ACTIVE` and does not
activate a provider. An LLM may neither approve nor activate provider
capabilities. All 17 hard authority values remain false.

## Architecture

`saathi/platform/tg/provider_contracts/` contains:

- provider-neutral `Provider`, `MarketDataProvider`, `AccountProvider`,
  `OrderProvider`, `ConnectivityProvider`, and `SessionProvider` contracts;
- a `ProviderTransport` abstraction and closed `TransportRegistry`;
- deterministic `MockTransport` and integrity-checked `ReplayTransport`;
- request, response, provider, capability, replay, error, and session schemas;
- deterministic synthetic fixture catalog;
- process-local idempotency ledger;
- governance-composed service, API, CLI, audit, evidence, and certification;
- static isolation scanning scoped to the provider-contract package.

Account and order interfaces are intentionally abstract and have no concrete
implementation.

## Capability model

| Capability | State | Data |
|---|---|---|
| quotes | `SUPPORTED_OFFLINE` | synthetic fixture |
| candles | `SUPPORTED_OFFLINE` | synthetic fixture |
| trades | `SUPPORTED_OFFLINE` | paginated synthetic fixture |
| orderbook | `SUPPORTED_OFFLINE` | synthetic fixture |
| symbols | `SUPPORTED_OFFLINE` | paginated synthetic fixture |
| market_status | `SUPPORTED_OFFLINE` | synthetic fixture |
| balances | `FORBIDDEN_BY_GOVERNANCE` | none |
| positions | `FORBIDDEN_BY_GOVERNANCE` | none |
| orders | `FORBIDDEN_BY_GOVERNANCE` | none |
| transfers | `FORBIDDEN_BY_GOVERNANCE` | none |

The negotiation vocabulary also includes `UNSUPPORTED` and `UNAVAILABLE`.
Negotiation reports state; it never grants authority or performs work.

## Mock behavior

Mock values, timestamps, identifiers, hashes, pagination cursors, and market
states are fixed. The catalog uses no current time and no randomness.
`simulated_latency_ms` is response metadata and causes no wait. Deterministic
error injection supports offline timeout and unavailability simulations.

Every response includes:

```text
source_type=MOCK
live=false
synthetic=true
account_derived=false
execution_capable=false
```

## Replay behavior

Replay records bind canonical request fingerprints to synthetic responses.
Duplicate fingerprints, malformed records, missing fixtures, and integrity
hash mismatches fail closed. Replay provenance changes to
`source_type=REPLAY`; it is never described as live, broker, account-derived,
or executable.

Fixtures were authored for this milestone. They contain no credential,
account, customer, portfolio, proprietary provider, or personal data.

## Validation and error model

Strict schemas reject missing, unknown, sensitive, or malformed request fields;
invalid provider declarations; capability-operation mismatches; malformed
response provenance; invalid error envelopes; malformed replay records; and
invalid session transitions.

Provider-independent errors include invalid request/response, unsupported or
forbidden capability, provider/transport unavailable, fixture missing/conflict,
timeout simulation, replay-integrity failure, invalid session state, and
idempotency conflict.

## Idempotency

Every request requires a deterministic idempotency key. The request fingerprint
is a canonical SHA-256 digest of provider, operation, parameters, and schema
version.

- same key + same request returns the same response;
- same key + different request fails closed;
- fresh processes derive identical fingerprints and responses;
- no record changes capability or authority.

The milestone adds no persistent idempotency store. Therefore no persistence
or restart-recovery authority is claimed.

## Offline session lifecycle

Allowed states:

```text
DISCONNECTED
MOCK_READY
REPLAY_READY
UNAVAILABLE
FAULTED
CLOSED
```

Readiness must match the offline transport. `CLOSED` is terminal. Active
offline states may close or fault; `FAULTED` may only close.

Forbidden state semantics:

```text
AUTHENTICATED
LOGGED_IN
ACCOUNT_CONNECTED
BROKER_CONNECTED
LIVE
TRADING_READY
EXECUTION_READY
```

## Network and SDK isolation

Only `mock` and `replay` transport names are accepted. The registry performs no
dynamic imports. The package scan rejects HTTP clients, WebSocket clients, raw
sockets, subprocess network clients, browser provider access, broker/exchange
SDKs, and dynamic import calls. Tests execute mock requests while socket
creation is blocked.

## Bounded surfaces

- API: `/api/v1/platform/tg/provider-contracts/*`
- CLI: `pc-charter`, `pc-providers`, `pc-capabilities`, `pc-sessions`,
  `pc-replay-fixtures`, `pc-mock-quote`, `pc-replay-quote`, `pc-security`,
  `pc-certify`
- UI: `/trading/provider-contracts`,
  `/trading/provider-contracts/capabilities`,
  `/trading/provider-contracts/replay`

The UI displays `OFFLINE MOCK DATA`, `NO PROVIDER CONNECTION`,
`NO ACCOUNT ACCESS`, and `NO ORDER EXECUTION`. It has no provider credential,
OAuth, login, account-link, live-connect, order-entry, paper-order, transfer,
withdrawal, canary, deployment, or release control.

## Maturity and limitation

- Target verdict:
  `PROVIDER_CONTRACTS_AND_MOCK_CONNECTIVITY_CERTIFIED_WITH_LIMITATIONS`
- Maximum state: `MOCK_PROVIDER_READY_NO_REAL_CONNECTIVITY`
- Maturity: `MOCK_CONNECTIVITY_ONLY`

No statement in this document implies real-provider integration. Any future
connectivity work requires a separate milestone and new explicit human
authority. M328 and later work is not part of this milestone.
