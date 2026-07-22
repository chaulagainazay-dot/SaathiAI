# M30 — Operations

## Assess connectors

```bash
python -m saathi.connectors.conformance assess-all
python -m saathi.connectors.conformance status
python -m saathi.connectors.conformance verify
python -m saathi.connectors.conformance drift
```

## Revoke

```bash
python -m saathi.connectors.conformance revoke gov.http --reason "safe reason"
```

Prior evidence is retained; state becomes REVOKED; ACTIVE blocked.

## Runtime eligibility

```text
caller → intent → ExecutionGateway → registry → rollout
→ connector certification → lifecycle/readiness
→ trust/capability → approval → adapter → redacted result
```

* OFF: no adapter execution (default)
* SHADOW: governance only; no external side effect
* CANARY/ACTIVE: require fresh CERTIFIED*
* Production certification still required for ACTIVE
* Host rollout remains OFF unless operator changes it (not done in M30)

## Evidence

```text
docs/evidence/m30/certification_registry.json
docs/evidence/m30/connectors/<connector_id>/
```
