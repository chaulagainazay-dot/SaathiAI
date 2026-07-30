# M216–M223 — Broker Integration Sandbox Architecture & Trust Framework

**Terminal verdict:** `BROKER_SANDBOX_ARCHITECTURE_CERTIFIED_WITH_LIMITATIONS`

**Branch:** `milestone/m216-m223-broker-sandbox-architecture`

## Required statements

**THE SYSTEM REMAINS PAPER ONLY.**

**NO BROKER CONNECTIONS EXIST.**

**NO API CREDENTIALS WERE CREATED.**

**NO LIVE TRADING IS AUTHORIZED.**

**THE SANDBOX CANNOT EXECUTE REAL ORDERS.**

## Scope

Design and implement the complete architecture that future broker integrations will use while remaining fully disconnected from every real exchange and broker.

Continues from:

- M166–M191 Historical Research
- M192–M199 Paper Activation
- M200–M207 Durable Paper Operations
- M208–M215 Operational Graduation

Does **not** redesign Trading Guardian, Risk Engine, Paper Engine, Approval System, Ledger, Evidence, or Operational Graduation — only composes.

## Package

```
saathi/platform/tg/broker_sandbox/
  models.py           enums, posture, LLM boundary, catalog
  schema.py           additive SQLite tables (bs_*)
  store.py            SandboxStore
  abstraction.py      M216 generic broker interfaces
  registry.py         M217 capability registry (all NOT_CONNECTED)
  credentials.py      M218 metadata-only credential trust
  emulator.py         M219 deterministic sandbox emulator
  trust_pipeline.py   M220 multi-stage trust approval
  failure.py          M221 failure & recovery simulation
  security.py         M222 security validation suite
  control_center.py   M223 control center read model
  service.py          BrokerSandboxService facade
```

API prefix: `/api/v1/platform/tg/broker-sandbox/*`  
UI: `/trading/broker-sandbox`  
CLI: `python -m saathi.platform.tg paper-gov bs-*`  
Browser cert: `npm run cert:m223` (from `saathi-os/`)

## Milestone map

| ID | Capability | Result |
| --- | --- | --- |
| M216 | Generic broker interfaces (Broker, Account, Portfolio, Position, Order, Trade, ExecutionReport, MarketData, Asset, Balance, Connection, Capability) — no real broker impl | Implemented + tested |
| M217 | Capability registry: assets, paper, order types, margin, options, futures, crypto, equities, rate limits, auth method, streaming, order events, time zones, status — all NOT_CONNECTED | Implemented + tested |
| M218 | Credential references, provider metadata, scopes, rotation, expiry, revocation, audit, approval chain — never stores secrets, never usable | Implemented + tested |
| M219 | Deterministic emulator: market/limit, partial fills, rejects, timeouts, disconnects, latency, rate limiting, market closed, invalid symbols, network failures | Implemented + tested |
| M220 | Trust pipeline: owner, security, credential, risk, environment, simulation, paper graduation, manual confirmation — nothing auto-activates; never live | Implemented + tested |
| M221 | Failure suite: network loss, outage, duplicate/late fills, clock skew, replay, sequence gaps, connection loss, credential expiry, recovery, rollback — fail closed | Implemented + tested |
| M222 | Security: broker/credential/approval isolation, audit integrity, LLM boundaries, environment/sandbox separation, no approval bypass | Implemented + tested |
| M223 | Control Center UI: registry, capabilities, emulator, trust, approvals, credentials, recovery, audit, security — SANDBOX ONLY / NO LIVE BROKER | Implemented + tested |

## LLM boundary

LLM may: explain, recommend, analyse, compare, generate reports, simulate.

LLM may **not**: connect brokers, store credentials, approve credentials, approve brokers, execute orders, enable live mode, authorize trading, bypass approval.

## Explicit non-actions

No Binance / Alpaca / Interactive Brokers / Zerodha / Bybit / Coinbase / Kraken login.  
No broker API keys. No OAuth. No production deployment. No live trading.

## Verification

| Gate | Result |
| --- | --- |
| Focused M216–M223 | 18 passed |
| M200–M223 subset | 48 passed |
| Frontend unit | 2 passed |
| Security suite | 8/8 all_passed |
| Failure suite | 19 scenarios, all_fail_closed |
| Authority / credential scan | clean (no live flags, no usable secrets) |
| CLI `paper-gov bs-verdict` | pass |
| Browser cert | `BROKER_SANDBOX_BROWSER_CERT_PASSED_WITH_LIMITATIONS` (0 hard fails; 1 soft UI auth journey) |
| Terminal verdict | `BROKER_SANDBOX_ARCHITECTURE_CERTIFIED_WITH_LIMITATIONS` |

## Limitations

- Single-host SQLite
- Catalog brokers are design metadata only (never connect)
- Credential references never hold secrets and cannot authenticate
- Trust approval is sandbox-scoped only (never live)
- Owner human sign-off not claimed
- Browser cert may soft-limit on unauthenticated UI journey

## Owner sign-off

`NOT_CLAIMED_AUTOMATED_ONLY`

## Evidence

`docs/trading/m216_m223_evidence/`
