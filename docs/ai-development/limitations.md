# Limitations

**Milestones:** M344–M351

An honest inventory. Where a control is evaluative rather than technical, this
document says so; that distinction is the point of the four-tier model, and
blurring it here would undo the work.

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

## Specific limitations

1. **No filesystem sandbox.** Nothing prevents a process from writing outside its worktree. `agentdev` never grants an unrestricted shell, no contract declares such a scope, and contamination is detected — but detection is not prevention, and BE-02 is tiered accordingly.

2. **No model is in the loop.** Every agent in the simulated mission is a scripted caller of the real modules. The systems are proven; agent *behaviour* under a real model is not. This is exactly the objection the Testing agent raised in the red-team review, and it is preserved unresolved rather than answered.

3. **Ten scenarios do not bound the behaviour space.** The suite establishes that ten specific refusals hold. The mission flagged the name "behaviour coverage" as a stretch and referred it to the owner; M352 rejected the term outright. The suite is a *behaviour scenario suite*, reported as a count — see [terminology.md](terminology.md).

4. **No provider is connected.** No credential, no network, no paid call. Any claim about live-provider behaviour or cost is unmeasured.

5. **Peak memory was not instrumented.** Only wall-clock duration was measured. The Cost agent recorded this as a limitation rather than estimating.

6. **No UI.** There is no operator console, dashboard or Control Center surface. The CLI is the only interface.

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
| No model in the loop | The next milestone's controlled provider routing |
| Ten scenarios | Growth driven by real incidents, not by target counts |
| Peak memory unmeasured | `resource.getrusage` instrumentation in the suite runner |
| No UI | An operations console, explicitly deferred |
