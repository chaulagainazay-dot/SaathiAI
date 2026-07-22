# M20.5 — Canonical Engineering Session Ledger, Integrity Evidence, Recovery

## Purpose

Make engineering sessions **auditable and recoverable** without inventing a second Mission Engine or harness RunLedger.

## Components

| Module | Role |
|--------|------|
| `session_ledger.py` | Append-only JSONL + hash chain (`session_ledger.jsonl`) |
| `evidence.py` | Integrity baselines/checks/violations as evidence files + ledger events |
| `recovery.py` | Stale lease reclaim, missing-PID crash mark, resume plan (no auto-launch) |
| `store.put_session` | Emits `session_created` / `session_status` ledger events |

## Data layout (under store root, default `data/engineering/`)

```text
session_ledger.jsonl
session_ledger_meta.json
integrity_evidence/*.json
sessions.json          # mutable state (existing)
checkpoints.json       # existing
```

## Recovery semantics

* **reclaim_lease** → `terminated` + ledger `stop`
* **mark_crashed** → `crashed` when owner PID missing
* **resume_ready** → marks session with checkpoint metadata; **never** auto-launches agents

## CLI

```bash
.venv/bin/python -m saathi.engineering ledger
.venv/bin/python -m saathi.engineering ledger <session_id>
.venv/bin/python -m saathi.engineering recover
.venv/bin/python -m saathi.engineering recover --dry-run
.venv/bin/python -m saathi.engineering evidence <session_id>
.venv/bin/python -m saathi.engineering resume-plan <session_id>
```

## Explicit non-goals

* Not harness `run_ledger`  
* Not OS/process checkpointing of agent PIDs across reboot as full resume  
* Not merge/deploy/trading  

## Next

M20.6 live small-model certification (if environment allows).
