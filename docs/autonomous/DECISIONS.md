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

## ADR-IELTS-006 — unavailable provider is an explicit adapter state

- Decision: compose the local heuristic through `SafeFallbackScorer` with an explicit
  unavailable provider adapter when no governed scorer is configured.
- Alternatives: call legacy provider helpers; invoke the local scorer directly without
  provider-state provenance; return no feedback.
- Evidence: no safe configured provider exists and paid/network provider use is not
  authorized.
- Consequences: provider failure details stay private, local fallback is repeatable
  and visibly labelled, and module capability remains provider-assisted `false`.

## ADR-IELTS-007 — remediate runtime dependencies without framework migration

- Decision: move Next.js to the compatible 15.5.22 patch line and override its
  vulnerable production PostCSS/Sharp transitive versions; update Playwright and
  local PostCSS for the test/build toolchain.
- Alternatives: accept production high-severity advisories; perform an unrelated
  Next/ESLint major migration.
- Evidence: production `npm audit` initially reported three high vulnerabilities;
  the bounded update yields zero production vulnerabilities and passes all frontend,
  build, and browser gates.
- Consequences: runtime audit is clean. ESLint-only minimatch advisories remain
  documented until a coordinated major toolchain upgrade.

## ADR-MISSION-001 — compose mission control over existing platform authorities

- Decision: keep `missions` in `PlatformStore` authoritative, add additive
  mission-runtime tables and a tenant-scoped service, and reserve all external tool
  dispatch for `PlatformAgentRuntime` through the sole `ExecutionGateway`.
- Alternatives: extend the legacy M10 executor directly; create another mission
  database, queue daemon, identity layer, or execution engine.
- Evidence: M17 already proves graph execution concepts, M20 provides engineering
  checkpoint semantics, M52 makes `PlatformAgentRuntime` canonical, and the platform
  store/context/RBAC/audit services already own durable tenant state and authority.
- Consequences: M69 adds no tool execution path. M70 may schedule and coordinate tasks
  but can dispatch them only through the canonical runtime/gateway and cannot infer or
  bypass approval.

## ADR-MISSION-002 — persist an explicit hierarchy and immutable evidence trail

- Decision: model Goal → Phase → Milestone → Task → Subtask as bounded nodes, task
  dependencies as a validated DAG, and evidence/decisions/checkpoints/reviews/
  certifications as append-only mission artifacts.
- Alternatives: store an opaque plan JSON blob; infer progress from logs; overwrite
  checkpoints.
- Evidence: restart recovery requires deterministic task identity, explicit
  transitions, dependency status, budget counters, and a snapshot hash.
- Consequences: plan replacement is allowed only before any task attempt and clears
  stale plan artifacts atomically. Completion is gated by passing named evidence and
  independent review where configured.

## ADR-MISSION-003 — role agents delegate; they never grant or execute

- Decision: represent Planner, Architect, Implementer, Reviewer, Test, Browser,
  Documentation, and Certification agents as a fixed orchestration-role directory.
  A role may submit one declared task only to `PlatformAgentRuntime.execute_context`
  or resume an existing platform execution through the canonical runtime.
- Alternatives: give every role its own executor, connector client, credential set,
  or implicit permission map.
- Evidence: PlatformAgentRuntime already owns identity/binding/session validation,
  approvals, idempotency and runtime state; ExecutionGateway is the sole registered
  tool boundary.
- Consequences: agent selection grants nothing. Runtime binding policy and RBAC can
  deny any role task, approval requirements remain human-controlled, and no
  mission-runtime module imports or invokes ExecutionGateway.

## ADR-MISSION-004 — retry only confirmed failure; never replay uncertainty

- Decision: retry only a small allowlist of transient error codes paired with
  `FAILURE_CONFIRMED`, within each task's retry ceiling and mission resource budget.
  Approval waits resume the original platform execution. Recorded dispatch with
  unknown outcome is blocked for review and never replayed automatically.
- Alternatives: retry every exception; create a fresh execution after approval;
  assume interrupted dispatch failed.
- Evidence: M52 recovery explicitly classifies recorded dispatch as requiring manual
  review, while the gateway's outcome contract distinguishes confirmed failure from
  unknown side effects.
- Consequences: exponential retry backoff is finite; unexpected errors fail closed;
  recovery needs fresh authenticated context and preserves the original idempotency
  and platform execution record.
