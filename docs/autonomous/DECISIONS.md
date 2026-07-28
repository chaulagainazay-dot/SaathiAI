# Autonomous Architecture Decisions

## ADR-IELTS-001 — SaathiOS platform owns the bounded IELTS module

- Decision: implement IELTSAlert under `saathi.platform` and the existing SaathiOS
  shell, with the platform database, context, RBAC, notifications, evidence
  references, and audit as authorities.
- Alternatives: extend legacy unscoped helpers; import the separate product repo;
  create a parallel service.
- Evidence: M64 makes ModuleRegistry/browser discovery authoritative; legacy IELTS
  helpers use process memory or direct model calls and lack organization/workspace
  isolation; the separate `pielts` repo is out of this repository's change scope.
- Consequences: a small canonical module service and schema are added in place;
  legacy helpers remain compatibility-only and non-authoritative.

## ADR-IELTS-002 — deterministic local feedback is the operational default

- Decision: use a repeatable, criteria-level local practice estimator. Every result
  is labelled `local heuristic result` / `practice estimate` and includes limitations.
  Speaking pronunciation is `not_assessed` without audio analysis.
- Alternatives: reuse legacy provider calls; report scoring unavailable.
- Evidence: no configured provider is required, paid calls are prohibited, and a
  legacy speaking fallback returns an unsupported numeric estimate.
- Consequences: no secret or network dependency; no official score claim; provider
  capability remains false until a separately governed adapter is configured.

## ADR-IELTS-003 — evidence references, not artifact blobs

- Decision: store bounded artifact/evidence references and metadata only.
- Alternatives: store audio/image payloads in SQLite.
- Evidence: platform evidence and audit services already exist and the product
  boundary prohibits raw media in relational fields.
- Consequences: local workflows are complete for metadata and text submissions;
  artifact upload/storage remains a centralized platform concern.

## ADR-IELTS-004 — manual verification is not payment processing

- Decision: payment records capture declared amount/currency/method, transaction and
  evidence references, and a human-only audited review state. No settlement occurs.
- Alternatives: gateway integration or automatic approval.
- Evidence: no provider registration or production authority exists.
- Consequences: owner/admin review is required; self-approval is denied; records are
  explicitly labelled manual verification.

## ADR-IELTS-005 — activate only through the backend module authority

- Decision: enable IELTSAlert in the authenticated ModuleRegistry only after the
  bounded API, permission, tenant-isolation, UI, and browser contracts pass. The
  frontend descriptor remains a non-authoritative metadata mirror.
- Alternatives: keep the module as a placeholder; make frontend routing authoritative.
- Evidence: M64 established backend discovery as browser authority, and M67 verifies
  the complete minimum operational contract.
- Consequences: IELTSAlert is actionable in navigation, dashboard, and command search
  only when returned by backend discovery; registration itself grants no permission.
