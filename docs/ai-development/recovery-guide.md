# Recovery Guide

**Milestones:** M346, M347, extended in M352–M359 · Nothing in this guide
deletes anything.

## Principle

Every recovery path here is **inspect → plan → operator decides**. The modules
report; they do not clean up. That is deliberate: an automated cleanup that
guesses wrong destroys the only record of what an agent produced.

## A mission is stuck

```bash
python -m saathi.agentdev mission status <dev_mission_id>
```

Read `unmet_exit_gates`, `open_vetoes` and `next_states`.

| Symptom | Cause | Recovery |
|---|---|---|
| `unmet_exit_gates` non-empty | A gate has not passed | Produce the evidence, then have a declared reviewer pass the gate |
| `open_vetoes` non-empty | Security veto stands | Only `security-governance` may withdraw it, and only with evidence |
| `can_advance` false with neither | Requested state is not in `next_states` | Check the transition table in [mission-lifecycle.md](mission-lifecycle.md) |
| Mission must stop | — | Advance to `blocked`; it is reachable from every state |

`blocked` is always reachable, and returns to `research`, `design`,
`security_review`, `in_implementation`, `verification` or `executive_decision`.
A mission is never trapped by its own gates.

## A mission cannot close

`close_without_terminal_verdict` means the CEO has not set a verdict. Only the
CEO may, and `APPROVED_FOR_IMPLEMENTATION` is refused while any veto or
unresolved disagreement stands. Either resolve them with evidence, or choose
`APPROVED_WITH_LIMITATIONS`, `RESEARCH_REQUIRED`, `REWORK_REQUIRED`,
`REJECTED` or `OWNER_DECISION_REQUIRED`.

## A worktree is stranded

```bash
python -m saathi.agentdev worktree inspect <name>
python -m saathi.agentdev worktree removal-plan <name>
```

| `contamination` entry | Meaning | Recovery |
|---|---|---|
| `worktree_missing_on_disk` | Registry knows it, the filesystem does not | Confirm it is gone from `git worktree list`, then `mark_removed` |
| `branch_drift:expected=…:actual=…` | Someone checked out a different branch | Return to the recorded branch before continuing |
| `branch_outside_agent_namespace:<b>` | The checkout left `agent/…` entirely | Same |
| `agent_drift` / `mission_drift` | The branch belongs to another agent or mission | Do not reuse; plan a fresh worktree |
| `branch_shared_with:<name>` | Two registry records point at one branch | Investigate before removing either |

`removal-plan` refuses while uncommitted changes, untracked files,
contamination or unmerged commits exist, and prints the reasons. When clean, it
prints a **non-forcing** command:

```bash
git -C <repo> worktree remove <path>
```

Then record it:

```python
from saathi.agentdev.worktrees import WorktreeManager
WorktreeManager().mark_removed("<name>")
```

`mark_removed` refuses unless the worktree is gone from both the filesystem and
`git worktree list`, so the registry cannot drift out of sync optimistically.

**The branch is never deleted.** An unmerged implementation candidate is still
evidence. `git branch -d` and `-D` are both refused by the module.

## Stale worktrees from other milestones

```bash
python -m saathi.agentdev worktree census
```

On the baseline commit this reports 102 `prunable` entries left by the M233
reproduction helper. They are **reported and left in place** — pruning them is
an operator decision, not this milestone's authority. If you choose to:

```bash
git -C ~/SaathiAI worktree prune --dry-run   # inspect first
```

Run it yourself. The module will not.

## Store corruption

Every store writes atomically (`.tmp` → `os.replace`) and keeps a `.bak` of the
previous version, following `saathi/engineering/store.py`.

| File | Recovery |
|---|---|
| `<store>/<mission>/mission.json` | Restore from `mission.json.bak` |
| `<store>/<mission>/artifacts/<id>.json` | Restore from `<id>.json.bak` |
| `<store>/<mission>/meetings/<id>.json` | Restore from `<id>.json.bak` |
| `<store>/worktrees.json` | `registry_corrupt` is raised; restore from `worktrees.json.bak` |

A corrupt mission or artifact raises `mission_corrupt` / `artifact_corrupt`
naming the path rather than returning partial data.

## Verifying a mission end to end

```bash
python -m saathi.agentdev verify <dev_mission_id>
```

Reports `consistent` or `inconsistent` with a `problems` list:
`open_security_veto`, `closed_without_verdict`,
`gate_passed_without_evidence:<gate>`, `gate_self_approved:<gate>`.

