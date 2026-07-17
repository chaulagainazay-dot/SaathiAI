# M26 Operations Guide

## Commands

```bash
# Lifecycle
.venv/bin/python -m saathi.inference.ops start
.venv/bin/python -m saathi.inference.ops status
.venv/bin/python -m saathi.inference.ops readiness
.venv/bin/python -m saathi.inference.ops health
.venv/bin/python -m saathi.inference.ops drain
.venv/bin/python -m saathi.inference.ops stop
.venv/bin/python -m saathi.inference.ops restart
.venv/bin/python -m saathi.inference.ops recover

# Mode
.venv/bin/python -m saathi.inference.ops mode OFF
.venv/bin/python -m saathi.inference.ops mode SHADOW
.venv/bin/python -m saathi.inference.ops mode CANARY
.venv/bin/python -m saathi.inference.ops mode ACTIVE   # requires production_certified
.venv/bin/python -m saathi.inference.ops rollback

# Console
.venv/bin/python -m saathi.m20_console inference-ops

# Certification (unchanged)
.venv/bin/python -m saathi.inference.runtime_gate
.venv/bin/python -m saathi.inference.release_check
.venv/bin/python -m saathi.inference.cert_evidence status
```

## Fresh install / uncertain state

Default mode is **OFF**. Do not silently activate the host.

## Disable inference

```bash
.venv/bin/python -m saathi.inference.ops mode OFF
.venv/bin/python -m saathi.inference.ops stop
export SAATHI_INFERENCE_KILL_ALL=1   # existing kill switch
```

## Evidence paths

```text
docs/evidence/m26/ops_state.json
docs/evidence/m26/incidents.json
docs/evidence/m26/ops_events.jsonl
docs/evidence/m26/mode_history.jsonl
docs/evidence/m25/…   # certification package (preserved)
```

## Trading Guardian

```text
UNCHANGED / UNENGAGED
```
