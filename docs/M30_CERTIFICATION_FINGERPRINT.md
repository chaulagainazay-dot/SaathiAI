# M30 — Certification Fingerprint

**Module:** `saathi.connectors.conformance.fingerprint`

## Inputs

* Connector manifest (identity/runtime ceilings; timestamps excluded)
* Adapter implementations (`gov/adapters/*`)
* Governed runtime, gateway bridge, policy, side-effects, redaction, auth
* Trust / capability / validation / deps / builtins
* Conformance specification + assessor + sandbox + eligibility
* Spec version `m30.conformance.v1`

## Algorithm

SHA-256 over canonical JSON (`sort_keys`, stable separators) of the material
object. Same inputs ⇒ same fingerprint.

## Drift

If stored fingerprint ≠ current fingerprint for a CERTIFIED* record → **STALE**.

## False-positive controls

* Documentation under `docs/` is **not** fingerprinted.
* Manifest timestamps (`created_at`, `updated_at`, …) are stripped.
