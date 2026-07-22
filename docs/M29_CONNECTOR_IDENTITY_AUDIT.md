# M29 — Connector Identity Audit

**Milestone:** M29  
**Branch:** `milestone/m7-security-engine`  
**Starting HEAD:** `28e45e6`  
**Scope:** Evidence-first audit of connector identity before canonical manifest + trust registry.

---

## Baseline architectures (canonical — do not duplicate)

| Milestone | Role |
|-----------|------|
| M25 | Production certification package + runtime gate |
| M26 | Inference ops, readiness, rollout, resource guardian, incidents |
| M27 | Governed connector framework (`saathi.connectors.gov`) |
| M28 | ExecutionGateway enforcement, side-effect policy, bypass elimination |

M29 **defines what a connector is**. It reuses runtime, gate, rollout, approval, evidence, event bus, incidents, ExecutionGateway, and adapters.

---

## Existing connector metadata (pre-M29)

### `saathi.connectors.gov.models.ConnectorManifest` (M27)

| Field | Present | Notes |
|-------|---------|-------|
| connector_id | yes | |
| version | yes | Often short `"1"`, not semver |
| kind | yes | http/mcp/browser/local_tool/… |
| capabilities | yes | **Overloaded** as operation names |
| supported_operations | yes | Often duplicate of capabilities |
| auth_mode / auth_env_names | yes | Names only |
| timeout / retries / rate limit | yes | |
| evidence_policy | yes | redacted \| metadata_only |
| rollout_compatible | yes | |
| cloud / trading | yes | trading forbidden |
| description | yes | |
| display_name / owner | **no** | |
| trust_level | **no** | |
| capability_classes (READ/WRITE/…) | **no** | |
| side_effect_classes (declared) | **no** | Heuristic in M28 only |
| dependencies | **no** | |
| health / readiness policy | **no** | Ops exist in M26, not on connector |
| deprecation / replacement | **no** | |
| secret_references | **no** | only auth_env_names |
| incident_policy | **no** | hard-coded M26 bridge |

### Other registries (not identity authority)

| Surface | Role | Gap |
|---------|------|-----|
| `connectors/gov/registry.py` | Lifecycle + adapter bind | Overwrite on re-register; weak schema |
| `connectors/platform/registry.py` | Product connector platform | Parallel catalog; not ExecutionGateway path |
| `connectors/catalog.py` / manager | Account capabilities | Simulation / deprecation (M28) |
| `infrastructure/connectors/drivers` | Product drivers | Not on gov manifests (M28 residual) |

---

## Duplicated identity logic

1. **Capabilities vs operations** — same strings used for both; no capability class model.
2. **Kind vs adapter type** — `ConnectorKind` only; no stable adapter_type field.
3. **Side effects** — M28 classifies at execute time; not declared on identity.
4. **Built-in specs** — constructed inline in `register_builtin_adapters` (runtime-shaped identity).
5. **Platform vs gov catalogs** — two worlds; only gov is production path after M28.

---

## Missing schema (pre-M29)

* Semantic version discipline  
* Trust level  
* Explicit capability classes vs operations  
* Declared side-effect classes  
* Required approvals list  
* Secret references (non-value)  
* Dependency graph  
* Health / readiness metadata on connector  
* Incident policy declaration  
* Deprecation + replacement (no silent swap)  
* Supported environments  
* Owner / display_name  

---

## Missing trust model

No connector trust levels. Approval and rollout floors were operation/side-effect driven only. Callers could not raise trust (good) but the registry also could not express trust ceilings for future EXTERNAL_SERVICE / FINANCIAL connectors.

---

## Manifest inconsistencies

* Builtin manifests used `version="1"` (implicit).  
* M27 tests pass operation names as `capabilities`.  
* Empty re-register overwrote identity without history.  
* No fail-closed schema gate at `register()`.  

---

## Future SaaS readiness (not implemented in M29)

| Future connector | Expected trust | Capabilities | Notes |
|------------------|----------------|--------------|-------|
| Gmail / Calendar | EXTERNAL_SERVICE | HTTP, COMMUNICATE, ACCOUNT | OAuth later; secret refs only |
| GitHub | EXTERNAL_SERVICE | HTTP, READ, WRITE | |
| Slack / Discord | EXTERNAL_SERVICE | COMMUNICATE | |
| Stripe | PRIVILEGED | FINANCIAL, ACCOUNT | ACTIVE ineligible until reclass |
| Binance / trading | PROHIBITED | — | Always fail closed |

M29 ships **identity only** — no live accounts, OAuth, or API keys.

---

## Migration plan

1. Extend `ConnectorManifest` with M29 fields (defaults preserve M27/M28).  
2. Static builtin manifests in `saathi.connectors.registry.builtins`.  
3. Registry: duplicate fail, resolve/inspect/deprecate, version history, deps.  
4. Validate at register; trust/capability ceilings.  
5. Runtime + gateway resolve identity only via registry.  
6. `python -m saathi.connectors.registry docs` for catalog generation.  
7. Defer: full platform/infrastructure driver migration; live SaaS.

---

## Invariants retained

```text
production_certified = true (computed)
connector rollout = OFF (default)
inference rollout = OFF
connector bypasses = 0
cloud fallback = disabled
Trading Guardian = UNCHANGED / UNENGAGED
```
