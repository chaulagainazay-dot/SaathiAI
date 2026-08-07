# M112–M120 — SaathiOS Tool, Skill, and Capability Ecosystem Runtime

Date: 2026-07-29

Terminal verdict: `SKILL_ECOSYSTEM_RUNTIME_COMPLETE_WITH_LIMITATIONS`

## Milestone map

| Milestone | Scope | Status |
| --- | --- | --- |
| M112 | Manifest, identity, package validation | Complete |
| M113 | Registry, discovery, lifecycle | Complete |
| M114 | Dependency, compatibility, version resolution | Complete |
| M115 | Permissions, approvals, tool bindings | Complete |
| M116 | Execution contract, workers, reconciliation | Complete |
| M117 | Health, quarantine, upgrade, rollback, recovery | Complete |
| M118 | Knowledge, conversation, domain skills, developer contract | Complete |
| M119 | Workspace, APIs, CLI | Complete |
| M120 | Browser cert + full regressions | Complete with limitations |

## Architecture

Central package: `saathi/platform/skills/`

- `SkillRuntime` — discovery, validate, register, enable/disable, execute, upgrade/rollback, quarantine
- Built-in packages under `saathi/platform/skills/packages/`
- Extends **ModuleRegistry** (metadata composition) and **ToolRegistry** (tool bindings)
- Execution: PlatformAgentRuntime → ExecutionGateway (optional Fleet lease path)
- Does **not** replace ToolRegistry, ModuleRegistry, gateway, approvals, or orchestration

## Domain skills (deterministic local)

- `saathi.repo_audit` (+ v1.1.0 upgrade package)
- `saathi.test_runner`
- `saathi.hcg_ops_review`
- `saathi.ielts_readiness`
- `saathi.documentation`
- `saathi.knowledge_search`
- `saathi.mutation_safe` (approval-required)
- `malicious_sample` (fail-closed validation fixture)

## Evidence

- Tests: `tests/test_m112_skill_runtime.py`
- Browser: `docs/evidence/m120/browser/M120_BROWSER_CERT.json`
- Summary: `docs/evidence/m120/M120_CERTIFICATION_SUMMARY.json`

## Limitations

- Local repository-controlled skills only
- Declarative / adapter-bound skills
- No public marketplace or remote install
- No third-party cryptographic publisher trust
- Single-host persistence
- Loopback workers only
- Production not authorized

## Production

Not authorized. No push/merge/deploy/credentials/Trading Guardian change.
