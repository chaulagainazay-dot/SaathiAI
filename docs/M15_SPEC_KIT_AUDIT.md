# M15 Spec Kit Integration Audit

## Decision: native wrapper, not a vendored repo
The user pasted `github.com/garrytan/gstack` to "wire into claude". Investigated:
**gstack is a Next.js/Convex/Clerk SaaS starter, not GitHub Spec Kit.** Dragging
it into this Python monorepo would violate Constitution Art. VI (reuse over
rebuild, no wholesale vendoring). Implemented Spec Kit's *discipline* natively
and offline instead.

## What shipped
- `.specify/memory/constitution.md` — SaathiOS Delivery Constitution v1.0 (8 articles).
- `.specify/presets/saathios/preset.json` — pipeline + gates + requirement-id pattern.
- `saathi/specs/traceability.py` — validator + convergence gate (Art. VII).
- `saathi/specs/cli.py` — `python -m saathi.specs.cli version|health|init|validate|converge`.
- `specs/m15-universal-connectors/` — spec.md, plan.md, tasks.md, traceability.json (19 reqs), convergence.md.

## Pipeline
constitution → spec → clarify → plan → tasks → consistency → implement →
validate → converge → report. The convergence gate fails on any requirement
whose artifact file or test file is missing, or whose id is malformed
(`^M\d+-[A-Z]+-\d{3}$`).

## M10 orchestration linkage
`tasks.md` encodes a dependency-ordered task graph (T1..T12). An M10 orchestrator
derives its agent strategy from it: critical path T1→T4→T6, parallel leaves
T2/T3/T11, fan-out T7–T10 from T6/T5, T12 join/gate.

## Result
`converge` → **CONVERGED**, 19/19 mapped + tested.
