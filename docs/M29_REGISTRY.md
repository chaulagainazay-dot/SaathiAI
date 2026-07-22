# M29 — Connector Registry

## Authority

One canonical registry: `saathi.connectors.gov.registry.ConnectorRegistry`.

Identity resolution is **only** by `connector_id` through the registry.

Never by:

* import path  
* filename  
* arbitrary unregistered string  

## Functions

| Method | Behavior |
|--------|----------|
| register | Validate + insert; **duplicate IDs fail** |
| unregister | Remove identity + adapter bind |
| validate | Schema + auth + deps → VALIDATED |
| list / list_ids | Deterministic listing |
| resolve | Fail closed if unknown |
| inspect | Public identity + trust floors + history |
| deprecate | Mark deprecated; optional replacement must exist |
| bind_adapter | Attach adapter after identity exists |
| validate_dependencies | Graph + cycle rejection |

### Version upgrades

`register(..., allow_upgrade=True)` requires **strictly greater** version and
records `version_history`. Silent replacement is forbidden.

### Persistence

```text
saathi.connectors.registry.persistence
  save_registry_snapshot / load_registry_snapshot
```

Snapshots store manifests only; adapters re-bound at bootstrap.

## CLI

```text
python -m saathi.connectors.registry docs
python -m saathi.connectors.registry docs --markdown --out docs/generated/connector_catalog.md
python -m saathi.connectors.registry list
python -m saathi.connectors.registry inspect gov.http
python -m saathi.connectors.registry bootstrap
python -m saathi.connectors.registry trust-matrix
```

## Fail closed

* Unknown connector → `UnknownConnectorError` / execute denied  
* Unregistered after unregister → cannot execute  
* PROHIBITED trust → denied  
* Deprecated → health-only; mutations denied  
