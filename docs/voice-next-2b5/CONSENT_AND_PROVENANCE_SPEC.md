# CONSENT_AND_PROVENANCE_SPEC

## Required fields (per speaker / session)

| Field | Storage |
| --- | --- |
| speaker_id (pseudonymous) | local JSON |
| consent_version | local JSON |
| commercial_training_ok | bool |
| product_redistribution_ok | bool |
| personal_adapter_ok | bool |
| recorded_at | ISO-8601 |
| dataset_version | string |
| revocation_policy_ref | string |
| notes | free text (no legal names) |

## Schema (local only)

```json
{
  "speaker_id": "spk_01",
  "consent_version": "saathi-voice-consent-v1",
  "commercial_training_ok": false,
  "product_redistribution_ok": false,
  "personal_adapter_ok": true,
  "recorded_at": "2026-08-07T00:00:00Z",
  "dataset_version": "product-clean-pilot-0",
  "revocation_policy_ref": "OWNER_DATA_POLICY.md#revocation"
}
```

## Rules

- No personal legal names in Git.
- Training scripts refuse PRODUCT_CLEAN bucket items without `commercial_training_ok=true` when speaker-sourced.
- Common Voice items use CC0 provenance, not individual consent forms.

