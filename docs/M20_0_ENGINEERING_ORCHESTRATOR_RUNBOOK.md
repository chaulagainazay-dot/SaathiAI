# M20.0 — Engineering Orchestrator Operator Runbook

## Defaults

All orchestration is **off** until env flags are set. Inspect is always safe.

## Safe inspection

```bash
cd /path/to/SaathiAI
.venv/bin/python -m saathi.engineering status
.venv/bin/python -m saathi.engineering backlog
.venv/bin/python -m saathi.engineering readiness
.venv/bin/python -m saathi.engineering security
.venv/bin/python -m saathi.engineering handoff
```

## Harmless mock pilot (local)

```bash
export SAATHI_ENG_ORCH_ENABLED=1
export SAATHI_ENG_ORCH_LAUNCH=1
# leave WRITES/COMMITS/PUSHES unset
.venv/bin/python -m saathi.engineering pilot
```

## Enable write supervision (explicit only)

```bash
export SAATHI_ENG_ORCH_ENABLED=1
export SAATHI_ENG_ORCH_LAUNCH=1
export SAATHI_ENG_ORCH_WRITES=1
# optional:
# export SAATHI_ENG_ORCH_COMMITS=1
# export SAATHI_ENG_ORCH_PUSHES=1
.venv/bin/python -m saathi.engineering launch <item_id> --adapter claude_code --write
```

Never pass `--unsafe`, `--force-push`, `--deploy`, or `--skip-approval`.

## Stop a session

```bash
.venv/bin/python -m saathi.engineering stop <session_id>
.venv/bin/python -m saathi.engineering stop <session_id> --force   # audited force
```

## Disable immediately

```bash
unset SAATHI_ENG_ORCH_ENABLED SAATHI_ENG_ORCH_LAUNCH \
      SAATHI_ENG_ORCH_WRITES SAATHI_ENG_ORCH_COMMITS SAATHI_ENG_ORCH_PUSHES
```

## Rollback package

```bash
git revert <m20.0-sha>
rm -rf data/engineering/
```

## Out of scope forever for this pilot

Merge to main · production deploy · live trading · unrestricted shell/MCP · multi-repo parallel writes.
