# M27 Connector Framework Audit

**Branch:** `milestone/m7-security-engine`  
**Starting HEAD:** `8d938c3`  
**Date:** 2026-07-17  
**Operator authorization:** M27 only (governed connector framework)

---

## 1. Baseline (must preserve)

```text
production_certified = true (computed)
rollout mode = OFF
cloud fallback = disabled
Trading Guardian = UNCHANGED / UNENGAGED
M26 ops lifecycle canonical
```

---

## 2. Existing connector surfaces (do not duplicate)

| Surface | Location | Role |
|---------|----------|------|
| Universal account manager | `saathi/connectors/manager.py` | account-scoped execute; simulated unless adapter |
| Platform models | `saathi/connectors/platform/models.py` | ConnState, RiskClass, envelopes |
| Infrastructure registry | `saathi/infrastructure/connectors/` | Connector ABC, Manifest, health ranking |
| Drivers | `infrastructure/connectors/drivers/*` | telegram, github, youtube, fs, browser, n8n |
| ExecutionGateway | `saathi/execution/gateway.py` | ToolIntent → approval → handler |
| MCP governance | `saathi/mcp_governance/` | policy, redaction, inventory, timeouts |
| Browser governance | `saathi/browser/` | domain policy, redaction, production adapter |
| M26 ops | `saathi/inference/ops/` | rollout, incidents, readiness, events |

---

## 3. Duplication / gaps

| Issue | Notes |
|-------|-------|
| Multiple registries | connectors.manager vs infrastructure.registry vs platform.registry |
| Lifecycle names differ | ConnState vs Status vs M26 ServicePhase |
| Governance incomplete on direct manager.execute | may skip runtime_gate / reservation |
| No single HTTP governed adapter | ad-hoc httpx in places |
| Local shell risk | need allowlisted wrapper only |
| M26 rollout not wired to connectors | connectors ignore OFF/SHADOW/CANARY |

---

## 4. Unsafe patterns to avoid in M27

* Live account OAuth / real API keys  
* Cloud inference or paid SaaS enablement  
* Arbitrary shell  
* Second event bus / incident system  
* Bypassing ExecutionGateway for consequential actions  
* Storing secrets in code or evidence  

---

## 5. Reusable components for M27

* M26 `RolloutMode`, incidents, redaction style  
* M25 `runtime_gate` production_certified probe  
* `mcp_governance.redaction`  
* `browser.domain_policy` / evidence redaction  
* Platform `RiskClass` / approval thresholds (map, do not reimplement trading)  
* Infrastructure `Manifest` fields (extend, do not fork drivers)  

---

## 6. Environment limitations

* No live credentials in this milestone  
* Connectors validate **in process** with fakes/simulators  
* HTTP adapter uses injectable transport (tests use stubs)  
* Default host rollout remains **OFF**  

---

## 7. Bounded M27 implementation

```text
saathi/connectors/gov/     # canonical governed framework (new)
  models, policy, registry, runtime, auth, adapters
tests/test_m27_connector_framework.py
docs/M27_*.md
```

**In scope:** framework + HTTP/MCP/browser-reuse/local-tool adapters + tests.  
**Out of scope:** dozens of SaaS integrations, live Gmail/GitHub login, M28, Trading Guardian.

---

## 8. Non-goals

* M28  
* Enabling cloud inference  
* Adding API keys  
* Connecting live user accounts  
* Modifying Trading Guardian  
* Public production deploy  
