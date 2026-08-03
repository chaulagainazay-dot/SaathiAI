# Twenty bounded runtime owner decision template

Status: `UNDECIDED`; this template grants no authority.

Complete every field explicitly. Do not substitute agent identity, inferred
values, defaults, or a provider fallback.

| Field | Owner value |
| --- | --- |
| `runtime_option` |  |
| `provider_or_operator` |  |
| `host_architecture` |  |
| `host_region` |  |
| `cost_ceiling` |  |
| `currency` |  |
| `payment_responsibility` |  |
| `billing_alert_threshold` |  |
| `start_date` |  |
| `expiry_date` |  |
| `maximum_runtime_hours` |  |
| `shutdown_trigger` |  |
| `removal_deadline` |  |
| `data_restrictions` |  |
| `network_restrictions` |  |
| `webhook_option` |  |
| `public_exposure_exception` |  |
| `runtime_operator` |  |
| `security_reviewer` |  |
| `evidence_reviewer` |  |
| `cost_owner` |  |
| `image_digest_manifest` |  |
| `authentication_role` |  |
| `credential_expiry` |  |
| `backup_location` |  |
| `backup_retention` |  |
| `abort_conditions` |  |
| `approval_id` |  |
| `decision` |  |

Allowed `decision` values are `APPROVE_BOUNDED_RUNTIME_VALIDATION`,
`APPROVE_WITH_LIMITATIONS`, `DEFER`, and `REJECT`.

Any approval is time-limited, expires automatically at the earlier of the stated
expiry or maximum runtime, and applies only to the named host and synthetic data.
It grants no production authority, CRM write authority, provider fallback,
public exposure, email, OAuth, real-data use, or autonomous action. Teardown and
removal evidence is mandatory. Any scope expansion requires a new owner decision.

The owner must also acknowledge the separate CI repair, partial image/source
relationship, read-only Metadata limitation, webhook deferral/exception choice,
and the exact abort catalogue before M361 can enter.
