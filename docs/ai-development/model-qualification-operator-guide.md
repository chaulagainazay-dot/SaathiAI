# Model Qualification — Operator Guide

**Milestones:** M369–M376
**Command group:** `python -m saathi.agentdev qualification`

Every command here is operator-invoked and read-only unless it is the
qualification run itself. Nothing schedules, polls or runs on its own.

## 1. Reading the current state

```bash
# The thirteen panels as a terminal summary
python -m saathi.agentdev qualification show

# The same state as JSON
python -m saathi.agentdev qualification state

# Installed models, digests, host eligibility
python -m saathi.agentdev qualification inventory

# Memory, swap, pressure, disk right now
python -m saathi.agentdev qualification baseline

# Owner decision, authority boundary, every role threshold
python -m saathi.agentdev qualification thresholds

# The routing decision for one role, or the whole policy
python -m saathi.agentdev qualification route --role RESEARCH_DRAFTING
python -m saathi.agentdev qualification route
```

These read evidence files. They contact no provider except `inventory` and
`baseline`, which read loopback Ollama endpoints.

## 2. Verifying claims in a model response

```bash
python -m saathi.agentdev qualification verify-claims --file response.json
cat response.json | python -m saathi.agentdev qualification verify-claims
```

Classifies every model claim in the output as a verified claim, an unverified
claim or a contradictory claim, against external evidence.

## 3. Rendering the console

```bash
python -m saathi.agentdev qualification render --output /path/to/page.html
```

The page is static. No form, no button, no input, no script that mutates
anything, no polling.

## 4. Running the qualification suite

This is the one command that loads models. Expect roughly ten to fifteen minutes
on an 8 GiB machine for three small models, and expect the machine to be busy.

```bash
# Everything eligible, three runs per scenario
python scripts/run_m369_m376_qualification.py --runs 3

# One model only — prior evaluations are preserved, not dropped
python scripts/run_m369_m376_qualification.py --models qwen3:4b

# Rebuild matrix, routing and certification from evidence already on disk.
# Loads no model.
python scripts/run_m369_m376_qualification.py --rebuild-only

# Certify with the counts from a recorded pytest run
python scripts/run_m369_m376_qualification.py --rebuild-only --tests tests.json
```

### Before running

- Close what you can. The run competes with everything else for memory.
- Check `qualification baseline`. If swap is nearly full, wait.
- `ollama ps` should be empty. The run unloads residents first, but a model
  loaded by something else mid-run will trip the ceiling.

### What it writes

Only into `docs/evidence/m369_m376/`. It creates scratch state under
`.saathi-agent-state/m369_qualification/run-<timestamp>/`, fresh per run — a
reused scratch directory collides with the previous run's mission ids, the
probes raise, and a raising probe is conservatively recorded as
`SYSTEM_FAILED_OPEN`. That turns leftover state into a fabricated boundary
breach, so the directory is never reused.

### If it aborts a model

That is the resource guard working. The model is recorded as
`EVALUATION_INCOMPLETE` with the breach text. Free memory and re-run with
`--models <that model>`; the other evaluations are preserved.

## 5. Reading a `BLOCKED` certificate

`LOCAL_MODEL_QUALIFICATION_BLOCKED` has two quite different causes, and the
certificate distinguishes them in `verdict_reasons`:

| Reason | What to do |
|---|---|
| Attacks the system failed open on, no probe errors | A real boundary finding. Stop and fix the control. |
| The reasons name probe errors | An evaluation fault. The harness raised before it could measure the control. Fix the harness and re-run. |
| Failing tests | Fix the tests; the count came from a recorded run. |

`probe_errors` is also reported as its own number at the top level.

## 6. Test counts

The certifier never runs pytest. Supply a recorded run:

```json
{
  "discovered": 1462,
  "executed": 1462,
  "passed": 1462,
  "failed": 0,
  "skipped": 0,
  "commands": ["python -m pytest tests/ -q"]
}
```

A certificate that measured its own tests would be the same class of
self-report this range exists to distrust.

## 7. What no command here does

Downloads a model · deletes a model · starts a mission · approves anything ·
writes outside the evidence directory · changes a global configuration ·
contacts a cloud provider · spends money · pushes · merges · deploys.

## Companion documents

- [Overview](model-qualification-overview.md)
- [Limitations](model-qualification-limitations.md)
- [Routing policy](local-model-routing-policy.md)
