# SPEAKER_CONSENT_SPEC

## Machine-readable fields

Schema: `tools/voice-stt-data/schemas/consent.schema.json`

| Field | Notes |
| --- | --- |
| speaker_id | `spk_NNN` pseudonym only |
| consent_version | `saathi-product-speech-consent-v1` |
| commercial_model_training_allowed | **required true** for PRODUCT_CLEAN train |
| internal_research_allowed | optional |
| evaluation_allowed | optional |
| redistribution_allowed | **default false** |
| recorded_at | ISO-8601 |
| withdrawal_reference | how to request deletion |
| region_group | optional high-level only |

## Do not collect

- Full legal name
- Government ID
- Home address
- Financial account information
- Health information

unless independently necessary and explicitly authorized.

## Product rule

SaathiOS may train commercial product models **only if** `commercial_model_training_allowed = true`.

Human statement template: `tools/voice-stt-data/templates/consent_statement.md`

