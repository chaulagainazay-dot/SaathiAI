# M28 Connector Migration Audit

**Branch:** `milestone/m7-security-engine`  
**Starting HEAD:** `0a25728`  
**Date:** 2026-07-17  
**Operator authorization:** M28 only (canonical connector migration + ExecutionGateway enforcement)

---

## 1. Baseline (must preserve)

```text
production_certified = true (computed)
inference rollout mode = OFF
connector rollout mode = OFF
cloud fallback = disabled
Trading Guardian = UNCHANGED / UNENGAGED
M25–M27 invariants intact
```

---

## 2. Mission (bounded)

Migrate production-capable connector execution onto:

```text
Caller → ToolIntent/ConnectorIntent → ExecutionGateway
  → connector governance (M27 runtime + M28 side-effect policy)
  → approved adapter
  → redacted result + evidence
```

Not in scope: live SaaS OAuth, connector marketplace, Trading Guardian, cloud enablement.

---

## 3. Surfaces inspected

| Surface | Location | Role |
|---------|----------|------|
| Governed framework | `saathi/connectors/gov/` | M27 canonical runtime + adapters |
| ExecutionGateway | `saathi/execution/gateway.py` + `universal.py` | Universal ToolIntent boundary |
| Legacy account manager | `saathi/connectors/manager.py` | Account-scoped execute (sim/live) |
| Platform engine | `saathi/connectors/platform/execution.py` | M15 substrate under gateway |
| Platform API/CLI | `platform/api.py`, `cli.py`, `integration.py` | Funnel to ExecutionEngine |
| Server API | `saathi/server.py` `/api/v1/connectors/execute` | Calls manager.execute |
| MCP governance | `saathi/mcp_governance/` | Policy authority (reused) |
| Browser | `saathi/browser/` | Domain policy (reused) |
| Infra drivers | `saathi/infrastructure/connectors/drivers/` | Product adapters |
| Computer agent | `saathi/computer_agent/*` | Uses ExecutionEngine |
| Gov CLI | `python -m saathi.connectors.gov` | Direct runtime exec |

---

## 4. Migration map (authoritative)

| Path | Caller | Capability | R/W | External SE | Governance path | Approval | Evidence | Decision | Compat | Tests | Residual risk |
|------|--------|------------|-----|-------------|-----------------|----------|----------|----------|--------|-------|---------------|
| `connectors/gov/runtime.py` | framework | all gov ops | mixed | yes if ACTIVE | self (canonical) | mutation tokens | m27/m28 evidence | **MIGRATE** (wire to EG) | N/A | m27+m28 | low |
| `execution/gateway.py` + `universal.py` | all families | ToolIntent | mixed | via handler | universal boundary | L3/L4 + store | execution store | **MIGRATE** (connector handler) | keep API | m17.22+m28 | low |
| `connectors/manager.py:execute` | server API, catalog tests | email/social/… | mut | sim or live adapter | was direct | none | event bus | **WRAP** | shim → gateway | connector_layer + m28 | med if live adapter |
| `server.py connectors_execute` | HTTP API | manager caps | mut | via manager | token-gated only | none | via manager | **WRAP** | via manager | m28 API contract | med |
| `platform/execution.py` | computer_agent, API, CLI | platform tools | mixed | adapter | gateway → substrate | risk-bound | store events | **WRAP** | fail-closed if gateway missing | m15/m17 + m28 | low |
| `platform/api.py` / `cli.py` / `integration.py` | ops/UI | platform tools | mixed | via engine | already engine | engine | engine | **RETAIN** (already funnel) | none | m15/m16 | low |
| `gov/__main__.py exec` | operators | gov ops | mixed | via runtime | direct runtime | runtime | m27 | **WRAP** | CLI → gateway bridge | m28 | low |
| `gov/adapters/*` | runtime only | adapter ops | mixed | yes | runtime-only | runtime | redacted | **RETAIN** (internals) | allowlist | m27 | low if allowlisted |
| `infrastructure/connectors/drivers/*` | product registry | telegram/github/… | mixed | possible | platform registry | platform | sparse | **OUT_OF_SCOPE** | keep drivers | deferred M29+ | med until migrated |
| `connectors/adapters/telegram.py` | manager register | messaging | mut | yes if live | manager | none | bus | **WRAP**/block live without gov | deprecation | m28 | med |
| `connectors/accounts.py` / `catalog.py` | UI/metadata | read | RO | no | n/a | n/a | n/a | **RETAIN_READ_ONLY** | none | connector_layer | low |
| `platform/store.py` credentials resolve | engine | secret ref | RO local | no values in evidence | engine | n/a | redacted | **RETAIN_READ_ONLY** | none | m15 | low |
| MCP governance modules | gov.mcp adapter | policy/status | RO-ish | no live MCP in M28 | mcp_governance | existing | redacted | **RETAIN** | reuse | m17.25+m27 | low |
| Browser governance | gov.browser + M17.23 | navigate | mut | browser | EG + browser | approval | redacted | **RETAIN** | existing EG path | m17.23 | low |
| Trading / exchange paths | none registered | trade | mut | financial | forbidden | n/a | n/a | **BLOCK** | reject register/exec | m28 | none if blocked |
| Payments charge (catalog) | manager | payments.charge | mut | financial | manager sim | none | bus | **BLOCK** | fail closed | m28 | none |
| Tests / docs | pytest | any | mixed | no prod | test fixtures | fixtures | tmp | **TEST_ONLY** | allowlist | suite | low |
| Direct `requests`/`httpx` in saathi (non-gov) | various | HTTP | mixed | possible | ad-hoc | varies | varies | **OUT_OF_SCOPE** except connectors tree | bypass scan scoped | debt | med residual |

