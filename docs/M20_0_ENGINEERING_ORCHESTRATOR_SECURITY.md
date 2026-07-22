# M20.0 — Engineering Orchestrator Security

## Threat model (pilot)

| Threat | Control |
|--------|---------|
| Uncontrolled coding agent | Disabled by default; max 1 session; readiness gate |
| Arbitrary repo write | Repository allowlist; cwd confinement; path traversal deny |
| Arbitrary shell | Orchestrator never runs free-form shell; validation catalog only |
| Arbitrary MCP | Explicitly denied in security module |
| Secret leakage | `saathi.repair.secrets_scan` on prompts/context/files/handoff |
| Prompt injection | Knowledge safety wrap; injection lines stripped; cannot authorize launch |
| Permission expansion via prompt | Prompt builder flags; settings remain sole authority |
| Force-push / merge / deploy | Hard-disabled settings; stop policy terminate |
| Trading crossover | Isolation report + import scan + permission denials |
| Parallel writers | Readiness + max sessions |
| Credential pass-through | Child env stripped of API keys |

## Trading Guardian isolation

Engineering Orchestrator:

- cannot execute trades  
- cannot access exchange credentials  
- cannot authorize trading via engineering capabilities  
- cannot enable trading via prompt text  
- does not modify kill switches  
- does not hold trading secrets in InsForge or knowledge paths  

Evidence: `saathi/engineering/security.py` + tests in `tests/test_m20_0_engineering_orchestrator.py`.

## Permission model

| Capability | Gate |
|------------|------|
| inspect backlog / repo | Always (read-only) |
| generate plan | Orchestrator enabled recommended |
| launch read-only agent | `SAATHI_ENG_ORCH_ENABLED` + `LAUNCH` |
| launch write agent | + `WRITES` |
| create commit | `COMMITS` |
| push branch | `PUSHES` (never force) |
| trade / merge / deploy | **Forbidden always** |

No universal admin bypass.

## Stop policy (high severity → terminate)

Secret detection, force-push, merge, deploy, live trading, destructive action, critical security validation failure.

## Disable procedure

```bash
unset SAATHI_ENG_ORCH_ENABLED SAATHI_ENG_ORCH_LAUNCH \
      SAATHI_ENG_ORCH_WRITES SAATHI_ENG_ORCH_COMMITS SAATHI_ENG_ORCH_PUSHES
python -m saathi.engineering stop <session_id> --force   # if needed
```

## Rollback

```bash
git revert <m20.0-commit-sha>
# remove data/engineering/ session state if desired
rm -rf data/engineering/
```

Trading Guardian and Mission Engine paths are untouched by package removal.
