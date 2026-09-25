# SaathiOS Agent Instructions

## Mission

SaathiOS is Ajay Chaulagain's local-first AI operating system. Improve the existing architecture through bounded, evidence-backed milestones. Reuse existing systems rather than creating parallel implementations.

## Authoritative project documents

Before planning meaningful work, inspect the relevant parts of:

- Brain.md
- Business.md
- Writing and Speaking Style.md
- docs/AUTONOMOUS_ROADMAP.md
- TECHNICAL_DEBT.md
- CAPABILITY_MATRIX.md
- HANDOFF.md, when present
- current Git status and recent commits

Use the repository's actual paths when these files are located elsewhere.

## Default operating mode

1. Begin with a read-only intake audit.
2. Identify the current milestone and repository state.
3. Select one bounded, evidence-supported slice.
4. Record the starting commit.
5. Reuse existing architecture.
6. Implement the smallest complete change.
7. Add deterministic regression tests.
8. Run focused tests first.
9. Run the appropriate full validation suite.
10. Update relevant project documentation.
11. Produce a concise final report with evidence and remaining blockers.

## Safety and permissions

Do not perform any of these without explicit user authorization:

- push commits;
- merge branches;
- open or merge pull requests;
- deploy services;
- modify DNS;
- rotate or expose credentials;
- change production databases;
- delete data;
- install broad system dependencies;
- access unrelated directories;
- execute live financial trades.

Never reveal secrets, tokens, cookies, credentials, or private keys.

Prefer a dedicated branch or worktree for substantial changes.

Do not mark work complete merely because code was written. Completion requires passing tests, checks, and repository-specific evidence.

## Architecture discipline

- Do not build duplicate orchestration, memory, event bus, mission, alerting, monitoring, approval, or execution systems.
- Inspect existing implementations before adding new modules.
- Keep authoritative state clearly defined.
- Prefer adapters and stable interfaces for external repositories.
- Keep third-party code isolated where licensing or replacement risk exists.
- Maintain rollback compatibility.
- Preserve backward compatibility unless an approved milestone explicitly changes it.

## Documentation discipline

When architecture, capability, business behavior, or communication style changes, update the applicable documents:

- Brain.md
- Business.md
- Writing and Speaking Style.md
- roadmap and milestone records
- capability matrix
- technical debt register
- architecture decision records

Do not make cosmetic documentation changes when no meaningful decision changed.

## Verification requirements

For code changes, perform as applicable:

- targeted tests;
- full regression tests;
- formatting and lint checks;
- type checks;
- build verification;
- secret scan;
- dependency/security checks;
- browser verification;
- git diff --check.

Report commands and results accurately. Never claim a check passed if it was not executed.

## Trading Guardian

Any SaathiOS roadmap, architecture, implementation, or repair affecting trading must preserve the Trading Guardian.

Required controls:

- advisory mode by default;
- approval-required and tightly bounded limited-autonomous modes;
- paper-trading and backtesting gates;
- deterministic position sizing;
- mandatory stop-loss and governed take-profit;
- daily and weekly loss limits;
- leverage disabled by default;
- exchange credentials without withdrawal permission;
- stale-data and reconciliation checks;
- circuit breakers;
- emergency kill switch;
- immutable audit trail;
- explicit human approval before live activation.

Never allow a model or tool to silently weaken these controls.

## Engineering harness (ECC)

The ECC plugin (`ecc@ecc`, project scope) is the development harness for this
repository. It is a development-plane tool only.

- ECC holds no trading, risk, approval, execution, broker, or ledger authority.
  Its agents produce suggestions, nothing more.
- Architecture documents, ADRs, and code override ECC memory, ECC rules, and
  generic ECC patterns whenever they disagree.
- SaathiOS mission, milestone, evidence, and certification discipline stay
  canonical. ECC review, TDD, build-fix, and security passes are additional
  inputs, never the gate.
- Before changing a subsystem, state its canonical implementation, authority
  owner, existing tests, relevant ADRs, milestone evidence, and regression risk.
- Give every proposed architectural change one verdict: KEEP, ADAPT, INTEGRATE,
  REPLACE, COMBINE, DEFER, or REJECT. Newer and larger are not arguments.
- Do not weaken a linter, formatter, or test config to make a check pass. Fix
  the code.
- Trading-plane work additionally requires authority, risk, approval,
  ExecutionGateway, ledger, reconciliation, and no-live-authority audits.

The harness runs a **curated profile**: the `ecc@ecc` plugin is installed but
disabled and serves only as the pinned vendor source; 47 selected components are
synced project-locally by `scripts/ecc_profile_sync.sh` from
`.claude/ecc-profile.json`. Never upgrade ECC automatically — follow the update
procedure in the policy document.

Full policy, conflict resolution, security posture, resource budget, update
procedure, and rollback: `docs/engineering/ECC_INTEGRATION.md`.

## Final report format

Include:

1. overall result;
2. milestone or task completed;
3. starting and ending Git state;
4. files changed;
5. architecture reused;
6. tests and checks run;
7. unresolved blockers;
8. documentation updated;
9. deployment, push, and production-change status.