### Decision legend

| Decision | Meaning |
|----------|---------|
| MIGRATE | Production path must reach ExecutionGateway + gov runtime |
| WRAP | Public API retained; implementation routes to canonical path + deprecation |
| RETAIN_READ_ONLY | Safe local/metadata reads; documented |
| DEPRECATE | Marked for removal after callers migrate |
| TEST_ONLY | Allowed only under tests |
| BLOCK | Fail closed (trading/financial/account-change) |
| OUT_OF_SCOPE | Deferred; not production-capable M28 slice or already governed elsewhere |

---

## 5. Selected bounded M28 scope

1. Canonical **ExecutionGateway ↔ GovernedConnectorRuntime** bridge.  
2. **Default connector family handler** on UniversalBoundary.  
3. **Wrap** `connectors.manager.execute` (server + catalog callers).  
4. **Fail-closed** platform ExecutionEngine when gateway is unavailable for executable work.  
5. **Side-effect classification** with fail-closed undeclared/financial/trading/account.  
6. **Bypass detection** for production connector bypasses (count = 0).  
7. **Migration ledger** + deprecation evidence.  
8. Deterministic **M28 tests**.

### Explicitly deferred

* Full migration of every infrastructure driver to gov manifests.  
* Live OAuth / SaaS account connect.  
* Second marketplace registry.  
* Trading Guardian engagement.  
* Blanket HTTP client ban outside connectors tree (tracked as debt).

---

## 6. Reused systems (no second copies)

| System | Reuse |
|--------|-------|
| ExecutionGateway / UniversalBoundary | Single authority; extend handler only |
| M27 `saathi.connectors.gov` | Runtime, policy, adapters, redaction |
| M26 rollout modes + incidents | OFF/SHADOW/CANARY/ACTIVE/DRAINING |
| M25 runtime_gate / cert evidence | production_certified probe |
| Platform approval store | Exact-action binding for platform tools |
| mcp_governance / browser policy | Via gov adapters |

---

## 7. Unsafe patterns (do not introduce)

* Live credentials / OAuth in repo  
* Cloud inference enablement  
* Process-local `is_admin` / `skip_approval` production authority  
* Direct adapter execute from callers  
* Caller-selected adapter implementation  
* Caller-overridden side-effect class or rollout mode  
* Temporary dual-transport fallback after governance failure  

---

## 8. Implementation gate

Implementation begins only after this audit is committed as the migration map.

```text
audit = COMPLETE
scope = BOUNDED
ready_for_implementation = true
```
