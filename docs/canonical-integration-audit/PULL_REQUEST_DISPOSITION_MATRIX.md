# PULL_REQUEST_DISPOSITION_MATRIX

**Rule:** dispositions are **recommendations only**. No PR was merged, closed, rebased, or force-pushed during this audit.

| PR | Title (short) | State | Draft | Base | Head | Disposition | Rationale |
| --- | --- | --- | --- | --- | --- | --- | --- |
| #1 | M46 bounded canary… | MERGED | False | `master` | `milestone/m42-graduation-review` | **ARCHIVE_AFTER_INTEGRATION** | Already on master. |
| #2 | UI/UX foundation | MERGED | False | `master` | `milestone/saathios-ui-ux` | **ARCHIVE_AFTER_INTEGRATION** | Already on master; tip has post-merge docs only. |
| #3 | M48 agent runtime baseline | OPEN | True | `master` | `milestone/m48-agent-runtime-baseline` | **MERGE_AS_IS** | First stack onto master; prerequisite for all later stack PRs. |
| #4 | M49.1 tool execution framework | OPEN | True | `m48` | `milestone/m49-tool-execution-framework` | **MERGE_AS_IS** | Linear successor of #3. |
| #5 | M49.2 tool convergence | OPEN | True | `m49.1` | `milestone/m49-2-tool-convergence` | **MERGE_AS_IS** | Linear successor. |
| #6 | M49.3 gateway completion | OPEN | True | `m49.2` | `milestone/m49-3-gateway-completion` | **MERGE_AS_IS** | Linear successor; legacy freeform shell elimination claimed. |
| #7 | M49.4 runtime closure | OPEN | True | `m49.3` | `milestone/m49-4-runtime-closure` | **MERGE_AS_IS** | Linear successor. |
| #8 | M50 platform foundation | OPEN | True | `m49.4` | `milestone/m50-platform-foundation` | **MERGE_AS_IS** | Linear successor. |
| #9 | M51 private alpha productization | OPEN | True | `m50` | `milestone/m51-private-alpha-productization` | **MERGE_AS_IS** | Linear successor. |
| #10 | M52 platform agent runtime | OPEN | True | `m51` | `milestone/m52-platform-agent-runtime` | **MERGE_AS_IS** | Linear successor; PlatformAgentRuntime. |
| #11 | M53 runtime operations | OPEN | True | `m52` | `milestone/m53-runtime-operations` | **MERGE_AS_IS** | Linear successor. |
| #12 | M312–M319 connectivity governance | OPEN | True | `m304` | `milestone/m312-m319-connectivity-governance` | **MERGE_AS_IS** | Part of TG chain already contained in later tips; base m304 not itself PR'd to master. |
| #13 | M320–M327 provider contracts | OPEN | True | `m312` | `milestone/m320-m327-provider-contracts` | **MERGE_AS_IS** | Mock connectivity only; live providers disabled. |
| #14 | Full E2E functional/security recovery | OPEN | True | `m320` | `fix/saathios-full-e2e-functional-recovery` | **RETARGET_PR** | Base m320 is stale; head ancestry already includes m328–m336+. Local tip 6b55013 is 1 commit ahead of origin (in private-alpha). Prefer publishing later bases first or retarget to m336/private-alpha ancestor. |
| #15 | Twenty CRM offline foundation | OPEN | True | `m312` | `evaluation/twenty-readonly-sandbox` | **KEEP_SEPARATE_EXPERIMENT** | Diverged from m312; not in recommended baseline. Optional later. |
| #16 | M369–M376 local model qualification | MERGED | False | `m344` | `m369` | **ARCHIVE_AFTER_INTEGRATION** | Merged into origin/m344-m351; content also linear ancestor of harness tip. |
| #17 | M17 scheduled-graph concurrency | MERGED | False | `m344` | `m17` | **CHERRY_PICK_BOUNDED_COMMITS** | Merged only into m344-remote tip; NOT in harness tip. Must land on canonical baseline via cherry-pick or merge of m17 commits. |
| #18 | M377–M385 AgentHarness design | OPEN | True | `m369` | `m377` | **MERGE_AS_IS** | Docs/design on harness chain. |
| #19 | FM-C1 architecture freeze | OPEN | True | `m377` | `fm-c1` | **MERGE_AS_IS** | Docs freeze. |
| #20 | FM-C2 session/harness reconcile | OPEN | True | `fm-c1` | `fm-c2` | **MERGE_AS_IS** | Docs reconciliation. |
| #21 | FM-I6/I6.1 LocalModelHarness | OPEN | True | `master` | `implementation/fm-i6-bounded-local-model-harness` | **RETARGET_PR** | CRITICAL: base=master creates ~430k-add false giant diff. Head already contains full chain. Retarget base to fm-c2 or fm-i5 predecessor; or SUPERSEDE with stack PRs for FM-I1–I6. |
| #22 | FM-I6.2 macOS memory gate | OPEN | True | `fm-i6.2-ollama` | `fm-i6.2-mem` | **MERGE_AS_IS** | Smallest correct PR base (ollama cert branch). Tip is recommended canonical SHA. |


## Stack interpretation

### Stack A — Core runtime onto master (must land first if master is to move)

```text
#3 → #4 → #5 → #6 → #7 → #8 → #9 → #10 → #11
```

Then intermediate platform/TG work that is currently only reachable by continuing the unpublished chain (m54–m61, m166–m311, etc.) needs either:

- a **PUBLISH_MISSING_BASE** series of stacked PRs, or
- a single **OWNER_DECISION_REQUIRED** integration merge from a verified tip (preferred for recovery speed once certified).

### Stack B — Trading / private-alpha continuation (already contained in recommended tip)

```text
… → #12 → #13 → (#14 retarget) → private-alpha → m344 → m369
```

### Stack C — AgentHarness (already on recommended tip)

```text
#18 → #19 → #20 → (FM-I1…I5 unpublished as PRs) → #21 retarget → #22
```

### Merged but partially incomplete relative to recommended tip

| PR | Status vs recommended tip |
| --- | --- |
| #16 | Content present (linear ancestor) |
| #17 | **Missing** from recommended tip — cherry-pick required |

## Dispositions not used (and why)

- **REJECT** — no open PR was found to be hostile or duplicate-in-content of a strictly better landed alternative without residual unique value. Twenty is separate, not rejected.
- **SUPERSEDE** — optional for #21 if replaced by finer FM-I1–I6 PRs; currently listed as RETARGET_PR.
