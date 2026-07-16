# M20.4 Runbook — Engineering Control Center

## Enable (local pilot only)

```bash
export SAATHI_ENG_ORCH_ENABLED=1
export SAATHI_ENG_ORCH_LAUNCH=1
# keep writes/commits/pushes unset/false
unset SAATHI_ENG_ORCH_WRITES SAATHI_ENG_ORCH_COMMITS SAATHI_ENG_ORCH_PUSHES
```

## Monitor

```bash
python -m saathi.engineering control-center
python -m saathi.control_center.cli engineering
python -m saathi.engineering monitor <session_id>
```

## Approve + launch read-only (Claude)

```bash
python -m saathi.engineering approve-readonly <item_id> --adapter claude_code
python -m saathi.engineering launch <item_id> --mode readonly --adapter claude_code --approval <approval_id>
```

Mock (deterministic, no external Claude):

```bash
python -m saathi.engineering launch <item_id> --mode readonly --adapter mock
```

## Integrity

```bash
python -m saathi.engineering integrity > /tmp/snap.json
# after session
python -m saathi.engineering integrity verify /tmp/snap.json
```

## Quarantine

If integrity fails: session status `quarantined`, operator review required. **Do not** auto-reset user work.

## Stop / disable

```bash
python -m saathi.engineering stop <session_id>
unset SAATHI_ENG_ORCH_ENABLED SAATHI_ENG_ORCH_LAUNCH
```

## Rollback

Revert M20.4 commit or leave flags off. JSON store under `data/engineering/` is pilot-local.