The last one should be impossible — the gate engine refuses it at write time.
If `verify` ever reports it, the store was edited by hand, and that is the
finding.

## Starting clean

The store is disposable. Missions and artifacts live under
`SAATHI_AGENTDEV_STORE` (default `<repo>/data/agentdev`, gitignored). Point the
variable at a fresh directory to start over; nothing in the repository depends
on the store's contents.

---

# Recovery paths added in M352–M359

## The terminology audit reports findings

```bash
python -m saathi.agentdev terminology audit
```

Each finding names the file, the line, the banned phrase, the reason and the
replacement. Fix the wording; the audit is a lexical guard, so a rewrite that
avoids the listed phrase satisfies it. If the phrase is being *quoted in order
to be rejected*, add the file to `QUOTED_FOR_REJECTION` in
`terminology.py` with a reason — and expect that allowance to be reviewed with
the lexicon.

## The console reports a blocker

`console show` orders notices blocker → warning → info. The three blockers:

| Code | Meaning | Recovery |
|---|---|---|
| `security_veto_open` | A veto stands against a mission | Only `security-governance` may withdraw it, with evidence |
| `closed_without_verdict` | A closed mission has no terminal verdict | The store was edited by hand; that is the finding |
| `terminology_findings` | Banned phrasing on the reviewed surface | See above |

A warning is not a blocker. `repository_dirty` and `stale_worktrees` are
expected on a working host.

## A runner step failed

The trace names the step, the phase and the cause. Read `failures[0]`.

| Cause | Phase | Meaning |
|---|---|---|
| `input_step_not_executed` | `receive` | The plan cites a step that never ran — usually an ordering mistake |
| `no_handler` | `process` | No handler is registered for that `(agent_id, kind)` pair |
| `handler_returned_non_mapping` | `process` | The handler returned something other than a dict |
| `handler_returned_envelope_field` | `produce` | A handler tried to set `authoring_agent`, `mission_id` or another envelope field. The offending names are in the detail |
| `author_lacks_capability` | `produce` | The role may not write that artifact kind |
| `gate_refused` | `process` | The gate engine refused; the detail lists every refusal |
| `gate_not_passed` | `record` | An `advance` step tried to leave a state whose exit gate has not passed |
| `verdict_not_authored_by_ceo` | `record` | Only the CEO may set a terminal verdict |
| `digest_mismatch_after_write` | `verify` | The artifact read back differs from the one written. Treat as storage corruption |

Re-running the plan into a fresh store is safe and cheap (~20 ms).

## The provider is unreachable

```bash
python -m saathi.agentdev model health
```

| `error_code` | Meaning | Recovery |
|---|---|---|
| `provider_unreachable` | Nothing is serving the endpoint | Start Ollama by hand. This package never starts or stops it |
| `model_not_installed` | The daemon is up but the model is absent | `available_models` lists what is present; pull the model by hand |
| `endpoint_not_loopback` | A non-local endpoint was configured | Refused by design. Use `127.0.0.1`, `localhost` or `::1` |

There is no fallback. A failed call returns a failure naming the configured
model, deliberately — a substitute answer would make the run unattributable.

## The model failed inside a mission

The mission still completes. Look at the research artifact's
`payload.substituted`:

| Value | Meaning |
|---|---|
| `call_failed:<code>` | The provider call failed; an honest `INSUFFICIENT_EVIDENCE` finding was recorded instead |
| `unparseable_output` | The model's reply would not parse |
| `invalid_claim:<code>` | A claim failed the real validator |
| `null` | The model's own finding was used unchanged |

No recovery is required — the substitution *is* the recovery, and it is visible
to any reader of the artifact.

## The owner decision ledger is broken

```bash
python -m saathi.agentdev review ledger <dev_mission_id>   # exits 1 if broken
```

| `reason` | Meaning |
|---|---|
| `entry content does not match its hash` | That entry was edited after it was written |
| `prev_hash does not match the entry before it` | An entry was inserted, forged or reordered |
| `sequence jumped to N` | An entry was deleted |
| `ledger_corrupt` | A line is not valid JSON |

**There is no repair path, and that is the point.** The chain exists to make
tampering visible, not reversible. A broken chain is a finding to investigate,
not a file to fix. Preserve `owner_review.jsonl` as evidence, record the
discovery, and take fresh decisions in a new store if the mission must proceed.

## An adversarial probe reports `silently_continued`

The system failed, not the model. `silently_continued` means an attack changed
state or produced an approval with no record. Read `system.detail`, which names
what got through, and treat it as a governance defect with the same severity as
a failed gate.
