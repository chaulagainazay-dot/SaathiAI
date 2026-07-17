# M29 — Canonical Connector Manifest Schema

## Principle

Every connector is a **deterministic manifest**. No runtime-generated identity.
No hidden behavior. Unregistered connectors cannot execute.

## Required fields

| Field | Type | Notes |
|-------|------|-------|
| connector_id | string | Stable id (`gov.http`, …) |
| version | string | Prefer semver `MAJOR.MINOR.PATCH` |
| display_name | string | Human label |
| description | string | |
| owner | string | Owning module/team |
| adapter_type | string | http \| mcp \| browser \| local_tool \| … |
| kind | enum | M27 `ConnectorKind` (compat) |
| trust_level | enum | See trust model |
| capability_classes | string[] | READ, WRITE, HTTP, … |
| supported_operations | string[] | get, health, … unique |
| side_effect_classes | string[] | READ_ONLY, EXTERNAL_MUTATION, … |
| required_approvals | string[] | Ops needing approval |
| auth_mode | enum | none \| env_var \| local_secure \| future_secret_manager |
| auth_env_names | string[] | Names only |
| secret_references | string[] | Names/refs only — never values |
| timeout_seconds | float | |
| max_retries / retry_policy | int / object | |
| rate_limit_per_minute | int | |
| evidence_policy | string | redacted \| metadata_only |
| incident_policy | string | m26 \| default |
| health_policy | object | startup_check, health_check |
| readiness_policy | object | readiness_check, requires_lifecycle |
| dependencies | string[] | Other connector_ids |
| rollout_compatible | string[] | Subset of OFF…DRAINING |
| supported_environments | string[] | local, dev, test, staging, production |
| cloud | bool | Default false |
| trading | bool | Must be false |
| deprecated / deprecated_at / replacement_connector | | No silent replacement |
| created_at / updated_at | ISO8601 | |

## Validation rejects

* Duplicate operations  
* Invalid rollout mode  
* Missing capability (after kind default)  
* Invalid trust  
* Capability exceeding trust ceiling  
* Invalid side-effect class  
* Undeclared auth when mode requires refs  
* Undeclared evidence  
* Undeclared incidents (`none` / empty)  
* Trading connectors  
* Self-replacement  

Validation is deterministic (`validate_manifest`).

## Module

```text
saathi/connectors/gov/models.py          # ConnectorManifest
saathi/connectors/registry/validation.py # validate_manifest
saathi/connectors/registry/builtins.py   # static gov.* manifests
```
