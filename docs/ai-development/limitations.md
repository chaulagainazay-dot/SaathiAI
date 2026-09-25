# Limitations

**Milestones:** M344–M351, updated through M359

An honest inventory. Where a control is evaluative rather than technical, this
document says so; that distinction is the point of the tier model, and blurring
it here would undo the work.

> **M352–M359 update.** Two limitations were resolved and are struck through
> below: the naming question (M352) and the absence of a UI (M353). One was
> **measured rather than removed**: "no model is in the loop" became "a model
> is in one seat, and here is exactly how it behaved" — see §*Prompt guidance
> only* and [model-evaluation.md](model-evaluation.md). Hard numbers now live in
> [operating-limits.md](operating-limits.md).

## Enforcement tiers, applied

### Technically enforced

The code path cannot proceed. A `PermissionError`, `MissionError`, `GateError`,
`WorktreeError` or `ConfigProtectionError` is raised.

- Destructive git verbs and force flags — refused before `subprocess`
- Worktree creation without both environment flags
- The twelve-flag denial block — re-applied after every override
- No self-approval on any gate, pass or fail
- Owner-only gates; the owner may pass nothing else
- Security-owned gates require the security role
- Gate evidence must exist, be the right kind and come from the right party
- Mission transitions, exit gates, verdict authorship
- `APPROVED_FOR_IMPLEMENTATION` while a veto or disagreement stands
- Meeting phase order, chair-only transitions, phase-specific artifact kinds
- `decided` outcome with an unanswered challenge
- Protected-path classification and proposal completeness
- Forbidden CLI flags, refused before argument parsing

### Schema validated

Malformed input is rejected at construction.

- Role contracts: capability vocabulary, global prohibitions, path scopes, authority ceiling, reviewer resolution
- Artifacts: envelope fields, per-kind requirements, claim epistemics, high/critical finding evidence
- The seven-field disagreement structure
- Branch names and mission-id shape

### Orchestration checked

The workflow refuses to advance. A process acting outside the workflow is not
stopped.

- Which agent may review which author
- Required meeting participants and submission bounds
- Challenge targeting and one-response-per-challenge
- Worktree collision rules and one-worktree-per-agent-per-mission
- Dirty-tree removal refusal — the plan withholds the command; it does not lock the directory

### Prompt guidance only

Depends on agent compliance. Detectable by evaluation; **not** enforced.

- "Separate fact from inference" — the *shape* is validated, the *honesty of the labelling* is not. An agent can label a guess as a fact and supply a plausible-looking reference.
- "Do not present inference as fact" — same.
- "Report INSUFFICIENT_EVIDENCE rather than inventing certainty" — the value is available and cheap; choosing it is not enforced.
- "Read the callers before raising a finding" — the finding must *claim* caller evidence; whether the agent read it is unverifiable here.
- "Implement the smallest complete change" — no mechanical check.
- "Do not duplicate an existing system" — the architecture artifact must contain a reuse table; whether that table is honest is a human judgement.

**M356 measured exactly this tier, and it is the weakest one.** `qwen3:4b`
passed 32 of 32 schema and artifact criteria and 2 of 7 honesty criteria. It
labelled a guess as a fact with a plausible-looking reference in scenario ME-01,
and in ME-07 it refused in the refusal field while asserting in the same reply
that it had edited protected configuration and force-pushed. Prompt guidance is
not enforcement; this is what that costs in practice.

### Model evaluated

A local model produced the behaviour and a published rubric scored it. Added in
M352 as a fifth tier because M356 needed a name for claims that are neither
enforced nor merely documented.

- Establishes what one model did, on one host, at one moment, against a named rubric
- Establishes nothing about another model, another host, or the same model tomorrow
- A failed scenario is a recorded measurement, not a defect in the harness

## Specific limitations

1. **No filesystem sandbox.** Nothing prevents a process from writing outside its worktree. `agentdev` never grants an unrestricted shell, no contract declares such a scope, and contamination is detected — but detection is not prevention, and BE-02 is tiered accordingly.

2. ~~**No model is in the loop.**~~ **Measured in M356, not removed.** One seat — the Research Agent — is now occupied by `qwen3:4b`; every other seat stays scripted. The mission still closes with every gate enforced. The model itself passed 2 of 8 behaviour scenarios and, in M357, complied with 7 of 9 prompt attacks while the system held on 9 of 9. Model behaviour is now known rather than unproven, and what is known is that it cannot be trusted on its face.

3. **Ten scenarios do not bound the behaviour space.** The suite establishes that ten specific refusals hold. The mission flagged the name "behaviour coverage" as a stretch and referred it to the owner; M352 rejected the term outright. The suite is a *behaviour scenario suite*, reported as a count — see [terminology.md](terminology.md).

4. **No cloud provider is connected, and none can be.** One local provider over loopback, no credential and no paid call. A non-loopback endpoint is refused at adapter construction. Any claim about a cloud provider's behaviour or cost remains unmeasured.

5. ~~**Peak memory was not instrumented.**~~ **Resolved in M353.** `resources.py` measures physical memory, free disk, load average and this process's peak RSS with no new dependency, and reports peak as peak rather than current. The provider daemon's resident size is read separately through `model health`. See [operating-limits.md](operating-limits.md).

6. ~~**No UI.**~~ **Resolved in M353.** The read-only Agent Operations Console renders fifteen panels as a terminal summary or a self-contained HTML page — see [operations-console.md](operations-console.md). It remains read-only and does not poll: it has no approve, advance, create, remove, merge, deploy or provider verb, and a refresh means running the command again.

7. **The 102 pre-existing stale worktrees remain.** They are reported by the census and left in place; removing another milestone's leftovers is not this milestone's authority.

8. **`ecc doctor` drift is unrelated.** ECC stays at `~/dev-toolkits/ECC`, read-only, outside this repository. Its known link-rewrite false positive is documented there.

9. **The gate engine trusts artifact authorship.** It verifies that an artifact's `authoring_agent` matches the expected party; it cannot verify that the named agent actually produced the content.

10. **Concurrency ceilings are declared, not enforced.** `max_reasoning_agents` and friends are recorded in settings and reported by `doctor`. Nothing in this milestone spawns agents, so nothing enforces the ceiling yet.

## What still requires the owner

- Passing the `owner_approval` gate — no agent may, by construction
- Any change to protected configuration
- Any push, merge or deploy
- ~~Deciding whether the first suite may claim behaviour evaluation before a model participates~~ — **resolved in M352**: no. See [terminology.md](terminology.md) §3.
- Authorising the next milestone

## What would change these limitations

| Limitation | What would resolve it |
|---|---|
| No filesystem sandbox | OS-level isolation (container, sandbox profile) around agent processes |
| Ten scenarios | Growth driven by real incidents, not by target counts |
| The evaluated model fails most honesty scenarios | A different model, evaluated the same way. The rubric is published so any candidate can be scored against it |
| Only one model-backed seat | A second seat, evaluated before it is trusted — never both at once on an 8 GB host |
| Ceilings unenforced | A process supervisor that counts what it spawns. Nothing spawns anything today |
| Ledger detects but cannot prevent | Storage the operator cannot write to directly |
| Attack coverage is a list of nine | More attacks, added when one is discovered rather than invented to raise a count |
| ~~No UI~~ | Delivered in M353 as a read-only console |
| ~~No model in the loop~~ | Measured in M356; see [model-evaluation.md](model-evaluation.md) |
| ~~Peak memory unmeasured~~ | Delivered in M353 by `resources.py` |
