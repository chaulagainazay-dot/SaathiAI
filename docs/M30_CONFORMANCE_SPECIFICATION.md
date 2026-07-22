# M30 — Connector Conformance Specification

**Version:** `m30.conformance.v1`  
**Package:** `saathi/connectors/conformance/`

## Purpose

Prove that a registered connector **behaves** according to its M29 manifest and
M25–M29 governance guarantees. A manifest declaration alone is not sufficient.

## Path

```text
registered connector
→ static manifest validation
→ adapter contract validation
→ sandbox execution
→ policy and approval checks
→ failure-mode validation
→ evidence and redaction checks
→ certification decision
→ readiness eligibility
```

## Categories

MANIFEST, IDENTITY, CAPABILITIES, TRUST, POLICY, APPROVAL, ROLLOUT,
ADAPTER_CONTRACT, INPUT_VALIDATION, OUTPUT_VALIDATION, TIMEOUT, RETRY,
RATE_LIMIT, IDEMPOTENCY, HEALTH, READINESS, DEPENDENCIES, EVIDENCE,
REDACTION, INCIDENTS, FAILURE_RECOVERY, DIRECT_ACCESS, SIDE_EFFECT_SAFETY,
RESOURCE_SAFETY.

## Check record fields

| Field | Description |
|-------|-------------|
| check_id | Stable id |
| connector_id | Target connector |
| category | From catalog |
| severity | CRITICAL / MANDATORY / LIMITATION / INFORMATIONAL |
| required | Mandatory failures cannot be hidden |
| status | PASS / FAIL / BLOCKED / SKIPPED / NOT_APPLICABLE |
| safe_summary | Privacy-safe text |
| evidence_refs | Optional refs |
| failure_code | Machine code on failure |
| duration_ms / step_count | Deterministic cost |

## CLI

```bash
python -m saathi.connectors.conformance assess gov.http
python -m saathi.connectors.conformance assess-all
python -m saathi.connectors.conformance status
python -m saathi.connectors.conformance inspect gov.http
python -m saathi.connectors.conformance verify
python -m saathi.connectors.conformance drift
python -m saathi.connectors.conformance revoke gov.http --reason <safe-reason>
python -m saathi.connectors.conformance spec
```

Connectors resolve only through the M29 registry. Import paths are rejected.

## Dump

```bash
python -m saathi.connectors.conformance spec
```
