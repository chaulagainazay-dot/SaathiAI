# M39.5 — Monitoring & Incident Response

**Status:** MONITORING_INCIDENT_SURFACE_COMPLETE_OFFLINE.
**Series:** PRE-M40 offline readiness (`docs/PRE_M40_OFFLINE_READINESS_PLAN.md`).
**Module:** `saathi/credentials/m39_5.py`.
**Tests:** `tests/test_m39_5_monitoring_incident.py` — 17 passed.
**Evidence:** `docs/evidence/m39_5/` (deterministic; leak-clean).

## Purpose

Define the observability and incident surface for the M39 external-provider
validation surface using local/synthetic signals only — no live transport, no
secret ever accepted in an event.

## Components

- **Audit-event contracts** — 8 M39 event types, each requiring `event_type`,
  `session_id`, `privacy_safe`, `contains_secret_values`, plus type-specific fields.
- **Event validator** — fail-closed; rejects unknown types, missing fields,
  `privacy_safe != true`, `contains_secret_values != false`, any forbidden field
  (`secret`/`token`/`api_key`/`authorization`/`password`/`value`), and any content
  that fails a deep leak scan.
- **Alert definitions** — `ALT-1`…`ALT-9`: stuck run, budget exhaustion, auth
  denial, secret-resolution failure, lease leak, leak finding, kill-switch trip,
  provider failure rate, canary-escalation attempt — with severities SEV1–SEV3.
- **Deterministic alert detector** — evaluates definitions over a local synthetic
  signals dict; returns fired alerts and highest severity.
- **Metrics contract** — 8 counters/gauges; labels may not carry secret values.
- **Incident severity definitions** + **incident runbook** (`INC-1`…`INC-6`) +
  **recovery runbook** (`REC-1`…`REC-6`), including kill-switch trip, leak scan,
  external revocation, reconcile-without-secret-reopen, and resume-only-with-
  operator-authorization.

## Authority state (unchanged)

CANARY / ACTIVE / rollout / production / write = **NOT GRANTED**. Trading Guardian
**UNENGAGED**. Any observed canary-grant attempt is a SEV1 alert.

## Reproduce

```bash
python -m pytest tests/test_m39_5_monitoring_incident.py -q
python -m saathi.credentials.cli m39-5-alert-definitions
python -m saathi.credentials.cli m39-5-incident-runbook
python -m saathi.credentials.cli m39-5-emit-evidence   # deterministic
```
