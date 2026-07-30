# M224–M231 — Read-Only Broker Connectivity Readiness and Credential Lifecycle Simulation

**Terminal verdict:** `READ_ONLY_BROKER_READINESS_CERTIFIED_WITH_LIMITATIONS`

**THE SYSTEM REMAINS PAPER AND SANDBOX ONLY.**  
**NO REAL BROKER CONNECTION WAS CREATED.**  
**NO REAL BROKER ACCOUNT WAS ACCESSED.**  
**NO REAL API CREDENTIALS WERE REQUESTED, ACCEPTED OR STORED.**  
**NO ORDER SUBMISSION OR ORDER CANCELLATION CAPABILITY EXISTS.**  
**LIVE TRADING IS NOT AUTHORIZED.**  
**READ-ONLY READINESS DOES NOT GRANT READ-ONLY PRODUCTION AUTHORITY.**  
**OWNER SIGN-OFF IS NOT CLAIMED UNLESS PROVIDED EXPLICITLY OUTSIDE AUTOMATION.**

---

## Architecture

Extends Trading Guardian / Broker Sandbox (M216–M223) with a **simulation-only** readiness layer:

| Module | Package | Responsibility |
|--------|---------|----------------|
| M224 | `adapter.py` | Read-only provider adapter **contract** (no real providers) |
| M225 | `policy.py` | Capability policy engine (allow simulation / deny write/real) |
| M226 | `credentials.py` + `secrets.py` | Simulated credential lifecycle + aggressive secret rejection |
| M227 | `scope.py` | Least-privilege scope validation |
| M228 | `connection.py` + `transport.py` | Connection state machine + transport guard |
| M229 | `snapshots.py` | Account snapshot read models + reconciliation (recommendations only) |
| M230 | `drills.py` | Expiry / revocation / incident drills (fail closed) |
| M231 | `control_center.py` + UI | Readiness Control Center `/trading/broker-readiness` |

**Module ownership:** `saathi/platform/tg/broker_readiness/`  
**Storage:** `data/platform/broker_readiness.db` (additive SQLite, transactional, restart-safe)  
**Reuses:** authority conventions, audit patterns, CLI (`paper-gov br-*`), platform API, TradingShell.

No parallel broker architecture. No alternative credential vault. No secondary approval system.

---

## M224 — Adapter Contract

- Operations classified: `PUBLIC_DATA`, `READ_ONLY_ACCOUNT`, `TRADING_WRITE`, `TRANSFER_WRITE`, `ADMINISTRATIVE_WRITE`, `FORBIDDEN`
- M224 exposes **only** simulated `PUBLIC_DATA` and `READ_ONLY_ACCOUNT`
- Required connection state: `SIMULATED_NOT_CONNECTED`
- **No real provider implementation**

## M225 — Capability Policy Engine

Decisions: `ALLOW_SIMULATION_ONLY`, `READINESS_APPROVED_NOT_CONNECTED`, `DENY_WRITE_SCOPE`, `DENY_EXCESS_PERMISSION`, `DENY_EXPIRED`, `DENY_REVOKED`, `DENY_UNAPPROVED`, `DENY_WRONG_ENVIRONMENT`, `DENY_REAL_CONNECTION`, `DENY_UNKNOWN_CAPABILITY`, `FAIL_CLOSED`.

Mixed read/write permission sets are rejected entirely (no silent downgrade).

## M226 — Simulated Credential Lifecycle

States: proposed → classified → scope-reviewed → security-reviewed → owner-reviewed → approved-for-simulation → activated-in-simulation → expiring → expired → rotation-required → rotated-in-simulation → suspended → revoked → destroyed → archived.

Invariant: `credential_usable_for_real_connection = false`  
Never stores: key, secret, token, password, cookie, recovery code, private certificate, seed phrase, raw authorization header.

## M227 — Scope Validation

Allowed read scopes vs forbidden write scopes. Outcomes: `LEAST_PRIVILEGE_CONFIRMED_IN_SIMULATION`, `EXCESS_SCOPE_REJECTED`, `SCOPE_MISMATCH_REJECTED`, `WRITE_PERMISSION_REJECTED`, `UNKNOWN_SCOPE_REJECTED`.

## M228 — Connection State Machine

`NOT_CONFIGURED` … `SIMULATED_CONNECTED_READ_ONLY` … `REAL_CONNECTION_FORBIDDEN`.  
Transport guard returns `REAL_PROVIDER_TRANSPORT_FORBIDDEN` for external domains. No sockets to real providers.

## M229 — Snapshots & Reconciliation

Normalized read models for balances, positions, history. Reconciliation classifications include `MATCHED`, `TIMING_DIFFERENCE`, `CRITICAL_RECONCILIATION_FAILURE`, etc. **Never mutates** provider fixtures or paper portfolio automatically.

## M230 — Drills

Deterministic suite covering expiry, revocation, scope expansion, outages, kill-switch, etc. Security-sensitive drills end fail closed; no auto-reconnect after security failure; no auto approval restoration.

## M231 — Control Center

UI: `/trading/broker-readiness`  
API: `/api/v1/platform/tg/broker-readiness/*`  
CLI: `python -m saathi.platform.tg.cli paper-gov br-*` (all emit `SIMULATION_ONLY=true`)

Labels: **SIMULATION ONLY · NO REAL CONNECTION · NO REAL CREDENTIAL · READ-ONLY ARCHITECTURE · NO ORDER SUBMISSION · LIVE TRADING NOT AUTHORIZED**

---

## Network Isolation

`TransportGuard` blocks forbidden provider domains and non-localhost hosts. Testable; records attempts. Real transport is structurally difficult.

## LLM Authority Boundary

LLM may explain/recommend only. LLM may **not** accept/store/approve credentials, activate sessions, connect, trade, or certify owner approval. All outputs advisory (`llm/refuse` endpoint).

## Security / Threat Model

Catalogued threats (secret leakage, excessive permissions, scope drift, real transport activation, LLM escalation, …) each with attack path, preventative/detective/recovery controls, residual limitation, evidence reference. See security scan output in evidence.

## Testing

- Focused: `tests/test_m224_m231_broker_readiness.py` (21 passed)
- Regression: M166–M231 TG suite (154 passed including M216)
- Frontend: 246 passed
- Production build: pass (`/trading/broker-readiness` included)
- Browser: `npm run cert:m231` → `READ_ONLY_BROKER_READINESS_BROWSER_CERT_PASSED_WITH_LIMITATIONS`

## Explicit Non-Actions

- No real API keys/secrets/OAuth
- No connection to Binance, Alpaca, IBKR, Zerodha, Bybit, Coinbase, Kraken, or any real provider
- No order submission/cancellation
- No production deployment
- No owner credentials requested
- M232 not started

## Limitations

- Single-host SQLite
- Simulated fixtures only
- Browser UI labels soft-limited behind sign-in gate without injected browser auth
- Owner human sign-off not claimed by automation
- Readiness ≠ production read-only authority

## Owner Sign-Off Status

`NOT_CLAIMED_AUTOMATED_ONLY`

## Next Recommended Milestone

**M232+** only after explicit owner planning — remain paper/sandbox only; do not auto-start real connectivity work.
