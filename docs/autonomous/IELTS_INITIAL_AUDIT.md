# IELTSAlert Initial Repository Audit

Baseline: `milestone/m61-backend-workflow-persistence` at
`e0632460a12d3401146c12a1e79eac950a29682e`.

## Findings and disposition

| Area | Evidence | Disposition |
|---|---|---|
| Module authority | `saathi/platform/module_registry.py`; M64 `m64.1` authenticated discovery | REUSE |
| Shell/navigation/dashboard/command palette | shared discovery context, Sidebar, Applications page, route boundary | EXTEND |
| Identity/tenancy/RBAC | `PlatformExecutionContext`, `PlatformPermission`, role maps, authenticated platform API | REUSE |
| Persistence | `PlatformStore`, single-host SQLite, idempotent milestone migrations | EXTEND |
| Projects/missions/approvals/runtime/gateway | centralized platform services already present | REUSE; IELTS must not duplicate |
| Notifications | M61 `notifications` table and `WorkflowService` | REUSE |
| Audit | centralized `audit_events` and `append_audit` | REUSE |
| Evidence | platform `Evidence`/`EvidenceStore` plus a legacy `from_pielts_essay` adapter | ADAPT references; do not persist blobs |
| Legacy writing estimator | `saathi/tools/writing_eval.py` has a deterministic heuristic but labels a precise band | ADAPT rubric ideas; replace labels/precision |
| Legacy speaking endpoints | `saathi/tools/ielts_endpoints.py` uses process sessions/direct provider call and fabricates `6.0` on failure | DEPRECATE as module authority |
| Legacy learning integration | `ingest_pielts_interaction` records product episodes without platform tenant context | MIGRATE later through a scoped adapter |
| Existing learner/curriculum code | generic coach/curriculum helpers and seed scripts | OUT_OF_SCOPE for canonical state |
| Availability provider | no governed live IELTS test-center provider found | MISSING; implement labelled deterministic fixture source |
| Payment verification | no IELTS-specific bounded manual workflow found | MISSING; implement human-reviewed state machine |
| Provider configuration | generic model/provider infrastructure exists, but no safe configured IELTS scoring contract is evidenced | MISSING; local fallback only |
| Firebase/Gemini references | legacy scripts/product references; no authority to mutate production resources or call paid providers | EXTERNAL / OUT_OF_SCOPE |
| Separate product repository | roadmap and graph index reference `/Users/macbookpro/Saathi/apps/pielts` | EXTERNAL; no filesystem changes or code fabrication |
| Protected design specification | untracked `docs/design-spec/` | OUT_OF_SCOPE and untouched |

## Architecture classification

- REUSE: platform context, RBAC, PlatformStore database, projects/missions,
  notifications, evidence references, audit, approvals, ModuleRegistry, shell,
  authenticated client, route guards.
- EXTEND: permission enum/role mapping, idempotent schema migration, module service,
  platform API, frontend routes/components, registry descriptor and tests.
- ADAPT: IELTS rubric vocabulary and existing evidence linkage concepts.
- MIGRATE: legacy product interactions only through a future explicit tenant-scoped
  import boundary.
- DEPRECATE: legacy process-memory/direct-provider IELTS endpoints as operational
  SaathiOS module authority.
- EXTERNAL: separate `pielts` repository, Firebase/Vercel deployments, external
  scoring and test-center providers.
- MISSING: canonical tenant-scoped IELTS state, safe scoring contract, alert source,
  manual verification workflow, integrated UI.
- OUT_OF_SCOPE: copyrighted question bank, production infrastructure, real payments,
  external sends, HCG POS, Travel, Finance, and Trading changes.

## M65 completion contract

- Canonical validated records and legal lifecycle transitions.
- Idempotent single-host schema in the platform database.
- Explicit IELTS permissions with no registration-as-grant behavior.
- Service enforces tenant/workspace scope, ownership, human review, bounded text and
  deterministic serialization.
- Focused domain/store/RBAC tests pass; diff and secret/safety checks are clean.

